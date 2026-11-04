"""Per-batch manifest CSV: one row per photo, the provenance record of a run."""

import csv
import io
from datetime import datetime

MANIFEST_COLUMNS = (
    "original_key",
    "colorized_key",
    "comparison_key",
    "model_id",
    "model_version",
    "input_size",
    "output_format",
    "width",
    "height",
    "original_bytes",
    "colorized_bytes",
    "duration_ms",
    "status",
    "error",
    "processed_at",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def build_manifest(rows: list[dict]) -> bytes:
    """Render `rows` (dicts keyed by MANIFEST_COLUMNS) as UTF-8 CSV bytes.

    Unknown keys are rejected so a renamed field cannot silently drop a column.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        unknown = set(row) - set(MANIFEST_COLUMNS)
        if unknown:
            raise ValueError(f"unknown manifest columns: {sorted(unknown)}")
        writer.writerow({col: _cell(row.get(col)) for col in MANIFEST_COLUMNS})
    return buf.getvalue().encode("utf-8")
