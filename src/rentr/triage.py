"""Cheap, deterministic triage before any translation-provider request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from rentr.protection import ProtectionError, protect_text

_PLACEHOLDER = re.compile(r"__RENTR_[0-9]{4}__")
_URL_ONLY = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)


class UnitDisposition(StrEnum):
    """Whether a source string needs natural-language translation."""

    PROVIDER = "provider"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True, slots=True)
class UnitTriage:
    """Explainable classification used by estimates, context and translation."""

    disposition: UnitDisposition
    visible_text: str
    reason: str

    @property
    def requires_provider(self) -> bool:
        return self.disposition is UnitDisposition.PROVIDER


def classify_source_text(source_text: str) -> UnitTriage:
    """Classify source without evaluating Ren'Py syntax or sending it anywhere.

    Ren'Py tags/interpolations/formats are first replaced with opaque placeholders.
    If nothing linguistic remains outside those protected fragments, translating the
    string cannot improve it and may only corrupt control syntax. Such units are
    copied through unchanged.
    """
    try:
        protected = protect_text(source_text)
    except ProtectionError:
        # Malformed syntax must continue through the normal fail-closed pipeline so
        # the user sees the real validation error instead of silently skipping it.
        return UnitTriage(UnitDisposition.PROVIDER, source_text, "protection_error")

    visible = _PLACEHOLDER.sub("", protected.protected_text).strip()
    if not visible:
        return UnitTriage(UnitDisposition.PASSTHROUGH, "", "control_only")
    if _URL_ONLY.fullmatch(visible):
        return UnitTriage(UnitDisposition.PASSTHROUGH, visible, "url_only")
    if not any(character.isalpha() for character in visible):
        return UnitTriage(UnitDisposition.PASSTHROUGH, visible, "nonlinguistic")
    return UnitTriage(UnitDisposition.PROVIDER, visible, "linguistic")


def requires_provider_translation(source_text: str) -> bool:
    """Fast convenience predicate for provider planning and UI counts."""
    return classify_source_text(source_text).requires_provider
