"""Colorization batches: the primary entity.

A batch is one colorization run over a chosen set of grayscale originals with a
fixed model configuration. It owns its colorized outputs, comparison images and
manifest CSV. The configuration is immutable after creation because it defines
what the outputs and the manifest mean; only name and description are editable.
"""

from datetime import datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field

from app.types.base import ResponseModel


class ModelId(StrEnum):
    """DDColor checkpoints published on the Hugging Face Hub (`piddnad/<id>`)."""

    ddcolor_modelscope = "ddcolor_modelscope"
    ddcolor_paper = "ddcolor_paper"
    ddcolor_artistic = "ddcolor_artistic"
    ddcolor_paper_tiny = "ddcolor_paper_tiny"


class InputSize(IntEnum):
    """Square resolution the model predicts colour at (output keeps the original size)."""

    s256 = 256
    s512 = 512


class OutputFormat(StrEnum):
    jpeg = "jpeg"
    png = "png"
    webp = "webp"


class BatchStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    running = "running"
    done = "done"
    partial = "partial"
    failed = "failed"
    interrupted = "interrupted"


class ItemStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class BatchItemRecord(BaseModel):
    """One photo inside a stored batch record (no presigned URLs)."""

    original_key: str
    colorized_key: str | None = None
    comparison_key: str | None = None
    status: ItemStatus = ItemStatus.pending
    error: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    original_bytes: int | None = None
    colorized_bytes: int | None = None
    comparison_bytes: int | None = None
    processed_at: datetime | None = None


class Batch(ResponseModel):
    """A colorization run: configuration, status and byte counts."""

    batch_id: str
    name: str
    description: str | None = None
    model_id: ModelId
    input_size: InputSize
    output_format: OutputFormat
    make_comparisons: bool
    status: BatchStatus
    photo_count: int
    done_count: int
    failed_count: int
    original_bytes: int = Field(description="Bytes of the grayscale originals in this batch.")
    derived_bytes: int = Field(
        description="Bytes this batch wrote: colorized outputs, comparisons and its manifest."
    )
    manifest_key: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BatchRecord(Batch):
    """The JSON stored at `colorization/batches/<batch_id>.json`.

    Adds the per-photo items and the resolved model version (provenance).
    """

    model_version: str | None = Field(
        default=None, description="`<model_id>@<Hugging Face revision sha>` of the last run."
    )
    items: list[BatchItemRecord] = Field(default_factory=list)


class BatchItem(ResponseModel):
    """One photo in a batch, with short-lived presigned URLs for viewing."""

    original_key: str
    colorized_key: str | None = None
    comparison_key: str | None = None
    status: ItemStatus
    error: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    original_url: str = Field(description="Inline presigned GET for the grayscale original.")
    colorized_url: str | None = None
    comparison_url: str | None = None


class BatchDetail(Batch):
    """A batch plus every item, for the detail page."""

    model_version: str | None = None
    items: list[BatchItem]


class CreateBatchRequest(BaseModel):
    """Create a batch. Defaults mirror the create form's suggested values."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    source_keys: list[str] = Field(
        default_factory=list,
        description="Original keys under the grayscale/ prefix. Ignored when all_unprocessed is true.",
    )
    all_unprocessed: bool = Field(
        default=False, description="Use every original that no batch has colorized yet."
    )
    model_id: ModelId = ModelId.ddcolor_paper_tiny
    input_size: InputSize = InputSize.s512
    output_format: OutputFormat = OutputFormat.jpeg
    make_comparisons: bool = True
    run_now: bool = True


class UpdateBatchRequest(BaseModel):
    """Only the descriptive fields are editable; the configuration is immutable."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class DeleteBatchResponse(ResponseModel):
    """A deleted batch. Grayscale originals are never deleted."""

    batch_id: str
    deleted_objects: int


class ColorizationStats(ResponseModel):
    """Dashboard aggregates, headlined by the write-amplification ratio."""

    photos_ingested: int
    photos_colorized: int
    batches_total: int
    grayscale_bytes: int
    derived_bytes: int = Field(
        description="Colorized outputs + comparison images + manifest CSVs under the app prefix."
    )
    amplification_ratio: float = Field(
        description="(grayscale_bytes + derived_bytes) / grayscale_bytes: stored bytes per ingested byte."
    )
    recent_batches: list[Batch]
