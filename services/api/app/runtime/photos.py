"""Photo Library routes, scoped to the app's grayscale originals."""

from fastapi import APIRouter, HTTPException

from app.service import photos as photo_service
from app.service.files import FileKeyError, FileNotFoundServiceError
from app.types import PhotoDetail, PhotoPage

router = APIRouter()


@router.get("/photos", response_model=PhotoPage)
def list_photos_endpoint(limit: int = 48, cursor: str | None = None):
    try:
        return photo_service.list_photos(limit=limit, cursor=cursor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/photos-by-key/detail", response_model=PhotoDetail)
def photo_detail_endpoint(key: str):
    try:
        return photo_service.get_photo_detail(key)
    except FileKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except FileNotFoundServiceError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
