import json
import zipfile
from pathlib import Path

import pytest

from rentr.mod_package import (
    ACTIVATION_CONTENT,
    ACTIVATION_PATH,
    MANIFEST_PATH,
    TranslationPackageError,
    apply_package_install,
    build_translation_package,
    load_install_receipt,
    plan_package_install,
    rollback_package_install,
    verify_translation_package,
)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    translation = workspace / "game" / "tl" / "turkish"
    translation.mkdir(parents=True)
    (translation / "script.rpy").write_text(
        'translate turkish strings:\n\n    old "Start"\n    new "Başla"\n',
        encoding="utf-8",
    )
    return workspace


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "VisualNovel"
    (game / "game").mkdir(parents=True)
    return game


def test_build_is_reproducible_and_verified(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    first = build_translation_package(workspace)
    first_bytes = first.package_path.read_bytes()
    second = build_translation_package(workspace)
    verified = verify_translation_package(second.package_path)

    assert second.package_path.read_bytes() == first_bytes
    assert first.package_hash == second.package_hash
    assert verified.manifest.language == "turkish"
    assert verified.manifest.activation == "default_language"
    assert [item.path for item in verified.manifest.files] == [
        ACTIVATION_PATH,
        "game/tl/turkish/script.rpy",
    ]
    assert dict((item.path, content) for item, content in verified.payloads)[
        ACTIVATION_PATH
    ] == ACTIVATION_CONTENT


def test_build_can_leave_language_activation_manual(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path), activate_turkish=False)

    verified = verify_translation_package(built.package_path)

    assert verified.manifest.activation == "manual"
    assert [item.path for item in verified.manifest.files] == [
        "game/tl/turkish/script.rpy"
    ]


def test_build_rejects_output_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(TranslationPackageError, match="dışında"):
        build_translation_package(_workspace(tmp_path), tmp_path / "outside.zip")


def test_verify_rejects_tampered_payload(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    tampered = built.package_path.with_name("tampered.zip")
    with zipfile.ZipFile(built.package_path) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "game/tl/turkish/script.rpy":
                content += b"# changed\n"
            target.writestr(info.filename, content)

    with pytest.raises(TranslationPackageError, match="doğrulanamadı"):
        verify_translation_package(tampered)


def test_verify_rejects_unlisted_and_traversal_paths(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    unsafe = built.package_path.with_name("unsafe.zip")
    with zipfile.ZipFile(built.package_path) as source, zipfile.ZipFile(unsafe, "w") as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info.filename))
        target.writestr("../outside.rpy", b"unsafe")

    with pytest.raises(TranslationPackageError, match="manifest"):
        verify_translation_package(unsafe)


def test_install_plan_is_dry_run_then_install_and_rollback_are_guarded(
    tmp_path: Path,
) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)

    plan = plan_package_install(built.package_path, game)

    assert plan.collisions == ()
    assert not (game / "game" / "tl" / "turkish" / "script.rpy").exists()
    receipt = apply_package_install(plan)
    assert (game / "game" / "tl" / "turkish" / "script.rpy").is_file()
    assert (game / ACTIVATION_PATH).read_bytes() == ACTIVATION_CONTENT
    loaded = load_install_receipt(receipt.receipt_path, game)
    assert loaded == receipt

    rollback_package_install(loaded)

    assert not (game / "game" / "tl" / "turkish" / "script.rpy").exists()
    assert not (game / ACTIVATION_PATH).exists()
    assert not receipt.receipt_path.exists()


def test_existing_files_require_consent_and_are_restored(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)
    existing = game / "game" / "tl" / "turkish" / "script.rpy"
    existing.parent.mkdir(parents=True)
    existing.write_text("original\n", encoding="utf-8")

    with pytest.raises(TranslationPackageError, match="replace-existing"):
        plan_package_install(built.package_path, game)

    receipt = apply_package_install(
        plan_package_install(built.package_path, game, replace_existing=True)
    )
    assert existing.read_text(encoding="utf-8") != "original\n"

    rollback_package_install(receipt)

    assert existing.read_text(encoding="utf-8") == "original\n"


def test_install_rejects_stale_plan(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)
    plan = plan_package_install(built.package_path, game)
    target = game / "game" / "tl" / "turkish" / "script.rpy"
    target.parent.mkdir(parents=True)
    target.write_text("someone else wrote here", encoding="utf-8")

    with pytest.raises(TranslationPackageError, match="plan sonrasında"):
        apply_package_install(plan)


def test_rollback_refuses_a_modified_installed_file(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)
    receipt = apply_package_install(plan_package_install(built.package_path, game))
    target = game / "game" / "tl" / "turkish" / "script.rpy"
    target.write_text("user edit", encoding="utf-8")

    with pytest.raises(TranslationPackageError, match="sonradan değişti"):
        rollback_package_install(receipt)

    assert target.read_text(encoding="utf-8") == "user edit"
    assert receipt.receipt_path.exists()


def test_receipt_cannot_redirect_backup_outside_game(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)
    receipt = apply_package_install(plan_package_install(built.package_path, game))
    raw = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    raw["files"][0]["created_new_file"] = False
    raw["files"][0]["backup_path"] = str(tmp_path / "outside.rpy")
    receipt.receipt_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(TranslationPackageError, match="dışında"):
        load_install_receipt(receipt.receipt_path, game)


def test_manifest_name_is_not_an_install_target(tmp_path: Path) -> None:
    built = build_translation_package(_workspace(tmp_path))
    game = _game(tmp_path)

    plan = plan_package_install(built.package_path, game)

    assert MANIFEST_PATH not in {target.relative_path for target in plan.targets}
