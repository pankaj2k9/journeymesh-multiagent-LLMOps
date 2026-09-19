"""The media library.

Uploading is gated on the ADMIN role - by a server-side dependency, not by
hiding a button. Reading one asset's metadata is open, because the files
themselves are public once they are on a published page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.config import get_settings
from app.core.constants import ROLE_ADMIN
from app.db.models import User
from app.media.images import MediaTooLarge
from app.schemas.media import (
    MediaAssetOut,
    MediaCategory,
    MediaListResponse,
    MediaUpdate,
)
from app.services.media_service import MediaService

router = APIRouter(prefix="/media", tags=["media"])


def media_service(session: Session = Depends(db_session)) -> MediaService:
    return MediaService(session)


@router.post(
    "",
    response_model=MediaAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image",
    description=(
        "The declared content type is ignored: the format is decided by the file's "
        "own magic bytes and confirmed by decoding it. SVG and HTML are refused "
        "because they can carry script and would be served from this origin. "
        "Metadata is stripped on re-encode, which matters because EXIF on a "
        "traveller's photograph routinely contains the coordinates of their home."
    ),
)
async def upload(
    file: UploadFile = File(...),
    category: MediaCategory = Form(default="blog"),
    alt_text: str = Form(default=""),
    title: str | None = Form(default=None),
    service: MediaService = Depends(media_service),
    user: User = Depends(require_role(ROLE_ADMIN)),
) -> MediaAssetOut:
    settings = get_settings()

    # Read with a ceiling rather than into memory unbounded: `UploadFile`
    # spools to disk, and a 4GB body would otherwise become a 4GB temp file
    # before any size check ran.
    payload = await file.read(settings.max_upload_bytes + 1)
    if len(payload) > settings.max_upload_bytes:
        raise MediaTooLarge(
            f"the upload exceeds the {settings.max_upload_bytes} byte limit"
        )

    return service.upload(
        payload,
        original_filename=file.filename or "upload",
        category=category,
        declared_type=file.content_type,
        alt_text=alt_text,
        title=title,
        uploaded_by=user.id,
    )


@router.get("", response_model=MediaListResponse, summary="Browse the media library")
def list_media(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: MediaCategory | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    service: MediaService = Depends(media_service),
    user: User = Depends(require_role(ROLE_ADMIN)),
) -> MediaListResponse:
    items, total = service.list(
        limit=limit, offset=offset, category=category, search=search
    )
    return MediaListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=MediaAssetOut, summary="One media asset")
def get_media(
    asset_id: str,
    service: MediaService = Depends(media_service),
    user: User = Depends(require_role(ROLE_ADMIN)),
) -> MediaAssetOut:
    return service.get(asset_id)


@router.patch(
    "/{asset_id}",
    response_model=MediaAssetOut,
    summary="Edit alt text or title",
    description=(
        "Only the descriptive fields are editable. The path, the bytes and the "
        "dimensions describe a file that already exists; replacing an image is a "
        "new upload."
    ),
)
def update_media(
    asset_id: str,
    payload: MediaUpdate,
    service: MediaService = Depends(media_service),
    user: User = Depends(require_role(ROLE_ADMIN)),
) -> MediaAssetOut:
    return service.update(asset_id, alt_text=payload.alt_text, title=payload.title)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an asset and its generated sizes",
    description=(
        "An image a published page still points at is refused unless `force` is "
        "set, because the alternative is an article quietly developing a broken "
        "image."
    ),
)
def delete_media(
    asset_id: str,
    force: bool = Query(default=False),
    service: MediaService = Depends(media_service),
    user: User = Depends(require_role(ROLE_ADMIN)),
) -> None:
    service.delete(asset_id, force=force)
