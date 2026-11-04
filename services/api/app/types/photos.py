"""Photo Library: grayscale originals and their colorized versions."""

from datetime import datetime

from pydantic import Field

from app.types.base import ResponseModel
from app.types.batches import InputSize, ModelId


class Photo(ResponseModel):
    """One ingested original and a pointer to its latest colorized version."""

    key: str
    filename: str
    size: int
    last_modified: datetime
    was_color: bool = Field(
        description="True when the ingest check found a colour image; it is desaturated before inference."
    )
    colorized_versions: int
    original_url: str = Field(description="Inline presigned GET for the original.")
    colorized_url: str | None = Field(
        default=None, description="Inline presigned GET for the latest colorized version."
    )


class PhotoPage(ResponseModel):
    items: list[Photo]
    next_cursor: str | None = None


class PhotoVersion(ResponseModel):
    """One colorized version of an original, produced by one batch."""

    batch_id: str
    batch_name: str
    model_id: ModelId
    input_size: InputSize
    colorized_key: str
    comparison_key: str | None = None
    size: int
    processed_at: datetime | None = None
    colorized_url: str
    comparison_url: str | None = None
    download_url: str = Field(description="Attachment presigned GET for the colorized file.")


class PhotoDetail(Photo):
    versions: list[PhotoVersion]
