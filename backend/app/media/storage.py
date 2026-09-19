"""Where uploaded files live.

The abstraction exists for one reason stated plainly in the brief: today this
deploys to a VPS with a local directory, and later it may deploy to S3, R2 or
GCS. Everything above this module - the CMS, the admin library, the blog - must
not care, so nothing above it ever sees a filesystem path.

Two rules the implementations share.

**A stored path is generated, never supplied.** The original filename is used
only to derive a readable slug; the path itself is built from a UUID, a
category and a date. A user-supplied name reaching ``os.path.join`` is how an
upload form becomes arbitrary file write, and no amount of sanitising a string
is as safe as never using it.

**A relative path is the only identity.** The database stores
``blog/2026/09/6f28ae89-barcelona-guide.webp`` and nothing else. The public URL
is derived at read time, so moving from a local disk to a CDN changes one
configuration value rather than every row.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger("journeymesh.media.storage")

# Categories an upload can belong to. A closed set, because the category
# becomes a directory name and an open one would be a path-traversal surface.
CATEGORIES = ("blog", "destinations", "marketing", "users", "trips")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 60


class MediaStorageError(RuntimeError):
    """Raised when a file cannot be stored or removed."""


def slugify(value: str) -> str:
    """A safe, readable stem derived from a filename.

    Decomposed to ASCII, lower-cased, and stripped of everything that is not a
    letter or a digit. What survives is used for readability only - the UUID in
    front of it is what makes the name unique and the path unguessable.
    """
    normalised = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    stem = PurePosixPath(ascii_only).stem.lower()
    slug = _SLUG_STRIP.sub("-", stem).strip("-")
    return (slug[:_MAX_SLUG].rstrip("-")) or "file"


def build_relative_path(
    *,
    category: str,
    original_filename: str,
    extension: str,
    now: datetime | None = None,
    identifier: str | None = None,
) -> str:
    """Compose the stored path. Never derived from user input alone.

    ``blog/2026/09/6f28ae89-barcelona-family-guide.webp``

    Partitioned by year and month so a directory listing stays usable after a
    few thousand uploads, and so a media backup can be taken incrementally.
    """
    if category not in CATEGORIES:
        raise MediaStorageError(f"unknown media category: {category!r}")

    stamp = now or datetime.now(timezone.utc)
    short_id = (identifier or uuid.uuid4().hex)[:8]
    suffix = extension.lower().lstrip(".")
    if not suffix.isalnum():
        raise MediaStorageError(f"unsafe file extension: {extension!r}")

    name = f"{short_id}-{slugify(original_filename)}.{suffix}"
    return f"{category}/{stamp:%Y}/{stamp:%m}/{name}"


class MediaStorage(ABC):
    """The contract the CMS is written against."""

    @abstractmethod
    def save(self, relative_path: str, data: bytes | BinaryIO) -> str:
        """Store bytes at this path and return the path actually used."""

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """Remove a file. Returns False when it was already gone."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        ...

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """The public URL for a stored file."""

    @abstractmethod
    def open(self, relative_path: str) -> bytes:
        ...


class LocalMediaStorage(MediaStorage):
    """Files on a persistent directory, served by the application.

    The root must be a volume that survives deployment. In production that is a
    named Docker volume mounted at ``/app/storage/media``; on a laptop it is a
    directory under the project. Putting it anywhere inside the built image
    would mean every deployment silently deleted every uploaded image, which is
    the exact failure this design is here to prevent.
    """

    def __init__(self, root: Path | str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.media_root).resolve()
        self.base_url = (base_url or settings.media_base_url).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- the guard every method goes through ----------------------------
    def _resolve(self, relative_path: str) -> Path:
        """Turn a stored path into an absolute one, refusing to escape the root.

        Belt and braces: paths are generated rather than supplied, so a
        traversal should be impossible already. This is the check that makes
        that a property of the system rather than of the caller's discipline.
        """
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise MediaStorageError(
                f"refusing to touch a path outside the media root: {relative_path!r}"
            )
        return candidate

    def save(self, relative_path: str, data: bytes | BinaryIO) -> str:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = data if isinstance(data, bytes) else data.read()

        # Write to a temporary file and rename, so a crash mid-write cannot
        # leave a half-written image being served to visitors.
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(payload)
        temporary.replace(target)

        logger.info(
            "media stored",
            extra={"path": relative_path, "bytes": len(payload)},
        )
        return relative_path

    def delete(self, relative_path: str) -> bool:
        target = self._resolve(relative_path)
        if not target.is_file():
            return False
        target.unlink()
        return True

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).is_file()

    def open(self, relative_path: str) -> bytes:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise MediaStorageError(f"no such media file: {relative_path}")
        return target.read_bytes()

    def get_url(self, relative_path: str) -> str:
        return f"{self.base_url}/{relative_path.lstrip('/')}"


_storage: MediaStorage | None = None


def get_storage() -> MediaStorage:
    """The configured backend.

    ``MEDIA_STORAGE_DRIVER=local`` today. An S3 or R2 driver registers here and
    nothing above this module changes.
    """
    global _storage
    if _storage is None:
        settings = get_settings()
        driver = settings.media_storage_driver.lower()
        if driver != "local":
            raise MediaStorageError(
                f"unknown media storage driver {driver!r}; only 'local' is implemented"
            )
        _storage = LocalMediaStorage()
    return _storage


def reset_storage() -> None:
    """Drop the cached backend. Used by tests that swap the root."""
    global _storage
    _storage = None


__all__ = [
    "CATEGORIES",
    "LocalMediaStorage",
    "MediaStorage",
    "MediaStorageError",
    "build_relative_path",
    "get_storage",
    "reset_storage",
    "slugify",
]
