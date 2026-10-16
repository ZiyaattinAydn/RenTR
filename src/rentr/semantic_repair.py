"""Deterministic routing signals and semantic guardrails for post-editing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rentr.providers import TranslationContext

_EXPLICIT_OR_SLANG = re.compile(
    r"\b(?:fuck|fucking|fucked|shit|damn|bitch|asshole|slut|horny|sex|sexy|hot|"
    r"cock|dick|pussy|cum|cumming|blowjob|suck|naked|orgasm|jerk\s+off|threesome|"
    r"beefcake|steamy|anal)\b",
    re.IGNORECASE,
)
_IDIOM_OR_AMBIGUOUS = re.compile(
    r"\b(?:no shortage|can't get enough|cannot get enough|holding my own|hold my own|"
    r"what strings did you pull|the talk|drives me crazy|size queen|what the|way too|"
    r"quite the|wanna|gonna|get off|sleep with|hit on|turn me on|what about|"
    r"here you go|it'?s about time|meet with|holding my own|found it a .* choice|"
    r"miss being with|i care)\b",
    re.IGNORECASE,
)
_FORMAL_TURKISH = re.compile(
    r"\b(?:siz|sizin|size|sizi|sizde|sizden|"
    r"[a-zçğıöşü]+(?:sınız|siniz|sunuz|sünüz|dınız|diniz|dunuz|dünüz|tınız|tiniz|"
    r"tunuz|tünüz|sanız|seniz|rsınız|rsiniz|rsunuz|rsünüz|acaksınız|eceksiniz|"
    r"ınız|iniz|unuz|ünüz))\b",
    re.IGNORECASE,
)
_SECOND_PERSON_SOURCE = re.compile(
    r"\b(?:you|your|yours|yourself|yourselves|you're|you've|you'll|you'd)\b",
    re.IGNORECASE,
)
_ALTERNATIVE_OUTPUT = re.compile(r"(?:\s/\s|\bor\s+alternatively\b)", re.IGNORECASE)
_DISCLAIMER_OUTPUT = re.compile(
    r"(?:cinsel içerikli|uygunsuz içerik|açık(?:ça)? cinsel|çeviri yapamam|"
    r"bu ifade|alternatif çeviri|translation:)",
    re.IGNORECASE,
)
_CONTROL_FRAGMENT = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")
_PLACEHOLDER_FRAGMENT = re.compile(r"__RENTR_[0-9]{4}__")
_TURKISH_PROFANITY = re.compile(
    r"\b(?:sik|siktir|lan|ulan|lanet|kahret|defol|bok|piç|orospu|sürtük)\w*\b",
    re.IGNORECASE,
)
_TURKISH_SEXUAL_FUCK = re.compile(
    r"\b(?:sik|seks)\w*\b",
    re.IGNORECASE,
)
_SEXUAL_FUCK_SOURCE = re.compile(
    r"(?:\b(?:want|wants|wanted|wanna|going|gonna)\s+to\s+fuck\b|"
    r"\bfuck\s+(?:me|you|him|her|us|them)\b)",
    re.IGNORECASE,
)
_SEXUAL_PUSSY_SOURCE = re.compile(
    r"(?:\b(?:my|your|her|his|the)\s+pussy\b|\bpussy\s+(?:feel|feels|felt|was|is)\b)",
    re.IGNORECASE,
)
_TURKISH_PUSSY = re.compile(
    r"\b(?:vajina\w*|am(?:ım|ın|ı|lar|ların|lara|ları|larda|lardan|"
    r"ına|ını|ında|ından|ının|ımız|ımızı|ımıza|ımızda|ımızdan|ınız|ınızı|"
    r"ınıza|ınızda|ınızdan)?)\b",
    re.IGNORECASE,
)
_BAD_PUSSY_TRANSLITERATION = re.compile(r"\b(?:püs|pussy)\w*\b", re.IGNORECASE)
_CUM_IN_PUSSY_SOURCE = re.compile(r"\bcum\s+in\s+(?:my|your|her|the)\s+pussy\b", re.IGNORECASE)
_TURKISH_INSIDE_EJACULATION = re.compile(
    r"(?:\biç(?:im|in|ine|ime|ine|erisine|eri)\w*\b.{0,24}\bboşal\w*\b|"
    r"\bboşal\w*\b.{0,24}\biç(?:im|in|ine|ime|erisine|eri)\w*\b)",
    re.IGNORECASE,
)
_MALFORMED_TURKISH = re.compile(r"\b(?:benimden|pussymi|püsün)\b", re.IGNORECASE)
_SEXUAL_COCK_SOURCE = re.compile(
    r"(?:\b(?:his|your|my|her|the)\s+(?:cock|dick)\b|\b(?:cock|dick)\s+of\s+his\b)",
    re.IGNORECASE,
)
_TURKISH_COCK = re.compile(r"\b(?:sik|penis|alet)\w*\b", re.IGNORECASE)
_NEGATION_SOURCE = re.compile(
    r"\b(?:not|n't|never|no\s+longer|wasn't|weren't|isn't|aren't|don't|doesn't|didn't)\b",
    re.IGNORECASE,
)
_TURKISH_NEGATION = re.compile(
    r"(?:\b(?:değil|yok|hayır|asla|hiç)\b|"
    r"\b[a-zçğıöşü]+m[ae]\b|"
    r"\b[a-zçğıöşü]+m[aeıiuü](?:yor|yacak|yecek|z|dı|di|du|dü|mış|miş|muş|müş|"
    r"mak|mek)[a-zçğıöşü]*\b)",
    re.IGNORECASE,
)
_CONTEXT_NAME = re.compile(r"\b[A-Z][A-Za-z'-]{2,}\b")
_CONTEXT_NAME_STOPWORDS = {
    "And",
    "Are",
    "But",
    "Can",
    "Did",
    "Do",
    "Does",
    "For",
    "He",
    "Her",
    "His",
    "How",
    "I",
    "If",
    "It",
    "Its",
    "My",
    "No",
    "Not",
    "Oh",
    "She",
    "So",
    "That",
    "The",
    "Their",
    "Then",
    "There",
    "They",
    "This",
    "We",
    "What",
    "When",
    "Where",
    "Who",
    "Why",
    "Yes",
    "You",
    "Your",
}


def _visible_text(text: str) -> str:
    without_controls = _CONTROL_FRAGMENT.sub("", text)
    return _PLACEHOLDER_FRAGMENT.sub("", without_controls).strip()


def _has_suspicious_expansion(source_text: str, translated_text: str) -> bool:
    """Catch context continuation without punishing normal Turkish expansion."""

    source_visible = _visible_text(source_text)
    translated_visible = _visible_text(translated_text)
    source_length = len(source_visible)
    translated_length = len(translated_visible)
    if source_length < 40:
        return False
    return translated_length > source_length * 1.85 and translated_length - source_length > 45


def _adjacent_context_name_leaks(
    source_text: str,
    translated_text: str,
    context: TranslationContext | None,
) -> tuple[str, ...]:
    """Return names copied from adjacent context but absent from the source line."""

    if context is None:
        return ()
    source_folded = source_text.casefold()
    candidates: set[str] = set()
    for adjacent in (context.previous_source_text, context.next_source_text):
        if not adjacent:
            continue
        for match in _CONTEXT_NAME.finditer(adjacent):
            name = match.group(0)
            if name in _CONTEXT_NAME_STOPWORDS or name.casefold() in source_folded:
                continue
            candidates.add(name)

    leaked: list[str] = []
    for name in sorted(candidates):
        stem = re.escape(name.casefold())
        if re.search(rf"\b{stem}[a-zçğıöşü'’]*\b", translated_text.casefold()):
            leaked.append(name)
    return tuple(leaked)


@dataclass(frozen=True, slots=True)
class TranslationRisk:
    """Explainable routing score; this is not a literary quality grade."""

    score: int
    reasons: tuple[str, ...]
    hard_reasons: tuple[str, ...] = ()

    @property
    def should_repair(self) -> bool:
        return self.score >= 40 or bool(self.hard_reasons)


def semantic_guardrails(source_text: str) -> tuple[str, ...]:
    """Return source-specific, non-euphemizing guidance for repair and judging.

    These are hints, not fixed translations. They deliberately describe semantic
    invariants so models can choose natural Turkish without silently censoring.
    """

    rules: list[str] = []
    source_folded = source_text.casefold()
    source_visible_folded = _visible_text(source_text).casefold()

    if _SEXUAL_FUCK_SOURCE.search(source_text):
        rules.append(
            "sexual_fuck: preserve the explicit sexual verb and vulgar intensity; in Turkish "
            "prefer a direct sexual verb such as sik- or an equally explicit construction, "
            "not euphemisms like birlikte olmak or yatmak"
        )
    elif re.search(r"\bfuck\b", source_text, re.IGNORECASE):
        rules.append(
            "fuck_intensity: preserve the profanity/emotional force; do not neutralize it into "
            "a polite or content-free expression"
        )

    if re.search(r"\bcum(?:ming)?\b", source_text, re.IGNORECASE):
        rules.append(
            "cum: preserve the orgasm/ejaculation meaning; Turkish should explicitly express "
            "boşal- when that is the intended sexual sense"
        )

    if re.search(r"\bsex\b", source_text, re.IGNORECASE):
        rules.append(
            "sex: this is the sexual act unless context clearly says biological sex/gender; "
            "do not translate sexual sex as cinsiyet"
        )

    if re.search(r"\banal\s+sex\b", source_text, re.IGNORECASE):
        rules.append(
            "anal_sex: direct Turkish such as anal seks or anal ilişki is appropriate; explicit "
            "wording is not a defect and should not be euphemized"
        )

    if re.search(r"\bslut\b", source_text, re.IGNORECASE):
        rules.append(
            "slut: preserve the insulting/sexual label and its intensity; natural Turkish may "
            "use sürtük, kaşar, orospu or another context-matched sexual insult. Do not soften "
            "it into açık sözlü, rahat, arsız or a non-sexual adjective"
        )

    if _SEXUAL_PUSSY_SOURCE.search(source_text):
        rules.append(
            "pussy: preserve the explicit anatomical/slang reference in natural Turkish; do not "
            "omit it and do not invent/transliterate pseudo-Turkish forms such as püs or pussy-mi"
        )

    if _SEXUAL_COCK_SOURCE.search(source_text):
        rules.append(
            "cock_dick: preserve the explicit penis reference in natural Turkish; do not replace "
            "it with vague words such as tavır, şey, or body-language wording"
        )

    if "hot" in source_folded:
        rules.append(
            "hot: when describing sexual attractiveness/arousal, use a Turkish meaning such as "
            "çekici, seksi, ateşli or uyarıcı rather than literal temperature sıcak"
        )

    if re.fullmatch(r"\s*what\s+the(?:\.{2,}|…)?[!?]*\s*", source_text, re.IGNORECASE):
        rules.append(
            "what_the_incomplete: preserve the deliberately unfinished shock/disbelief; do not "
            "invent a specific action such as ne yapıyorsun when the source never says what "
            "happened"
        )

    if "holding my own" in source_folded or "hold my own" in source_folded:
        rules.append(
            "holding_my_own: this means keeping up/competing successfully, not being alone; "
            "natural Turkish can express başa çıkmak, geri kalmamak or dişe diş gitmek depending "
            "context, but not kendi başımayım"
        )

    if "here you go" in source_folded:
        rules.append(
            "here_you_go: when handing/giving something, use a Turkish offering expression such "
            "as buyur/al; do not turn it into işte o or invent an object"
        )

    if "what about you" in source_folded:
        rules.append(
            "what_about_you: preserve the reciprocal prompt, usually ya sen?/peki ya sen?; do not "
            "expand it into sen ne düşünüyorsun unless the source explicitly asks an opinion"
        )

    if source_visible_folded.strip(" /.:;!?…") == "about me":
        rules.append(
            "about_me: this is the elliptical question 'me?/about me?', not an invitation like "
            "benden bahsetmek ister misin"
        )

    if re.search(r"\bit'?s about time\b", source_text, re.IGNORECASE):
        rules.append(
            "about_time: preserve the sense of finally/it was due; do not translate it as artık "
            "yeter unless the source explicitly means enough"
        )

    if re.search(r"\bmeet with\b", source_text, re.IGNORECASE):
        rules.append(
            "meet_with: this normally means buluşmak/görüşmek with someone already known; do not "
            "use tanışmak unless the source explicitly means meeting for the first time"
        )

    if source_visible_folded.strip(" /.:;!?…") == "i care":
        rules.append(
            "i_care: preserve caring/concern; do not translate it as bana göre (in my opinion)"
        )

    if "pussy" in source_folded:
        rules.append(
            "pussy_register: pussy is slang; vajina preserves anatomy but can sound clinical, so "
            "prefer a natural register-matched Turkish expression when context is erotic/casual"
        )

    if "no shortage" in source_folded:
        rules.append(
            "no_shortage: preserve abundance; do not reverse it into yok, az, or scarcity"
        )

    return tuple(rules)


class TranslationRiskAnalyzer:
    """Route likely semantic/register mistakes to a contextual repair model."""

    def analyze(
        self,
        source_text: str,
        translated_text: str,
        *,
        context: TranslationContext | None = None,
    ) -> TranslationRisk:
        reasons: list[str] = []
        hard_reasons: list[str] = []
        score = 0
        source_folded = source_text.casefold()
        source_visible_folded = _visible_text(source_text).casefold()

        if _EXPLICIT_OR_SLANG.search(source_text):
            reasons.append("explicit_or_slang_source")
            score += 45

        if _IDIOM_OR_AMBIGUOUS.search(source_text):
            reasons.append("idiom_or_ambiguous_source")
            score += 40

        if _ALTERNATIVE_OUTPUT.search(translated_text):
            reasons.append("multiple_translation_alternatives")
            hard_reasons.append("multiple_translation_alternatives")
            score += 80

        if _DISCLAIMER_OUTPUT.search(translated_text):
            reasons.append("translator_disclaimer_or_commentary")
            hard_reasons.append("translator_disclaimer_or_commentary")
            score += 100

        if "hot" in source_folded and re.search(r"\bsıcak\w*\b", translated_text, re.I):
            reasons.append("hot_literalized_as_temperature")
            hard_reasons.append("hot_literalized_as_temperature")
            score += 80

        if re.search(r"\bsex\b", source_text, re.I) and re.search(
            r"\bcinsiyet\w*\b", translated_text, re.I
        ):
            reasons.append("sex_mistranslated_as_gender")
            hard_reasons.append("sex_mistranslated_as_gender")
            score += 90

        if source_visible_folded.strip(" /.:;!?…") == "sex" and not re.search(
            r"\b(?:seks|cinsel\s+ilişki)\b", translated_text, re.I
        ):
            reasons.append("sex_act_softened_to_concept")
            hard_reasons.append("sex_act_softened_to_concept")
            score += 85

        if re.search(r"\banal\s+sex\b", source_text, re.I) and not (
            re.search(r"\banal\w*\b", translated_text, re.I)
            and re.search(r"\b(?:seks|ilişki)\w*\b", translated_text, re.I)
        ):
            reasons.append("anal_sex_semantics_missing")
            hard_reasons.append("anal_sex_semantics_missing")
            score += 90

        if re.search(r"\bcum(?:ming)?\b", source_text, re.I) and not re.search(
            r"\bboşal\w*\b", translated_text, re.I
        ):
            reasons.append("cum_semantics_missing")
            hard_reasons.append("cum_semantics_missing")
            score += 90

        if _SEXUAL_FUCK_SOURCE.search(source_text):
            if not _TURKISH_SEXUAL_FUCK.search(translated_text):
                reasons.append("sexual_fuck_semantics_softened")
                hard_reasons.append("sexual_fuck_semantics_softened")
                score += 90
        elif re.search(r"\bfuck\b", source_text, re.I) and not _TURKISH_PROFANITY.search(
            translated_text
        ):
            reasons.append("fuck_intensity_softened")
            hard_reasons.append("fuck_intensity_softened")
            score += 70

        if re.search(r"\bslut\b", source_text, re.I) and not re.search(
            r"\b(?:sürtük|orospu|kaşar|fahişe)\w*\b", translated_text, re.I
        ):
            reasons.append("slut_semantics_softened")
            hard_reasons.append("slut_semantics_softened")
            score += 80

        if _SEXUAL_PUSSY_SOURCE.search(source_text):
            if _BAD_PUSSY_TRANSLITERATION.search(translated_text):
                reasons.append("pussy_malformed_transliteration")
                hard_reasons.append("pussy_malformed_transliteration")
                score += 90
            else:
                natural_inside_ejaculation = bool(
                    _CUM_IN_PUSSY_SOURCE.search(source_text)
                    and _TURKISH_INSIDE_EJACULATION.search(translated_text)
                )
                if not _TURKISH_PUSSY.search(translated_text) and not natural_inside_ejaculation:
                    reasons.append("pussy_semantics_missing")
                    hard_reasons.append("pussy_semantics_missing")
                    score += 85
                elif re.search(r"\bvajina\w*\b", translated_text, re.I):
                    reasons.append("pussy_register_softened_to_clinical")
                    score += 15

        if _SEXUAL_COCK_SOURCE.search(source_text) and not _TURKISH_COCK.search(translated_text):
            reasons.append("cock_semantics_missing")
            hard_reasons.append("cock_semantics_missing")
            score += 85

        if _MALFORMED_TURKISH.search(translated_text):
            reasons.append("malformed_turkish_word")
            hard_reasons.append("malformed_turkish_word")
            score += 90

        if re.fullmatch(r"\s*what\s+the(?:\.{2,}|…)?[!?]*\s*", source_text, re.I) and re.search(
            r"\bne\s+yap(?:ıyorsun|ıyorsunuz|ıyor|tı|tın|tınız)\b", translated_text, re.I
        ):
            reasons.append("what_the_incomplete_overexpanded")
            hard_reasons.append("what_the_incomplete_overexpanded")
            score += 85

        if re.search(r"\bholding my own\b|\bhold my own\b", source_text, re.I) and re.search(
            r"\bkendi\s+başım(?:a|da|dan|ayım)?\b", translated_text, re.I
        ):
            reasons.append("holding_my_own_mistranslated_as_alone")
            hard_reasons.append("holding_my_own_mistranslated_as_alone")
            score += 90

        if "here you go" in source_folded and re.search(
            r"\bişte\s+(?:o|bu kadar)\b", translated_text, re.I
        ):
            reasons.append("here_you_go_mistranslated")
            hard_reasons.append("here_you_go_mistranslated")
            score += 80

        if "what about you" in source_folded and re.search(
            r"\bsen\s+ne\s+düşün\w*", translated_text, re.I
        ):
            reasons.append("what_about_you_mistranslated_as_opinion")
            hard_reasons.append("what_about_you_mistranslated_as_opinion")
            score += 80

        if source_visible_folded.strip(" /.:;!?…") == "about me" and re.search(
            r"\bister\s+misin\b", translated_text, re.I
        ):
            reasons.append("about_me_overexpanded")
            hard_reasons.append("about_me_overexpanded")
            score += 80

        if re.search(r"\bit'?s about time\b", source_text, re.I) and re.search(
            r"\bartık\s+yeter\b", translated_text, re.I
        ):
            reasons.append("about_time_mistranslated_as_enough")
            hard_reasons.append("about_time_mistranslated_as_enough")
            score += 85

        if re.search(r"\bmeet with\b", source_text, re.I) and re.search(
            r"\btanış\w*\b", translated_text, re.I
        ):
            reasons.append("meet_with_mistranslated_as_first_meeting")
            hard_reasons.append("meet_with_mistranslated_as_first_meeting")
            score += 80

        if source_visible_folded.strip(" /.:;!?…") == "i care" and re.search(
            r"\bbana\s+göre\b", translated_text, re.I
        ):
            reasons.append("i_care_mistranslated_as_opinion")
            hard_reasons.append("i_care_mistranslated_as_opinion")
            score += 85

        if re.search(r"\bmiss\s+being\s+with\b", source_text, re.I) and re.search(
            r"\bolmamı\s+özle\w*\b", translated_text, re.I
        ):
            reasons.append("miss_being_with_reflexive_error")
            hard_reasons.append("miss_being_with_reflexive_error")
            score += 80

        source_visible_for_punctuation = _visible_text(source_text).lstrip()
        translated_visible_for_punctuation = _visible_text(translated_text).lstrip()
        if (
            translated_visible_for_punctuation.startswith((":", ";"))
            and not source_visible_for_punctuation.startswith((":", ";"))
        ):
            reasons.append("leading_punctuation_artifact")
            hard_reasons.append("leading_punctuation_artifact")
            score += 80

        if re.search(r"\bfuck\b", source_text, re.I) and re.search(
            r"\b(?:ah|oh)[,! ]+lanet(?:[.!?]+|$)", translated_text, re.I
        ):
            reasons.append("unnatural_standalone_lanet")
            hard_reasons.append("unnatural_standalone_lanet")
            score += 70

        if _has_suspicious_expansion(source_text, translated_text):
            reasons.append("suspicious_output_expansion")
            hard_reasons.append("suspicious_output_expansion")
            score += 90

        context_name_leaks = _adjacent_context_name_leaks(source_text, translated_text, context)
        if context_name_leaks:
            reasons.append("adjacent_context_name_leak")
            hard_reasons.append("adjacent_context_name_leak")
            score += 100

        # Negation loss is a common catastrophic semantic failure. Keep this conservative:
        # only flag longer clauses where English contains explicit negation and Turkish contains
        # no recognizable negative marker at all.
        visible_source = _visible_text(source_text)
        source_word_count = len(re.findall(r"[A-Za-z]+", visible_source))
        if (
            source_word_count >= 7
            and _NEGATION_SOURCE.search(visible_source)
            and not _TURKISH_NEGATION.search(translated_text)
        ):
            reasons.append("possible_negation_loss")
            hard_reasons.append("possible_negation_loss")
            score += 80

        casual_source = bool(
            _SECOND_PERSON_SOURCE.search(visible_source)
            or (
                context is not None
                and context.speaker
                and re.search(
                    r"\b(?:wanna|gonna|fuck|shit|damn)\b",
                    visible_source,
                    re.I,
                )
            )
            or (visible_source.rstrip().endswith("?") and 0 < source_word_count <= 4)
        )
        character_prefers_formal = bool(
            context is not None
            and context.character is not None
            and context.character.address_style.casefold() == "siz"
        )
        if casual_source and not character_prefers_formal and _FORMAL_TURKISH.search(
            translated_text
        ):
            reasons.append("unexpected_formal_register")
            score += 40

        source_words = tuple(re.findall(r"[A-Za-z]+", visible_source))
        if (
            len(source_words) >= 2
            and translated_text.strip().casefold() == source_text.strip().casefold()
        ):
            reasons.append("source_copied_without_translation")
            hard_reasons.append("source_copied_without_translation")
            score += 100

        # Short dialogue is cheap to repair and disproportionately context-sensitive.
        if context is not None and context.speaker and 0 < len(source_words) <= 4:
            reasons.append("short_dialogue_context")
            score += 10

        return TranslationRisk(
            score=min(score, 100),
            reasons=tuple(dict.fromkeys(reasons)),
            hard_reasons=tuple(dict.fromkeys(hard_reasons)),
        )

    @staticmethod
    def unresolved_hard_reasons(risk: TranslationRisk) -> tuple[str, ...]:
        """Hard flags remaining after repair must not enter translation memory."""
        return risk.hard_reasons
