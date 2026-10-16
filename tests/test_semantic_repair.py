from rentr.providers import CharacterGuidance, TranslationContext
from rentr.semantic_repair import TranslationRiskAnalyzer


def test_flags_literal_hot_and_no_shortage_as_hard_semantic_risk() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "There's no shortage of hot girls around him!",
        "Onun etrafında çok sıcak kızlar yok!",
        context=TranslationContext(speaker="b"),
    )

    assert risk.should_repair
    assert "explicit_or_slang_source" in risk.reasons
    assert "idiom_or_ambiguous_source" in risk.reasons
    assert "hot_literalized_as_temperature" in risk.hard_reasons


def test_flags_cum_softening_and_translation_alternatives() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Cum in my pussy!",
        "Benim içine girin! / İçime gelin!",
        context=TranslationContext(speaker="l"),
    )

    assert risk.should_repair
    assert "cum_semantics_missing" in risk.hard_reasons
    assert "multiple_translation_alternatives" in risk.hard_reasons


def test_flags_unexpected_formal_register_but_respects_character_card() -> None:
    analyzer = TranslationRiskAnalyzer()
    casual = analyzer.analyze(
        "Are you having fun?",
        "Eğleniyor musunuz?",
        context=TranslationContext(speaker="i"),
    )
    formal = analyzer.analyze(
        "Are you having fun?",
        "Eğleniyor musunuz?",
        context=TranslationContext(
            speaker="i",
            character=CharacterGuidance("Ian", "siz"),
        ),
    )

    assert "unexpected_formal_register" in casual.reasons
    assert "unexpected_formal_register" not in formal.reasons


def test_good_plain_translation_stays_low_risk() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Developer Menu",
        "Geliştirici Menüsü",
        context=TranslationContext(),
    )

    assert not risk.should_repair
    assert risk.reasons == ()


def test_short_question_flags_unexpected_formal_register_without_speaker() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Ready?",
        "Hazır mısınız?",
        context=TranslationContext(),
    )

    assert risk.should_repair
    assert "unexpected_formal_register" in risk.reasons


def test_flags_formal_second_person_morphology_without_speaker() -> None:
    analyzer = TranslationRiskAnalyzer()

    okay = analyzer.analyze(
        "You're okay",
        "İyisiniz.",
        context=TranslationContext(),
    )
    heard = analyzer.analyze(
        "Where did you hear that?",
        "Bunu nereden duydunuz?",
        context=TranslationContext(),
    )

    assert "unexpected_formal_register" in okay.reasons
    assert "unexpected_formal_register" in heard.reasons


def test_flags_malformed_or_missing_explicit_anatomy() -> None:
    analyzer = TranslationRiskAnalyzer()

    malformed = analyzer.analyze(
        "Your pussy feels so good!",
        "Senin püsün çok hoş!",
        context=TranslationContext(speaker="st"),
    )
    omitted = analyzer.analyze(
        "That cock of his drives me crazy.",
        "Onun tavırları beni deli ediyor.",
        context=TranslationContext(speaker="l"),
    )

    assert "pussy_malformed_transliteration" in malformed.hard_reasons
    assert "cock_semantics_missing" in omitted.hard_reasons


def test_direct_anal_sex_translation_is_not_a_hard_explicitness_error() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "How about some anal sex?",
        "Biraz anal seks yapmaya ne dersin?",
        context=TranslationContext(speaker="l"),
    )

    assert "anal_sex_semantics_missing" not in risk.hard_reasons


def test_flags_possible_negation_loss_in_long_clause() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "My pussy was soaking, but it wasn't Louise's tongue that I really wanted.",
        "Amım sırılsıklamdı, aslında Louise'in dilini istiyordum.",
        context=TranslationContext(),
    )

    assert "possible_negation_loss" in risk.hard_reasons


def test_semantic_guardrails_are_direct_without_forcing_one_translation() -> None:
    from rentr.semantic_repair import semantic_guardrails

    rules = semantic_guardrails("I want to fuck you. Cum in my pussy!")

    assert any(rule.startswith("sexual_fuck:") for rule in rules)
    assert any(rule.startswith("cum:") for rule in rules)
    assert any(rule.startswith("pussy:") for rule in rules)


def test_negation_detector_accepts_turkish_negative_imperative_and_progressive() -> None:
    analyzer = TranslationRiskAnalyzer()

    imperative = analyzer.analyze(
        "Yes, don't stop...! Oh, fuck! More...!",
        "Evet, durma! Ah, siktir! Daha fazla!",
        context=TranslationContext(speaker="x"),
    )
    progressive = analyzer.analyze(
        "She's not winning, that's for sure.",
        "Kesinlikle kazanmıyor.",
        context=TranslationContext(),
    )

    assert "possible_negation_loss" not in imperative.hard_reasons
    assert "possible_negation_loss" not in progressive.hard_reasons


def test_flags_suspicious_repair_expansion_as_hard_risk() -> None:
    source = (
        "I was letting myself get dragged into this. I had to keep my cool, "
        "I had to-{w=0.5}{nw}"
    )
    translated = (
        "Kendimi bu işin içine çekiliyordum. Sakin kalmam gerekiyordu, kontrolümü "
        "sağlamam gerekiyordu - Axel'i iterek beni öne itti, dört ayaklarım üzerinde "
        "durmamı sağladı.{w=0.5}{nw}"
    )
    risk = TranslationRiskAnalyzer().analyze(source, translated)

    assert "suspicious_output_expansion" in risk.reasons
    assert "suspicious_output_expansion" in risk.hard_reasons


def test_flags_name_copied_from_adjacent_context() -> None:
    context = TranslationContext(
        speaker="p",
        previous_source_text="I had to keep my cool.",
        next_source_text="Axel pushed me forward and told me to stay still.",
    )
    risk = TranslationRiskAnalyzer().analyze(
        "I had to keep my cool.",
        "Sakin kalmalıydım ama Axel beni öne itti.",
        context=context,
    )

    assert "adjacent_context_name_leak" in risk.reasons
    assert "adjacent_context_name_leak" in risk.hard_reasons


def test_pussy_semantics_does_not_treat_turkish_ama_as_anatomy() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "My pussy was soaking, but it wasn't Louise's tongue that I really wanted.",
        "Vücudum ıslanmıştı, ama aslında benim istediğim Louise'un dili değildi.",
        context=TranslationContext(),
    )

    assert "pussy_semantics_missing" in risk.hard_reasons


def test_cum_in_pussy_allows_natural_turkish_inside_ejaculation_construction() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Cum in my pussy!",
        "İçime boşal!",
        context=TranslationContext(speaker="l"),
    )

    assert "cum_semantics_missing" not in risk.hard_reasons
    assert "pussy_semantics_missing" not in risk.hard_reasons


def test_standalone_sex_requires_sex_act_not_abstract_concept() -> None:
    analyzer = TranslationRiskAnalyzer()
    softened = analyzer.analyze("Sex", "Cinsellik.", context=TranslationContext())
    direct = analyzer.analyze("Sex", "Seks", context=TranslationContext())

    assert "sex_act_softened_to_concept" in softened.hard_reasons
    assert "sex_act_softened_to_concept" not in direct.hard_reasons


def test_flags_holding_my_own_as_being_alone() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "I was holding my own against Jeremy.",
        "Jeremy'ye karşı kendi başımayım.",
        context=TranslationContext(),
    )
    assert "holding_my_own_mistranslated_as_alone" in risk.hard_reasons


def test_flags_here_you_go_as_iste_o() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Of course. Here you go.",
        "Elbette. İşte o.",
        context=TranslationContext(),
    )
    assert "here_you_go_mistranslated" in risk.hard_reasons


def test_flags_what_about_you_as_opinion_question() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Me? What about you?",
        "Ben mi? Sen ne düşünüyorsun?",
        context=TranslationContext(speaker="i"),
    )
    assert "what_about_you_mistranslated_as_opinion" in risk.hard_reasons


def test_flags_about_me_overexpansion() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "About me?",
        "Benden bahsetmek ister misin?",
        context=TranslationContext(speaker="i"),
    )
    assert "about_me_overexpanded" in risk.hard_reasons


def test_flags_its_about_time_as_enough() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "It's about time",
        "Artık yeter.",
        context=TranslationContext(),
    )
    assert "about_time_mistranslated_as_enough" in risk.hard_reasons


def test_flags_meet_with_as_first_meeting() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Meet with Holly",
        "Holly ile tanışın.",
        context=TranslationContext(),
    )
    assert "meet_with_mistranslated_as_first_meeting" in risk.hard_reasons


def test_flags_i_care_as_bana_gore() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "{image=icon_wits.webp}/{image=icon_charisma.webp}I care",
        "{image=icon_wits.webp}/{image=icon_charisma.webp}Bana göre.",
        context=TranslationContext(),
    )
    assert "i_care_mistranslated_as_opinion" in risk.hard_reasons


def test_flags_known_malformed_turkish_word() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "She closed herself off from me.",
        "Kendini benimden soyutladı.",
        context=TranslationContext(),
    )
    assert "malformed_turkish_word" in risk.hard_reasons


def test_flags_leading_punctuation_after_control_tag() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "{image=icon.webp}This feels good",
        "{image=icon.webp}:Bu iyi hissettiriyor",
        context=TranslationContext(),
    )
    assert "leading_punctuation_artifact" in risk.hard_reasons


def test_flags_unnatural_standalone_lanet_for_exclamatory_fuck() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "Yes, don't stop...! Oh, fuck! More...!",
        "Evet, durma! Ah, lanet! Daha fazlası!",
        context=TranslationContext(speaker="l"),
    )
    assert "unnatural_standalone_lanet" in risk.hard_reasons


def test_semantic_guardrails_ignore_protection_placeholders_for_exact_short_source() -> None:
    from rentr.semantic_repair import semantic_guardrails

    rules = semantic_guardrails("__RENTR_0000__I care")

    assert any(rule.startswith("i_care:") for rule in rules)


def test_flags_incomplete_what_the_as_invented_specific_action() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "What the...?!",
        "Ne yapıyorsun?!",
        context=TranslationContext(speaker="mr"),
    )
    assert "what_the_incomplete_overexpanded" in risk.hard_reasons


def test_slut_guardrail_does_not_accept_plain_arsiz_as_equivalent() -> None:
    risk = TranslationRiskAnalyzer().analyze(
        "I can't believe how much of a slut you are, Alison!",
        "Alison, ne kadar arsızsın, inanamıyorum!",
        context=TranslationContext(speaker="i"),
    )
    assert "slut_semantics_softened" in risk.hard_reasons
