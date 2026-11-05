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

First use downloads the weights from the Hugging Face Hub; once they are fully
cached they are resolved offline and the download stage is skipped. The download
runs on its own daemon thread, outside the model lock, and is watched: progress
(bytes in the local cache) is reported through `on_progress`, and a download that makes
no progress for `stall_seconds` raises `EngineUnavailableError` instead of
blocking the caller forever. A stalled download thread is abandoned, never
joined, so it cannot wedge the batch worker.
"""

import gc
import importlib.util
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
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


class LoadCancelled(Exception):
    """`on_progress` asked to stop while the model was downloading or loading."""


# Called with (stage, downloaded_bytes) while a model is prepared; stage is
# "downloading_model" or "loading_model". Returning False cancels the load.
ProgressCallback = Callable[[str, int | None], bool]
_POLL_SECONDS = 1.0
# What `from_pretrained` needs from a snapshot; both present means "fully cached".
_CONFIG_FILE = "config.json"
_WEIGHT_FILES = ("pytorch_model.bin", "model.safetensors")


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
    # Plain HTTPS, not Xet: Xet assembles chunks off-disk and writes the blob in
    # bursts (nothing for the first ~15 s, then long flat spells), so the cache
    # size, which is both the progress figure and the stall watchdog's signal,
    # stops reflecting live bytes. HTTPS streams into blobs/*.incomplete.
    # setdefault: an explicit HF_HUB_DISABLE_XET in the environment still wins.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
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


def _cache_bytes(repo_id: str) -> int:
    """Bytes of `repo_id` in the local Hub cache, partial (.incomplete) files included."""
    from huggingface_hub import constants

    blobs = Path(constants.HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}" / "blobs"
    if not blobs.is_dir():
        return 0
    return sum(f.stat().st_size for f in blobs.iterdir() if f.is_file())


def _cached_snapshot(snapshot_download: Any, repo_id: str) -> str | None:
    """The local snapshot path when the config and weights are fully cached, else None."""
    try:
        path = Path(snapshot_download(repo_id, local_files_only=True))
    except Exception:  # LocalEntryNotFoundError and friends: not cached
        return None
    complete = (path / _CONFIG_FILE).is_file() and any(
        (path / name).is_file() for name in _WEIGHT_FILES
    )
    return str(path) if complete else None


def _report(on_progress: ProgressCallback | None, stage: str, size: int | None) -> None:
    """Call `on_progress` best-effort; raise LoadCancelled when it returns False.

    Progress is advisory: an exception from the callback (for example a storage
    write timing out) is logged and the download or load carries on, so it can
    never abort the model or be mistaken for a download failure.
    """
    if on_progress is None:
        return
    try:
        keep_going = on_progress(stage, size)
    except Exception:
        logger.warning("Progress callback failed during %s; continuing", stage, exc_info=True)
        return
    if keep_going is False:
        raise LoadCancelled()


def _watched_download(
    snapshot_download: Any, repo_id: str, on_progress: ProgressCallback | None, stall_seconds: float
) -> str:
    """Run `snapshot_download` on a daemon thread; fail on a stall, stop on cancel."""
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["path"] = snapshot_download(repo_id)
        except BaseException as e:  # re-raised on the caller thread
            result["error"] = e

    worker = Thread(target=target, name=f"hf-download-{repo_id}", daemon=True)
    worker.start()
    last_bytes, last_change = -1, time.monotonic()
    while True:
        size = _cache_bytes(repo_id)
        now = time.monotonic()
        if size != last_bytes:
            last_bytes, last_change = size, now
        elif now - last_change > stall_seconds:
            raise EngineUnavailableError(
                f"downloading {repo_id} from the Hugging Face Hub stalled: no progress for "
                f"{int(stall_seconds)} s ({size / 1e6:.0f} MB so far). Check the network, "
                "then re-run the batch; the partial download resumes."
            )
        _report(on_progress, "downloading_model", size)
        worker.join(timeout=_POLL_SECONDS)
        if not worker.is_alive():
            break
    if "error" in result:
        raise result["error"]
    return result["path"]


def _evict(torch: Any) -> None:
    global _resident
    _resident = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if hasattr(torch, "mps") and torch.backends.mps.is_available():
        torch.mps.empty_cache()


def load_model(
    model_id: str,
    device_preference: str,
    on_progress: ProgressCallback | None = None,
    stall_seconds: float = 120.0,
) -> tuple[str, str]:
    """Ensure `model_id` is resident. Returns (model_version, device).

    `model_version` is `<model_id>@<Hugging Face revision sha>`. Weights are
    public (no token) and cached under HF_HOME after the first download.
    Raises `EngineUnavailableError` (download failed or stalled) or
    `LoadCancelled` (`on_progress` returned False).
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
    repo_id = f"{HF_ORG}/{model_id}"
    try:
        # Already cached: no network, and no "downloading" stage to report.
        snapshot = _cached_snapshot(snapshot_download, repo_id)
        if snapshot is None:
            # Outside the lock: a slow download never blocks inference callers.
            snapshot = _watched_download(snapshot_download, repo_id, on_progress, stall_seconds)
    except (EngineUnavailableError, LoadCancelled):
        raise
    except Exception as e:
        raise EngineUnavailableError(f"could not download DDColor '{model_id}': {e}") from e
    _report(on_progress, "loading_model", None)
    with _lock:
        if _resident is not None:
            _evict(torch)
        try:
            # The snapshot path names the exact revision (provenance). Load by
            # repo id, not by that local path: given a directory, the Hub mixin
            # looks only for model.safetensors, and these checkpoints ship
            # pytorch_model.bin. By id, offline, it resolves the cached files.
            model = model_cls.from_pretrained(repo_id, local_files_only=True)
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
