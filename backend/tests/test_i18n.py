"""The server-side phrase catalogue."""

from __future__ import annotations

import pytest

from app.core.constants import SUPPORTED_LANGUAGES
from app.core.i18n import PHRASES, translate, translate_all


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_phrase_exists_in_every_language(language):
    missing = [code for code, entry in PHRASES.items() if not entry.get(language)]
    assert missing == []


def test_placeholders_are_filled():
    rendered = translate("journey.title", "en", days=5, destination="Singapore")
    assert rendered == "5-day journey to Singapore"


def test_an_unknown_language_falls_back_to_english():
    assert translate("journey.closing", "fr") == translate("journey.closing", "en")


def test_an_unknown_code_returns_itself():
    assert translate("nothing.here", "en") == "nothing.here"


def test_code_lists_render_and_deduplicate():
    rendered = translate_all(
        ["packing.hot", "packing.hot", ["weather.indoor_ready", {"dates": "2027-01-11"}]],
        "en",
    )
    assert len(rendered) == 2
    assert "2027-01-11" in rendered[1]


@pytest.mark.parametrize(
    ("language", "low", "high"),
    [("bn", "ঀ", "৿"), ("hi", "ऀ", "ॿ")],
)
def test_translations_use_the_expected_script(language, low, high):
    rendered = translate("journey.closing", language)
    assert any(low <= char <= high for char in rendered)
