"""The B2 key layout, declared once. Everything lives under one app prefix:

    <p>grayscale/<filename>                         ingested original (never modified)
    <p>colorized/<batch_id>/<stem>.<jpg|png|webp>   colorized output, original resolution
    <p>comparisons/<batch_id>/<stem>.jpg            optional side-by-side comparison
    <p>manifests/<batch_id>.csv                     per-run manifest
    <p>batches/<batch_id>.json                      the Batch record
    <p>flags/was-color/<filename>                   marker: the original was a colour image

`<p>` is `settings.colorization_prefix` (default `colorization/`). Outputs are
keyed by batch, so re-running the same photos with another model keeps both
versions side by side.
"""

import re
import secrets
from datetime import UTC, datetime

from app.config import settings

_BATCH_ID_RE = re.compile(r"^b-\d{8}-\d{6}-[0-9a-f]{6}$")


def prefix() -> str:
    return settings.colorization_prefix


def grayscale_prefix() -> str:
    return f"{prefix()}grayscale/"


def colorized_prefix(batch_id: str) -> str:
    return f"{prefix()}colorized/{batch_id}/"


def comparisons_prefix(batch_id: str) -> str:
    return f"{prefix()}comparisons/{batch_id}/"


def manifest_key(batch_id: str) -> str:
    return f"{prefix()}manifests/{batch_id}.csv"


def was_color_prefix() -> str:
    return f"{prefix()}flags/was-color/"


def was_color_key(original_key: str) -> str:
    return f"{was_color_prefix()}{filename_of(original_key)}"


def filename_of(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def stem_of(key: str) -> str:
    name = filename_of(key)
    stem, dot, _ext = name.rpartition(".")
    return stem if dot and stem else name


def new_batch_id(now: datetime | None = None) -> str:
    """Sortable, unguessable id: `b-YYYYMMDD-HHMMSS-<6 hex>`."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"b-{stamp}-{secrets.token_hex(3)}"


def is_valid_batch_id(batch_id: str) -> bool:
    return bool(_BATCH_ID_RE.match(batch_id))


def is_original_key(key: str) -> bool:
    rest = key[len(grayscale_prefix()) :]
    return key.startswith(grayscale_prefix()) and bool(rest) and "/" not in rest


def output_keys(batch_id: str, original_keys: list[str], ext: str) -> dict[str, tuple[str, str]]:
    """Map each original to its (colorized_key, comparison_key) for one batch.

    Two originals sharing a stem (`a.png`, `a.tif`) get `a`, `a-2`, ... so no
    output overwrites another within a batch.
    """
    seen: dict[str, int] = {}
    result: dict[str, tuple[str, str]] = {}
    for key in original_keys:
        stem = stem_of(key)
        count = seen.get(stem, 0) + 1
        seen[stem] = count
        unique = stem if count == 1 else f"{stem}-{count}"
        result[key] = (
            f"{colorized_prefix(batch_id)}{unique}.{ext}",
            f"{comparisons_prefix(batch_id)}{unique}.jpg",
        )
    return result
