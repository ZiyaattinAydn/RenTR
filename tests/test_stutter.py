from rentr.stutter import normalize_stutters, restore_stutters


def test_normalize_stutters_hides_inline_waits_from_provider() -> None:
    plan = normalize_stutters(
        "Easy for y--{w=0.5}you to say. You n--{w=0.5}never had my problem."
    )

    assert plan.normalized_text == "Easy for you to say. You never had my problem."
    assert [spec.source_word for spec in plan.specs] == ["you", "never"]
    assert [spec.wait_tag for spec in plan.specs] == ["{w=0.5}", "{w=0.5}"]


def test_non_stutter_wait_is_left_for_normal_protection() -> None:
    plan = normalize_stutters("I had to-{w=0.5}{nw}")

    assert not plan.active
    assert plan.normalized_text == "I had to-{w=0.5}{nw}"


def test_restore_stutters_uses_semantic_anchors() -> None:
    plan = normalize_stutters(
        "Easy for y--{w=0.5}you to say. You n--{w=0.5}never had my problem."
    )

    restored = restore_stutters(
        "Senin için söylemesi kolay. Sen asla benim sorunumu yaşamadın.",
        plan,
    )

    assert restored == (
        "S--{w=0.5}senin için söylemesi kolay. Sen a--{w=0.5}asla "
        "benim sorunumu yaşamadın."
    )


def test_restore_sentence_initial_stutter_keeps_natural_target_case() -> None:
    plan = normalize_stutters("Y-{w=0.3}yes...")

    assert restore_stutters("Evet...", plan) == "E-{w=0.3}evet..."


def test_restore_dont_can_attach_to_negative_imperative() -> None:
    plan = normalize_stutters("No, d--{w=0.5}don't be ridiculous.")

    assert restore_stutters("Hayır, saçmalama.", plan) == "Hayır, s--{w=0.5}saçmalama."


def test_restore_multiple_benchmark_stutters() -> None:
    plan = normalize_stutters(
        "That's right... I s--{w=0.5}still can't believe you're seeing both of them "
        "at the same t--{w=0.5}time. You're quite the greedy b--{w=0.5}bastard."
    )

    restored = restore_stutters(
        "Doğru... Hâlâ ikisini de aynı anda gördüğüne inanamıyorum. "
        "Gerçekten açgözlü bir pisliksin.",
        plan,
    )

    assert "H--{w=0.5}hâlâ" in restored
    assert "a--{w=0.5}anda" in restored
    assert "p--{w=0.5}pisliksin" in restored
