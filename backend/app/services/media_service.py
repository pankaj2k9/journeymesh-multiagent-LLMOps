"""Accepting, recording and removing uploaded media.

Ties the three pieces together: ``media.images`` decides whether the bytes are
acceptable and produces the derivatives, ``media.storage`` puts them somewhere
durable, and this service records what happened.

The order matters and is deliberate: **validate, then store, then record**. A
row is only written once the bytes are safely on disk, so the library never
lists an asset whose file does not exist. The reverse - recording first - is
how a media library fills up with broken images after one failed write.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import TravelCrewError
from app.db.models import MediaAsset
from app.media import images, storage
from app.observability import metrics
from app.observability.logging import get_logger
from app.schemas.media import DerivativeOut, MediaAssetOut

logger = get_logger("journeymesh.services.media")


class MediaNotFound(TravelCrewError):
    status_code = 404
    code = "media_not_found"
    safe_message = "That media file could not be found."


class MediaInUse(TravelCrewError):
    """Refuses to delete an image a published page still points at."""

    status_code = 409
    code = "media_in_use"
    safe_message = "That image is still used by a page and was not deleted."


class MediaService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.storage = storage.get_storage()

    # ---- upload ----------------------------------------------------------
    def upload(
        self,
        payload: bytes,
        *,
        original_filename: str,
        category: str = "blog",
        declared_type: str | None = None,
        alt_text: str = "",
        title: str | None = None,
        uploaded_by: str | None = None,
    ) -> MediaAssetOut:
        """Validate, store and record one upload."""
        processed = images.process(payload, declared_type=declared_type)

        relative_path = storage.build_relative_path(
            category=category,
            original_filename=original_filename,
            extension=processed.extension,
        )
        self.storage.save(relative_path, processed.primary)

        derivatives: dict[str, Any] = {}
        for name, data in processed.derivatives.items():
            child_path = images.derivative_path(relative_path, name)
            self.storage.save(child_path, data)
            width, height = processed.dimensions[name]
            derivatives[name] = {"path": child_path, "width": width, "height": height}

        asset = MediaAsset(
            relative_path=relative_path,
            filename=relative_path.rsplit("/", 1)[-1],
            # Kept for display. Never used to build a path.
            original_filename=(original_filename or "")[:255],
            category=category,
            mime_type=processed.mime_type,
            file_size=processed.file_size,
            width=processed.width,
            height=processed.height,
            alt_text=(alt_text or "")[:300],
            title=title,
            derivatives=derivatives,
            uploaded_by=uploaded_by,
        )
        self.session.add(asset)
        self.session.flush()

        metrics.increment("media.uploaded", category=category)
        logger.info(
            "media uploaded",
            extra={
                "category": category,
                "bytes": processed.file_size,
                "derivatives": len(derivatives),
            },
        )
        return self.to_out(asset)

    # ---- reads -----------------------------------------------------------
    def get(self, asset_id: str) -> MediaAssetOut:
        return self.to_out(self._row(asset_id))

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        category: str | None = None,
        search: str | None = None,
    ) -> tuple[list[MediaAssetOut], int]:
        stmt = select(MediaAsset)
        count_stmt = select(func.count(MediaAsset.id))

        if category:
            stmt = stmt.where(MediaAsset.category == category)
            count_stmt = count_stmt.where(MediaAsset.category == category)
        if search:
            pattern = f"%{search.strip().lower()}%"
            condition = func.lower(MediaAsset.original_filename).like(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(MediaAsset.created_at.desc()).limit(limit).offset(offset)
        rows = list(self.session.scalars(stmt))
        total = int(self.session.scalar(count_stmt) or 0)
        return [self.to_out(row) for row in rows], total

    # ---- writes ----------------------------------------------------------
    def update(
        self, asset_id: str, *, alt_text: str | None = None, title: str | None = None
    ) -> MediaAssetOut:
        asset = self._row(asset_id)
        if alt_text is not None:
            asset.alt_text = alt_text[:300]
        if title is not None:
            asset.title = title[:200]
        self.session.flush()
        return self.to_out(asset)

    def delete(self, asset_id: str, *, force: bool = False) -> None:
        """Remove an asset and its derivatives.

        An asset a page still points at is refused unless the administrator
        insists, because the alternative is a published article quietly
        developing a broken image.
        """
        asset = self._row(asset_id)
        if asset.usage_count > 0 and not force:
            raise MediaInUse(
                f"this image is used in {asset.usage_count} place(s); "
                "detach it first or delete it explicitly"
            )

        for child in (asset.derivatives or {}).values():
            path = child.get("path") if isinstance(child, dict) else None
            if path:
                self.storage.delete(path)
        self.storage.delete(asset.relative_path)

        self.session.delete(asset)
        self.session.flush()
        metrics.increment("media.deleted")

    def mark_used(self, asset_id: str, delta: int = 1) -> None:
        """Track how many pages point at an asset, so deletion can warn."""
        asset = self.session.get(MediaAsset, asset_id)
        if asset is None:
            return
        asset.usage_count = max(0, asset.usage_count + delta)
        self.session.flush()

    # ---- internals -------------------------------------------------------
    def _row(self, asset_id: str) -> MediaAsset:
        asset = self.session.get(MediaAsset, asset_id)
        if asset is None:
            raise MediaNotFound(f"media asset {asset_id} does not exist")
        return asset

    def to_out(self, asset: MediaAsset) -> MediaAssetOut:
        derivatives = {}
        for name, child in (asset.derivatives or {}).items():
            if not isinstance(child, dict) or "path" not in child:
                continue
            derivatives[name] = DerivativeOut(
                path=child["path"],
                url=self.storage.get_url(child["path"]),
                width=int(child.get("width") or 0),
                height=int(child.get("height") or 0),
            )

        return MediaAssetOut(
            id=asset.id,
            relative_path=asset.relative_path,
            url=self.storage.get_url(asset.relative_path),
            filename=asset.filename,
            original_filename=asset.original_filename,
            category=asset.category,
            mime_type=asset.mime_type,
            file_size=asset.file_size,
            width=asset.width,
            height=asset.height,
            alt_text=asset.alt_text,
            title=asset.title,
            derivatives=derivatives,
            uploaded_by=asset.uploaded_by,
            usage_count=asset.usage_count,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )


__all__ = ["MediaInUse", "MediaNotFound", "MediaService"]
