"""Deterministic rendering for Ren'Py hesitation waits embedded inside words.

Ren'Py scripts often encode a spoken stutter as ``d--{w=0.5}don't``. Translating the
opaque wait token together with the English word is fragile because the target word may move or
change completely. This module removes only that narrow speech pattern before provider calls and
re-applies the hesitation to the translated Turkish word afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_STUTTER = re.compile(
    r"(?P<prefix>[A-Za-z])(?P<hyphens>-{1,2})"
    r"(?P<wait>\{w(?:=[^{}]+)?\})"
    r"(?P<word>[A-Za-z][A-Za-z'’]*)"
)
_WORD = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû]+(?:['’][A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû]+)?")

# High-confidence semantic anchors. These are used only to locate where the *existing* Turkish
# translation should receive the hesitation effect; they never replace translated words.
_TARGET_ANCHORS: dict[str, tuple[str, ...]] = {
    "you": ("sen", "sana", "seni", "senin", "sende", "senden"),
    "never": ("asla", "hiç"),
    "naked": ("çıplak", "soyun"),
    "but": ("ama", "fakat", "ancak"),
    "what": ("ne",),
    "mean": ("yani", "demek", "kast", "diyorum"),
    "yes": ("evet",),
    "still": ("hâlâ", "hala"),
    "time": ("zaman", "anda", "an"),
    "bastard": ("pislik", "herif", "piç", "şerefsiz", "alçak"),
}


@dataclass(frozen=True, slots=True)
class StutterSpec:
    """One source hesitation that must be rendered after translation."""

    source_word: str
    wait_tag: str
    hyphens: str
    relative_word_position: float


@dataclass(frozen=True, slots=True)
class StutterPlan:
    """Provider-safe source text plus deterministic post-rendering metadata."""

    normalized_text: str
    specs: tuple[StutterSpec, ...]

    @property
    def active(self) -> bool:
        return bool(self.specs)


def _source_word_positions(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in _WORD.finditer(text)]


def normalize_stutters(text: str) -> StutterPlan:
    """Remove only ``x--{w}word``-style hesitation controls from provider input.

    A match is accepted only when the repeated prefix letter equals the first letter of the word;
    ordinary wait tags remain untouched and continue through the normal protection pipeline.
    """

    matches = [
        match
        for match in _STUTTER.finditer(text)
        if match.group("prefix").casefold() == match.group("word")[0].casefold()
    ]
    if not matches:
        return StutterPlan(text, ())

    source_words = _source_word_positions(text)
    total_words = max(len(source_words), 1)
    specs: list[StutterSpec] = []
    output: list[str] = []
    cursor = 0

    for match in matches:
        output.append(text[cursor : match.start()])
        word = match.group("word")
        output.append(word)
        word_index = next(
            (
                index
                for index, (start, end) in enumerate(source_words)
                if start <= match.start("word") < end
            ),
            0,
        )
        relative = word_index / max(total_words - 1, 1)
        specs.append(
            StutterSpec(
                source_word=word,
                wait_tag=match.group("wait"),
                hyphens=match.group("hyphens"),
                relative_word_position=relative,
            )
        )
        cursor = match.end()

    output.append(text[cursor:])
    return StutterPlan("".join(output), tuple(specs))


def _anchor_match(text: str, source_word: str, used: set[tuple[int, int]]) -> re.Match[str] | None:
    anchors = _TARGET_ANCHORS.get(source_word.casefold(), ())
    for anchor in anchors:
        # Stem matching is intentional for verbs such as soyun-/kast-.
        pattern = re.compile(
            rf"\b{re.escape(anchor)}[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû'’]*\b", re.IGNORECASE
        )
        for match in pattern.finditer(text):
            if (match.start(), match.end()) not in used:
                return match
    return None


def _negative_imperative_match(text: str, used: set[tuple[int, int]]) -> re.Match[str] | None:
    # ``don't`` often disappears as an independent word in Turkish. Prefer a negative imperative
    # such as ``saçmalama``/``söyleme`` before falling back to relative-position alignment.
    pattern = re.compile(
        r"\b[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû]{3,}(?:ma|me)(?:yın|yin|yun|yün)?\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        if (match.start(), match.end()) not in used:
            return match
    return None


def _relative_match(
    text: str,
    position: float,
    used: set[tuple[int, int]],
) -> re.Match[str] | None:
    words = [match for match in _WORD.finditer(text) if (match.start(), match.end()) not in used]
    if not words:
        return None
    index = round(position * max(len(words) - 1, 0))
    return words[min(max(index, 0), len(words) - 1)]


def _render_prefix(target_word: str) -> tuple[str, str]:
    first = target_word[0]
    if first.isupper():
        return first.upper(), first.lower() + target_word[1:]
    return first.lower(), target_word


def restore_stutters(translated_text: str, plan: StutterPlan) -> str:
    """Re-apply source hesitation waits to already translated Turkish text.

    The function never invents lexical content. It locates an existing Turkish word using a
    high-confidence semantic anchor first, then a conservative relative-position fallback. If no
    word exists, the original translation is returned unchanged so the caller can still validate
    it normally.
    """

    if not plan.specs:
        return translated_text

    result = translated_text
    used: set[tuple[int, int]] = set()

    for spec in plan.specs:
        match = _anchor_match(result, spec.source_word, used)
        if match is None and spec.source_word.casefold() in {"don't", "dont"}:
            match = _negative_imperative_match(result, used)
        if match is None:
            match = _relative_match(result, spec.relative_word_position, used)
        if match is None:
            continue

        target_word = match.group(0)
        prefix, rendered_word = _render_prefix(target_word)
        replacement = f"{prefix}{spec.hyphens}{spec.wait_tag}{rendered_word}"
        start, end = match.span()
        result = result[:start] + replacement + result[end:]

        delta = len(replacement) - (end - start)
        shifted: set[tuple[int, int]] = set()
        for used_start, used_end in used:
            if used_start >= end:
                shifted.add((used_start + delta, used_end + delta))
            else:
                shifted.add((used_start, used_end))
        shifted.add((start, start + len(replacement)))
        used = shifted

    return result
