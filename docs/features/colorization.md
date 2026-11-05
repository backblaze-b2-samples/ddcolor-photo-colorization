<!-- last_verified: 2026-11-04 -->
# Feature: Colorization

## Purpose
Turn each grayscale original into a full-colour reconstruction at its original resolution with DDColor running locally, with no external API and no second key.

## Used By
- UI: indirectly, through [Batches](batches.md) (run / re-run) and the galleries
- API: `POST /batches` with `run_now`, `POST /batches/{batch_id}/run`
- Job: `service/colorize_runner.py` (one background thread)

## Core Functions
- `services/api/app/repo/ddcolor.py`: `ml_available`, `resolve_device`, `load_model`, `colorize`, `EngineUnavailableError`, `INSTALL_HINT`
- `services/api/app/repo/imaging.py`: `open_image` (EXIF orientation, 16-bit TIFF scaling, alpha flattening, pixel ceiling), `to_grayscale_rgb`, `encode`
- `services/api/app/repo/comparison.py`: `build_comparison`
- `services/api/scripts/install_ml.sh`: the `pnpm setup:ml` installer

## Canonical Files
- Engine adapter: `services/api/app/repo/ddcolor.py`
- Optional dependency set: `services/api/requirements-ml.txt`

## Inputs
- An original's bytes from `colorization/grayscale/` (JPEG, PNG, TIFF, WebP, BMP)
- Batch configuration: `model_id`, `input_size` (256 or 512), `output_format`, `make_comparisons`
- Environment: `DDCOLOR_DEVICE` (`auto` default, `cpu`, `cuda`, `mps`), `HF_HOME` (weights cache), `MAX_PHOTO_PIXELS` (60,000,000)

## Outputs
- Colorized image with the original's exact width and height, encoded as JPEG (quality 92), PNG or WebP (quality 90)
- Optional comparison JPEG: original and colorized side by side (each panel at most 1024 px high) above a caption naming the model and input size
- `model_version` = `<model_id>@<revision sha>` of the loaded checkpoint, recorded on the batch and in every manifest row

## Flow
- Decode with Pillow, apply EXIF orientation, desaturate to luminance (so a colour upload is treated as its grayscale version), keep 3 channels
- `load_model`: resolve the device (first of CUDA, Apple MPS, CPU for `auto`; an unavailable explicit choice falls back to CPU with a warning), reuse `piddnad/<model_id>` straight from the local Hub cache when its config and weights are already there (no network, no download stage), otherwise download it over plain HTTPS (Xet is disabled by default via `HF_HUB_DISABLE_XET=1`, because Xet writes the blob in bursts and the cache size would stop tracking live bytes), keep it as the single resident model
- DDColor's own `ColorizationPipeline`: convert to Lab, run the network on the `L` channel resized to `input_size` x `input_size`, predict the `ab` channels, resize `ab` back to the original size, recombine with the original full-resolution `L`, convert to RGB
- Encode, `put_object`, optional comparison `put_object`

## Install
- `pnpm setup:ml` runs `services/api/scripts/install_ml.sh`: `pip install -r requirements-ml.txt` (torch 2.6-2.8, torchvision, timm, opencv-python-headless 4.x, numpy < 2.3, huggingface_hub, plus setuptools/wheel/pyyaml/tqdm), then DDColor itself from `github.com/piddnad/DDColor` pinned to commit `2adb63f`, with `--no-deps --no-build-isolation`
- Why not a plain `pip install`: DDColor's `setup.py` imports torch at build time, and its `install_requires` pins `numpy==1.24.3` (no Python 3.12 wheel) and training-only packages
- On Linux the installer uses CPU torch wheels unless `TORCH_INDEX_URL` points at a CUDA index
- MPS runs with `PYTORCH_ENABLE_MPS_FALLBACK=1`, so an op MPS lacks falls back to CPU instead of failing

## Models
| `model_id` | Encoder | Weights | Notes |
| --- | --- | --- | --- |
| `ddcolor_artistic` | ConvNeXt-L | 912 MB | default; often the most saturated, but some portraits come out muted or sepia (try ModelScope via "Colorize again with another model") |
| `ddcolor_modelscope` | ConvNeXt-L | 912 MB | upstream demo default |
| `ddcolor_paper` | ConvNeXt-L | 912 MB | ICCV 2023 paper checkpoint |
| `ddcolor_paper_tiny` | ConvNeXt-T | 220 MB | fastest on CPU; often nearly grayscale output on portraits and street scenes |

## Edge Cases
- ML stack missing -> 503 with the install command; core API keeps working
- Weights unreachable (offline, Hub down) -> every item `failed` with the load error
- Weight download stalls (no new bytes in the Hub cache for `MODEL_DOWNLOAD_STALL_SECONDS`, default 120) -> every item `failed` with a "stalled" error; the abandoned download thread never blocks the worker, and a re-run resumes the partial download
- While a model downloads or loads, the queued batch carries `stage` (`downloading_model` / `loading_model`) and `model_download_bytes`, polled every second from the bytes in the Hub cache; the batch page shows it as text and as a determinate bar (bytes over the checkpoint's approximate size)
- Photo over `MAX_PHOTO_PIXELS` or undecodable -> that item `failed`
- 16-bit grayscale TIFF -> scaled to 8 bits, not clipped
- Transparent PNG -> flattened onto white
- Switching model between batches -> previous model evicted and device cache freed before loading

## UX States
- See [Batches](batches.md): per-item `running`, `done` with before/after, `failed` with its error

## Verification
- Test files: `services/api/tests/test_batches.py` (device policy, engine-failure path, 503 path, runner with the model call replaced), `services/api/tests/test_colorization_assets.py` (imaging, comparison), `services/api/tests/test_structure.py` (`test_ml_stack_only_in_ddcolor_adapter`, `test_ml_adapter_imports_the_stack_lazily`)
- `pnpm verify` runs without the ML stack by design; real inference is exercised at run time
- Manual real-run check: `pnpm setup:ml && pnpm seed:demo`, create a batch with defaults, confirm every item `done` with the original dimensions and a manifest whose `model_version` carries a revision sha
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: tests green; real run completes on CPU or MPS

## Related Docs
- [DDColor upstream](https://github.com/piddnad/DDColor) (Apache-2.0)
- [Batches](batches.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/app-workflows.md](../app-workflows.md)
