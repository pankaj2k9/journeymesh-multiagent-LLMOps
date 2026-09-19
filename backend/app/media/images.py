"""Validating and processing an uploaded image.

Everything here treats the upload as hostile, because it is: this is the one
endpoint where a stranger hands the server a file and asks it to keep it.

  * **The declared type is ignored.** ``Content-Type`` is whatever the client
    chose to send, so the format is decided by the file's own magic bytes and
    then confirmed by actually decoding it. A ``.png`` that does not decode as
    an image never reaches disk.
  * **SVG is refused outright.** It is not really an image to a browser; it is
    a document that can carry script, and serving one from our own origin
    would be stored XSS. The logos this project ships are developer assets in
    the build, not uploads.
  * **Decompression bombs are capped.** A 200-megapixel PNG is a few kilobytes
    on disk and gigabytes once decoded, which is a denial of service that
    looks like a small file.
  * **Metadata is stripped.** Re-encoding drops EXIF, and EXIF on a traveller's
    photograph routinely contains the GPS coordinates of their home.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import TravelCrewError
from app.observability.logging import get_logger

logger = get_logger("journeymesh.media.images")


class UnsupportedMedia(TravelCrewError):
    status_code = 415
    code = "unsupported_media_type"
    safe_message = "That file type is not accepted."


class MediaTooLarge(TravelCrewError):
    status_code = 413
    code = "media_too_large"
    safe_message = "That file is larger than the upload limit."


class CorruptMedia(TravelCrewError):
    status_code = 422
    code = "corrupt_media"
    safe_message = "That file could not be read as an image."


# Magic-byte signatures for the formats accepted. The declared MIME type is
# never consulted; this table is.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

ACCEPTED_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}
)

# Formats that are refused no matter what they claim to be. SVG and anything
# that is markup rather than pixels.
REFUSED_MIME_TYPES = frozenset(
    {"image/svg+xml", "text/html", "application/xml", "text/xml"}
)

# Longest edge for each generated size. A blog hero does not need the 6000px
# original a phone produced, and serving one is most of a page's weight.
DERIVATIVE_SIZES: dict[str, int] = {
    "thumbnail": 200,
    "small": 480,
    "medium": 1024,
    "large": 1920,
}

# What derivatives are encoded as. WebP is universally supported now and is
# meaningfully smaller than JPEG at the same perceptual quality.
DERIVATIVE_FORMAT = "WEBP"
DERIVATIVE_EXTENSION = "webp"
DERIVATIVE_QUALITY = 82


@dataclass
class ProcessedImage:
    """The result of accepting one upload."""

    mime_type: str
    extension: str
    width: int
    height: int
    primary: bytes
    derivatives: dict[str, bytes] = field(default_factory=dict)
    dimensions: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def file_size(self) -> int:
        return len(self.primary)


def sniff_mime(payload: bytes) -> str | None:
    """The real format, from the file's own first bytes."""
    for signature, mime in _SIGNATURES:
        if payload.startswith(signature):
            return mime
    # RIFF....WEBP
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    # ISO-BMFF box with an AVIF brand.
    if payload[4:8] == b"ftyp" and payload[8:12] in (b"avif", b"avis"):
        return "image/avif"
    # Markup, recognised explicitly so the refusal can say *why* rather than
    # falling through to a generic "not an image". A fixed-width slice cannot
    # match prefixes of different lengths, so this compares by prefix.
    head = payload.lstrip()[:64].lower()
    if head.startswith((b"<?xml", b"<svg")):
        return "image/svg+xml"
    if head.startswith((b"<!doctype html", b"<html")):
        return "text/html"
    return None


def validate(payload: bytes, *, declared_type: str | None = None) -> str:
    """Decide whether this upload is acceptable, and say what it actually is.

    ``declared_type`` is accepted only to be *compared* with reality; it never
    decides anything.
    """
    settings = get_settings()

    if not payload:
        raise CorruptMedia("the uploaded file was empty")
    if len(payload) > settings.max_upload_bytes:
        raise MediaTooLarge(
            f"the file is {len(payload)} bytes; the limit is {settings.max_upload_bytes}"
        )

    actual = sniff_mime(payload)
    if actual is None:
        raise UnsupportedMedia("that file is not an image format this application accepts")
    if actual in REFUSED_MIME_TYPES:
        # Named separately from "unknown" so the log says why.
        raise UnsupportedMedia(
            f"{actual} is refused: it can carry script and would be served from this origin"
        )
    if actual not in ACCEPTED_MIME_TYPES:
        raise UnsupportedMedia(f"{actual} is not an accepted image type")

    if declared_type and declared_type.split(";")[0].strip().lower() != actual:
        # Not fatal - browsers get this wrong innocently - but worth seeing,
        # because deliberate mismatch is what an attempt looks like.
        logger.info(
            "upload content-type did not match its contents",
            extra={"declared": declared_type, "actual": actual},
        )
    return actual


def process(
    payload: bytes,
    *,
    declared_type: str | None = None,
    generate_derivatives: bool = True,
) -> ProcessedImage:
    """Validate, decode, normalise and re-encode an upload."""
    settings = get_settings()
    mime = validate(payload, declared_type=declared_type)

    # Pillow's own bomb guard, set from configuration rather than left at its
    # library default.
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        try:
            with Image.open(io.BytesIO(payload)) as probe:
                probe.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CorruptMedia("that file could not be decoded as an image") from exc

        # `verify()` leaves the file unusable, so it is reopened to work on.
        with Image.open(io.BytesIO(payload)) as image:
            if image.width > settings.max_image_dimension or (
                image.height > settings.max_image_dimension
            ):
                raise MediaTooLarge(
                    f"the image is {image.width}x{image.height}; the limit is "
                    f"{settings.max_image_dimension}px on either edge"
                )

            # Honour the EXIF orientation flag before discarding EXIF, so a
            # phone photograph is not stored on its side.
            oriented = ImageOps.exif_transpose(image)
            animated = getattr(image, "is_animated", False)

            if animated:
                # An animated GIF survives as itself: re-encoding it to a still
                # WebP would silently destroy what it was.
                return ProcessedImage(
                    mime_type=mime,
                    extension="gif",
                    width=image.width,
                    height=image.height,
                    primary=payload,
                )

            flattened = _flatten(oriented)
            primary = _encode(flattened)

            derivatives: dict[str, bytes] = {}
            dimensions: dict[str, tuple[int, int]] = {}
            if generate_derivatives:
                for name, edge in DERIVATIVE_SIZES.items():
                    # Never upscale: a 300px logo has no business becoming a
                    # blurry 1920px "large".
                    if max(flattened.width, flattened.height) <= edge and name != "thumbnail":
                        continue
                    resized = _fit(flattened, edge)
                    derivatives[name] = _encode(resized)
                    dimensions[name] = (resized.width, resized.height)

            return ProcessedImage(
                mime_type=f"image/{DERIVATIVE_EXTENSION}",
                extension=DERIVATIVE_EXTENSION,
                width=flattened.width,
                height=flattened.height,
                primary=primary,
                derivatives=derivatives,
                dimensions=dimensions,
            )
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def _flatten(image: Any) -> Any:
    """Normalise colour mode, keeping transparency where it exists."""
    if image.mode in ("RGBA", "LA"):
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA" if "transparency" in image.info else "RGB")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _fit(image: Any, edge: int) -> Any:
    """Scale so the longest edge is ``edge``, preserving aspect ratio."""
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return copy


def _encode(image: Any) -> bytes:
    buffer = io.BytesIO()
    # `save` writes no EXIF unless asked, so the GPS coordinates in a
    # traveller's photograph do not survive the upload.
    image.save(buffer, format=DERIVATIVE_FORMAT, quality=DERIVATIVE_QUALITY, method=4)
    return buffer.getvalue()


def derivative_path(relative_path: str, size: str) -> str:
    """Where a generated size lives, beside its original.

    ``blog/2026/09/abc-guide.webp`` -> ``blog/2026/09/abc-guide@small.webp``
    """
    if "." not in relative_path:
        return f"{relative_path}@{size}"
    stem, _, suffix = relative_path.rpartition(".")
    return f"{stem}@{size}.{suffix}"


__all__ = [
    "ACCEPTED_MIME_TYPES",
    "CorruptMedia",
    "DERIVATIVE_EXTENSION",
    "DERIVATIVE_SIZES",
    "MediaTooLarge",
    "ProcessedImage",
    "UnsupportedMedia",
    "derivative_path",
    "process",
    "sniff_mime",
    "validate",
]
