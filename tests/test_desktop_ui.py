from __future__ import annotations

import ast
from pathlib import Path

APP_SOURCE = Path(__file__).parents[1] / "src" / "rentr" / "desktop" / "app.py"


def test_desktop_source_is_one_window_without_page_stack() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    assert "MainWindow" in class_names
    assert "QStackedWidget" not in source
    assert 'root.setObjectName("singleScreenRoot")' in source
    assert "self.review_table = QTableWidget(0, 4)" in source
