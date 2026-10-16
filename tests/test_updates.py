from __future__ import annotations

from pathlib import Path

import pytest

from rentr.domain import TranslationKind, TranslationUnit
from rentr.updates import UpdateKind, compare_inventories


def _unit(unit_id: str, source: str) -> TranslationUnit:
    return TranslationUnit(
        unit_id=unit_id,
        source_text=source,
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )


def test_classifies_added_removed_changed_and_unchanged_units() -> None:
    previous = (_unit("removed", "Old"), _unit("changed", "Before"), _unit("same", "Same"))
    current = (_unit("added", "New"), _unit("changed", "After"), _unit("same", "Same"))

    changes = compare_inventories(previous, current)

    assert {change.unit_id: change.kind for change in changes} == {
        "added": UpdateKind.ADDED,
        "changed": UpdateKind.CHANGED,
        "removed": UpdateKind.REMOVED,
        "same": UpdateKind.UNCHANGED,
    }


def test_rejects_duplicate_unit_ids() -> None:
    duplicate = _unit("same", "One")

    with pytest.raises(ValueError, match="yinelenen"):
        compare_inventories((duplicate, duplicate), ())
