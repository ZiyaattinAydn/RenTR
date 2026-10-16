from __future__ import annotations

from pathlib import Path

import pytest

from rentr.writer import (
    SafeWriteError,
    apply_safe_write,
    plan_safe_write,
    rollback_safe_write,
)


def test_new_file_is_previewed_written_atomically_and_removed_on_rollback(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "game" / "tl" / "turkish" / "script.rpy"

    plan = plan_safe_write(output, "Merhaba\n", workspace_root=workspace)

    assert not output.exists()
    assert "/dev/null" in plan.preview_diff
    receipt = apply_safe_write(plan)
    assert output.read_text(encoding="utf-8") == "Merhaba\n"
    assert not output.with_name(".script.rpy.rentr-partial").exists()

    rollback_safe_write(receipt)
    assert not output.exists()


def test_overwrite_creates_backup_and_rollback_restores_original(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    output = workspace / "game" / "tl" / "turkish" / "script.rpy"
    output.parent.mkdir(parents=True)
    output.write_text("Original\n", encoding="utf-8")

    receipt = apply_safe_write(
        plan_safe_write(output, "Translated\n", workspace_root=workspace)
    )

    assert receipt.backup_path is not None
    assert receipt.backup_path.read_text(encoding="utf-8") == "Original\n"
    rollback_safe_write(receipt)
    assert output.read_text(encoding="utf-8") == "Original\n"


def test_rejects_output_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SafeWriteError, match="dışında"):
        plan_safe_write(tmp_path / "game" / "script.rpy", "text", workspace_root=workspace)


def test_rejects_stale_plan_without_overwriting_external_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "script.rpy"
    output.write_text("first", encoding="utf-8")
    plan = plan_safe_write(output, "second", workspace_root=workspace)
    output.write_text("external", encoding="utf-8")

    with pytest.raises(SafeWriteError, match="değişti"):
        apply_safe_write(plan)

    assert output.read_text(encoding="utf-8") == "external"


def test_rejects_rollback_after_external_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "script.rpy"
    output.write_text("first", encoding="utf-8")
    receipt = apply_safe_write(plan_safe_write(output, "second", workspace_root=workspace))
    output.write_text("external", encoding="utf-8")

    with pytest.raises(SafeWriteError, match="değişti"):
        rollback_safe_write(receipt)

    assert output.read_text(encoding="utf-8") == "external"
