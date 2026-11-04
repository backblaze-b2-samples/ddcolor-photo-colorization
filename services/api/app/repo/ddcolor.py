"""DDColor adapter: the ONLY module that imports torch or DDColor, and lazily.

The heavy stack (torch, torchvision, timm, opencv, DDColor) lives in
`services/api/requirements-ml.txt` and is installed by `pnpm setup:ml`, not by
`pnpm run setup`. The core API, `pnpm verify` and CI therefore run without it;
`ml_available()` answers cheaply (no import) so the run endpoint can return an
actionable 503 instead of failing mid-batch.

Inference follows DDColor's own `ColorizationPipeline`: convert to Lab, predict
the `ab` channels at the model input size, resize `ab` back to the original
resolution and recombine it with the original `L` channel, so the output has the
source's exact dimensions.

Device: `auto` picks the first available of CUDA, Apple MPS, then CPU. MPS runs
with `PYTORCH_ENABLE_MPS_FALLBACK=1` so an unsupported op falls back to CPU
rather than failing. Only ONE checkpoint is kept resident: switching model
evicts the previous one (the large checkpoints are ~900 MB each).
"""

import gc
import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

HF_ORG = "piddnad"
INSTALL_HINT = (
    "DDColor is not installed. Install the optional ML stack with `pnpm setup:ml` "
    "(it runs services/api/scripts/install_ml.sh: pip install -r requirements-ml.txt, "
    "then DDColor pinned to a commit), then restart the API."
)
_REQUIRED_MODULES = ("torch", "cv2", "huggingface_hub", "ddcolor")


class EngineUnavailableError(RuntimeError):
    """The optional ML stack is missing or the model could not be loaded."""


def ml_available() -> bool:
    """True when every module inference needs is importable (does not import it)."""
    return all(importlib.util.find_spec(name) is not None for name in _REQUIRED_MODULES)


def resolve_device(preference: str, *, cuda: bool, mps: bool) -> str:
    """Pick the inference device. Pure, so the policy is unit-testable.

    `auto` -> first of cuda, mps, cpu. An explicit choice that is unavailable
    falls back to cpu (logged) rather than failing the batch.
    """
    pref = (preference or "auto").strip().lower()
    if pref == "auto":
        return "cuda" if cuda else "mps" if mps else "cpu"
    if pref == "cuda" and cuda:
        return "cuda"
    if pref == "mps" and mps:
        return "mps"
    if pref not in ("cpu", "cuda", "mps"):
        logger.warning("Unknown DDCOLOR_DEVICE=%r; using cpu", preference)
    elif pref != "cpu":
        logger.warning("DDCOLOR_DEVICE=%s is not available here; using cpu", pref)
    return "cpu"


@dataclass
class _Loaded:
    model_id: str
    revision: str
    device: str
    model: Any


_lock = Lock()
_resident: _Loaded | None = None


def _import_stack() -> tuple[Any, Any, Any, Any]:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    try:
        import torch
        from ddcolor import ColorizationPipeline, DDColor
        from huggingface_hub import PyTorchModelHubMixin, snapshot_download
    except ImportError as e:
        raise EngineUnavailableError(f"{INSTALL_HINT} ({e})") from e

    class DDColorHF(DDColor, PyTorchModelHubMixin):
        """DDColor with Hugging Face Hub loading, as the upstream README defines it."""

        def __init__(self, config=None, **kwargs):
            if isinstance(config, dict):
                kwargs = {**config, **kwargs}
            super().__init__(**kwargs)

    return torch, ColorizationPipeline, DDColorHF, snapshot_download


def _evict(torch: Any) -> None:
    global _resident
    _resident = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if hasattr(torch, "mps") and torch.backends.mps.is_available():
        torch.mps.empty_cache()


def load_model(model_id: str, device_preference: str) -> tuple[str, str]:
    """Ensure `model_id` is resident. Returns (model_version, device).

    `model_version` is `<model_id>@<Hugging Face revision sha>`. Weights are
    public (no token) and cached under HF_HOME after the first download.
    """
    global _resident
    torch, _pipeline, model_cls, snapshot_download = _import_stack()
    device = resolve_device(
        device_preference,
        cuda=torch.cuda.is_available(),
        mps=hasattr(torch.backends, "mps") and torch.backends.mps.is_available(),
    )
    with _lock:
        if _resident and _resident.model_id == model_id and _resident.device == device:
            return f"{model_id}@{_resident.revision}", device
        if _resident is not None:
            _evict(torch)
        try:
            repo_id = f"{HF_ORG}/{model_id}"
            # The snapshot path names the exact revision (provenance). Load by
            # repo id, not by that local path: given a directory, the Hub mixin
            # looks only for model.safetensors, and these checkpoints ship
            # pytorch_model.bin. By id it resolves the same cached files.
            snapshot = snapshot_download(repo_id)
            model = model_cls.from_pretrained(repo_id)
            model = model.to(torch.device(device)).eval()
        except Exception as e:
            raise EngineUnavailableError(f"could not load DDColor '{model_id}': {e}") from e
        _resident = _Loaded(model_id, Path(snapshot).name, device, model)
        logger.info("DDColor %s loaded on %s (rev %s)", model_id, device, _resident.revision)
        return f"{model_id}@{_resident.revision}", device


def colorize(img: Image.Image, model_id: str, input_size: int, device_preference: str) -> Image.Image:
    """Colorize an RGB image; the result has the input's exact dimensions."""
    load_model(model_id, device_preference)
    torch, pipeline_cls, _model_cls, _download = _import_stack()
    import numpy as np

    with _lock:
        loaded = _resident
        if loaded is None:  # pragma: no cover - load_model guarantees it
            raise EngineUnavailableError("model was evicted before inference")
        pipeline = pipeline_cls(
            loaded.model, input_size=input_size, device=torch.device(loaded.device)
        )
        bgr = np.ascontiguousarray(np.asarray(img.convert("RGB"))[:, :, ::-1])
        out_bgr = pipeline.process(bgr)
    return Image.fromarray(np.ascontiguousarray(out_bgr[:, :, ::-1]))
