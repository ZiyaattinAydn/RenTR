from __future__ import annotations

import json
from pathlib import Path

import pytest

from rentr.localization import (
    AddressStyle,
    LocalizationAssetError,
    LocalizationAssets,
    load_character_cards,
    load_glossary,
)


def test_loads_versioned_glossary_and_matches_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "1.0",
                "terms": [{"source": "Save", "target": "Kaydet"}],
            }
        ),
        encoding="utf-8",
    )

    glossary = load_glossary(path)

    assert glossary.version == "1.0"
    assert glossary.matching("SAVE your progress")[0].target == "Kaydet"


def test_loads_character_address_style_and_voice(tmp_path: Path) -> None:
    path = tmp_path / "characters.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "characters": [
                    {
                        "speaker": "eileen",
                        "display_name": "Eileen",
                        "address_style": "sen",
                        "traits": ["warm", "direct"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cards = load_character_cards(path)
    assets = LocalizationAssets(characters=cards)

    assert cards[0].address_style is AddressStyle.SEN
    assert assets.character_for("eileen") == cards[0]
    assert assets.character_for("unknown") is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": 2, "version": "1", "terms": []},
        {
            "schema_version": 1,
            "version": "1",
            "terms": [
                {"source": "Save", "target": "Kaydet"},
                {"source": "save", "target": "Kayıt"},
            ],
        },
    ],
)
def test_rejects_invalid_or_duplicate_glossary(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LocalizationAssetError):
        load_glossary(path)
