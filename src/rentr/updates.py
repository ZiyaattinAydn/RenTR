"""Compare translation inventories across game updates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rentr.domain import TranslationUnit


class UpdateKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class InventoryChange:
    unit_id: str
    kind: UpdateKind
    previous: TranslationUnit | None
    current: TranslationUnit | None


def compare_inventories(
    previous: tuple[TranslationUnit, ...],
    current: tuple[TranslationUnit, ...],
) -> tuple[InventoryChange, ...]:
    """Compare deterministic unit IDs while retaining both sides for review."""
    previous_by_id = {unit.unit_id: unit for unit in previous}
    current_by_id = {unit.unit_id: unit for unit in current}
    if len(previous_by_id) != len(previous) or len(current_by_id) != len(current):
        raise ValueError("Envanterde yinelenen unit_id karşılaştırılamaz")
    changes: list[InventoryChange] = []
    for unit_id in sorted(previous_by_id.keys() | current_by_id.keys()):
        old = previous_by_id.get(unit_id)
        new = current_by_id.get(unit_id)
        if old is None:
            kind = UpdateKind.ADDED
        elif new is None:
            kind = UpdateKind.REMOVED
        elif old.source_hash != new.source_hash:
            kind = UpdateKind.CHANGED
        else:
            kind = UpdateKind.UNCHANGED
        changes.append(InventoryChange(unit_id, kind, old, new))
    return tuple(changes)
