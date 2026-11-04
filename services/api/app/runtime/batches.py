"""Batch routes. Thin: validation lives in the Pydantic models, logic in service/.

Handlers are sync `def` so the blocking boto3 work runs in Starlette's
threadpool (see runtime/files.py). Colorization itself never runs on a request:
`run` only queues the batch for the background worker and returns.
"""

from fastapi import APIRouter, HTTPException

from app.service import batches as batch_service
from app.service import photos as photo_service
from app.service.batches import BatchError
from app.types import (
    Batch,
    BatchDetail,
    ColorizationStats,
    CreateBatchRequest,
    DeleteBatchResponse,
    FileUrlResponse,
    UpdateBatchRequest,
)

router = APIRouter()


def _http(error: BatchError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/batches", response_model=list[Batch])
def list_batches_endpoint(limit: int = 50):
    try:
        return batch_service.list_batches(limit=limit)
    except BatchError as e:
        raise _http(e) from None


@router.post("/batches", response_model=Batch, status_code=201)
def create_batch_endpoint(req: CreateBatchRequest):
    try:
        return batch_service.create_batch(req)
    except BatchError as e:
        raise _http(e) from None


@router.get("/batches/stats", response_model=ColorizationStats)
def batch_stats_endpoint():
    return photo_service.get_stats()


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def get_batch_endpoint(batch_id: str):
    try:
        return batch_service.get_batch(batch_id)
    except BatchError as e:
        raise _http(e) from None


@router.patch("/batches/{batch_id}", response_model=Batch)
def update_batch_endpoint(batch_id: str, req: UpdateBatchRequest):
    try:
        return batch_service.update_batch(batch_id, req)
    except BatchError as e:
        raise _http(e) from None


@router.delete("/batches/{batch_id}", response_model=DeleteBatchResponse)
def delete_batch_endpoint(batch_id: str):
    """Delete the batch's colorized outputs, comparisons, manifest and record.

    Grayscale originals are never deleted.
    """
    try:
        return batch_service.delete_batch(batch_id)
    except BatchError as e:
        raise _http(e) from None


@router.post("/batches/{batch_id}/run", response_model=Batch)
def run_batch_endpoint(batch_id: str):
    """Queue a batch for colorization (503 with the install command if DDColor is missing)."""
    try:
        return batch_service.run_batch(batch_id)
    except BatchError as e:
        raise _http(e) from None


@router.get("/batches/{batch_id}/manifest/download", response_model=FileUrlResponse)
def manifest_download_endpoint(batch_id: str):
    try:
        return FileUrlResponse(url=batch_service.manifest_download_url(batch_id))
    except BatchError as e:
        raise _http(e) from None
