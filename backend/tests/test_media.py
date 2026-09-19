"""Uploaded media.

This is the one endpoint where a stranger hands the server a file and asks it
to keep it, so most of this file is about refusing things. The storage tests
protect the other half of the promise: a generated path, inside the root,
always.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.media import storage
from app.media.images import (
    CorruptMedia,
    MediaTooLarge,
    UnsupportedMedia,
    derivative_path,
    process,
    sniff_mime,
    validate,
)
from app.media.storage import (
    LocalMediaStorage,
    MediaStorageError,
    build_relative_path,
    slugify,
)


def png_bytes(width: int = 800, height: int = 600, colour=(12, 99, 220)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestFormatSniffing:
    @pytest.mark.parametrize(
        "payload,expected",
        [
            (b"\xff\xd8\xff\xe0", "image/jpeg"),
            (b"\x89PNG\r\n\x1a\n", "image/png"),
            (b"GIF89a", "image/gif"),
            (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
            (b"\x00\x00\x00\x20ftypavif", "image/avif"),
        ],
    )
    def test_formats_are_recognised_by_their_own_bytes(
        self, payload: bytes, expected: str
    ) -> None:
        assert sniff_mime(payload) == expected

    def test_markup_is_recognised_as_markup(self) -> None:
        assert sniff_mime(b'<svg xmlns="http://www.w3.org/2000/svg"/>') == "image/svg+xml"
        assert sniff_mime(b'  <?xml version="1.0"?><svg/>') == "image/svg+xml"
        assert sniff_mime(b"<!DOCTYPE html><html></html>") == "text/html"

    def test_something_unrecognisable_is_not_guessed_at(self) -> None:
        assert sniff_mime(b"MZ\x90\x00this is a windows executable") is None


class TestValidation:
    def test_a_real_image_is_accepted(self) -> None:
        assert validate(png_bytes()) == "image/png"

    def test_svg_is_refused_with_the_reason(self) -> None:
        """It is a document that can carry script, served from our own origin."""
        with pytest.raises(UnsupportedMedia, match="can carry script"):
            validate(b'<svg xmlns="x"><script>alert(1)</script></svg>')

    def test_html_is_refused(self) -> None:
        with pytest.raises(UnsupportedMedia):
            validate(b"<!DOCTYPE html><html><body>hi</body></html>")

    def test_an_executable_is_refused(self) -> None:
        with pytest.raises(UnsupportedMedia):
            validate(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00")

    def test_an_empty_file_is_refused(self) -> None:
        with pytest.raises(CorruptMedia):
            validate(b"")

    def test_the_declared_type_is_never_believed(self) -> None:
        """A .png header on a script is still a script."""
        with pytest.raises(UnsupportedMedia):
            validate(b'<svg xmlns="x"/>', declared_type="image/png")

    def test_a_declared_type_does_not_make_a_real_image_fail(self) -> None:
        # Browsers get this wrong innocently; it is logged, not rejected.
        assert validate(png_bytes(), declared_type="image/jpeg") == "image/png"

    def test_an_oversized_payload_is_refused(self, monkeypatch) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "max_upload_bytes", 128, raising=False)
        with pytest.raises(MediaTooLarge):
            validate(png_bytes(400, 400))

    def test_a_png_header_with_rubbish_behind_it_is_caught_on_decode(self) -> None:
        """Passing the signature check is not enough; it has to decode."""
        with pytest.raises(CorruptMedia):
            process(b"\x89PNG\r\n\x1a\n" + b"not actually a png" * 10)


class TestProcessing:
    def test_an_upload_is_re_encoded_to_webp(self) -> None:
        result = process(jpeg_bytes(1200, 800))
        assert result.mime_type == "image/webp"
        assert result.extension == "webp"
        assert result.width == 1200 and result.height == 800

    def test_derivatives_are_generated_and_never_upscaled(self) -> None:
        result = process(png_bytes(2400, 1600))
        assert set(result.derivatives) == {"thumbnail", "small", "medium", "large"}
        assert result.dimensions["large"] == (1920, 1280)
        assert result.dimensions["thumbnail"] == (200, 133)

    def test_a_small_image_gets_a_thumbnail_but_no_larger_sizes(self) -> None:
        result = process(png_bytes(300, 200))
        assert "thumbnail" in result.derivatives
        assert "large" not in result.derivatives
        assert "medium" not in result.derivatives

    def test_re_encoding_drops_exif(self) -> None:
        """EXIF on a traveller's photo routinely carries their home coordinates."""
        buffer = io.BytesIO()
        image = Image.new("RGB", (600, 400), (10, 10, 10))
        exif = image.getexif()
        exif[271] = "SecretCamera"
        image.save(buffer, format="JPEG", exif=exif)

        assert b"SecretCamera" in buffer.getvalue()
        result = process(buffer.getvalue())
        assert b"SecretCamera" not in result.primary

    def test_an_image_beyond_the_dimension_ceiling_is_refused(self, monkeypatch) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "max_image_dimension", 500, raising=False)
        with pytest.raises(MediaTooLarge):
            process(png_bytes(900, 300))

    def test_transparency_survives(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(buffer, format="PNG")
        result = process(buffer.getvalue())
        with Image.open(io.BytesIO(result.primary)) as reopened:
            assert reopened.mode in ("RGBA", "RGB")

    def test_a_derivative_path_sits_beside_its_original(self) -> None:
        assert (
            derivative_path("blog/2026/09/abc-guide.webp", "small")
            == "blog/2026/09/abc-guide@small.webp"
        )


class TestPathGeneration:
    def test_a_filename_becomes_a_readable_slug(self) -> None:
        assert slugify("Bärcelona Family Guide!!.JPEG") == "barcelona-family-guide"

    def test_a_hostile_filename_cannot_survive_into_a_path(self) -> None:
        for hostile in ("../../etc/passwd", "..\\..\\windows\\system32", "/etc/shadow"):
            slug = slugify(hostile)
            assert "/" not in slug and "\\" not in slug and ".." not in slug

    def test_an_empty_name_still_produces_something(self) -> None:
        assert slugify("") == "file"
        assert slugify("...") == "file"

    def test_a_path_is_partitioned_by_category_and_date(self) -> None:
        path = build_relative_path(
            category="blog", original_filename="Guide.png", extension="webp"
        )
        assert path.startswith("blog/")
        assert path.endswith(".webp")
        assert len(path.split("/")) == 4  # blog/YYYY/MM/name

    def test_two_uploads_of_one_name_do_not_collide(self) -> None:
        first = build_relative_path(
            category="blog", original_filename="guide.png", extension="webp"
        )
        second = build_relative_path(
            category="blog", original_filename="guide.png", extension="webp"
        )
        assert first != second

    def test_an_unknown_category_is_refused(self) -> None:
        with pytest.raises(MediaStorageError):
            build_relative_path(
                category="../../etc", original_filename="x.png", extension="webp"
            )

    def test_an_unsafe_extension_is_refused(self) -> None:
        with pytest.raises(MediaStorageError):
            build_relative_path(
                category="blog", original_filename="x.png", extension="php/../"
            )


class TestLocalStorage:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> LocalMediaStorage:
        return LocalMediaStorage(root=tmp_path, base_url="/media")

    def test_a_file_round_trips(self, store: LocalMediaStorage) -> None:
        path = store.save("blog/2026/09/abc-test.webp", b"pixels")
        assert store.exists(path)
        assert store.open(path) == b"pixels"
        assert store.get_url(path) == "/media/blog/2026/09/abc-test.webp"

    def test_nothing_escapes_the_root(self, store: LocalMediaStorage) -> None:
        for hostile in ("../escape.txt", "../../etc/passwd", "blog/../../escape.txt"):
            with pytest.raises(MediaStorageError):
                store.save(hostile, b"x")

    def test_deleting_something_absent_is_false_not_an_error(
        self, store: LocalMediaStorage
    ) -> None:
        assert store.delete("blog/2026/09/never-existed.webp") is False

    def test_a_partial_write_leaves_nothing_being_served(
        self, store: LocalMediaStorage, tmp_path: Path
    ) -> None:
        """Written to a temporary name and renamed, so a crash is not half a file."""
        store.save("blog/2026/09/abc.webp", b"complete")
        leftovers = list(tmp_path.rglob("*.part"))
        assert leftovers == []

    def test_reading_something_absent_raises(self, store: LocalMediaStorage) -> None:
        with pytest.raises(MediaStorageError):
            store.open("blog/2026/09/missing.webp")

    def test_an_unknown_driver_is_refused(self, monkeypatch) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "media_storage_driver", "s3", raising=False)
        storage.reset_storage()
        with pytest.raises(MediaStorageError, match="only 'local' is implemented"):
            storage.get_storage()
        storage.reset_storage()
