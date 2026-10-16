"""PySide6 single-window beta shell using the shared RenTR core."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from rentr.desktop.controller import DesktopController, DesktopSnapshot, DesktopState
from rentr.desktop.workflow import (
    DesktopProjectPreview,
    PreparedProject,
    apply_desktop_project_preview,
    prepare_game_for_desktop,
    preview_project_translation,
)
from rentr.local_models import (
    OllamaProvider,
    QualityProfile,
    build_ollama_provider,
)
from rentr.mod_package import (
    InstallReceipt,
    apply_package_install,
    build_translation_package,
    plan_package_install,
    rollback_package_install,
)
from rentr.providers import OpenAICompatibleProvider
from rentr.renpy_cli import TargetPlatform
from rentr.triage import requires_provider_translation

_STYLE = """
QWidget { background: #111318; color: #eef0f5; font-size: 13px; }
QMainWindow { background: #111318; }
QFrame#card { background: #1a1e26; border: 1px solid #2a303c; border-radius: 10px; }
QLineEdit, QComboBox, QTextEdit, QTableWidget {
  background: #151922; border: 1px solid #323947; border-radius: 7px; padding: 7px;
}
QPushButton { background: #2b65f9; border: 0; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #3c73ff; }
QPushButton:disabled { background: #303541; color: #777e8e; }
QPushButton#secondary { background: #252b36; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#muted { color: #9da5b5; }
QProgressBar { background: #252b36; border: 0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #2b65f9; border-radius: 5px; }
"""


class MainWindow(QMainWindow):
    """One screen: selection, status, provider, preview and review stay visible."""

    def __init__(self, controller: DesktopController | None = None) -> None:
        super().__init__()
        self.controller = controller or DesktopController()
        self._prepared_project: PreparedProject | None = None
        self._pending_preview: DesktopProjectPreview | None = None
        self._last_install: InstallReceipt | None = None
        self.setWindowTitle("RenTR — Türkçe Yerelleştirme")
        self.setMinimumSize(1050, 720)
        self.setStyleSheet(_STYLE)
        self._build_ui()
        self._render(self.controller.snapshot)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("singleScreenRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("RenTR")
        title.setObjectName("title")
        subtitle = QLabel("Ren'Py oyunlarını güvenli çalışma kopyasında Türkçeleştir")
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        select_card = QFrame()
        select_card.setObjectName("card")
        select_layout = QGridLayout(select_card)
        select_layout.addWidget(QLabel("Oyun klasörü"), 0, 0)
        self.game_path = QLineEdit()
        self.game_path.setObjectName("gamePath")
        self.game_path.setPlaceholderText("İndirdiğin oyunun ana klasörü")
        select_layout.addWidget(self.game_path, 1, 0)
        browse = QPushButton("Seç")
        browse.setObjectName("secondary")
        browse.clicked.connect(self._choose_game)
        select_layout.addWidget(browse, 1, 1)
        inspect_button = QPushButton("Oyunu Analiz Et")
        inspect_button.clicked.connect(self._inspect_game)
        select_layout.addWidget(inspect_button, 1, 2)
        select_layout.addWidget(QLabel("İzole çalışma alanı"), 2, 0)
        self.workspace_path = QLineEdit()
        self.workspace_path.setPlaceholderText("Orijinal oyunun dışında yeni bir klasör")
        select_layout.addWidget(self.workspace_path, 3, 0)
        workspace_browse = QPushButton("Seç")
        workspace_browse.setObjectName("secondary")
        workspace_browse.clicked.connect(self._choose_workspace)
        select_layout.addWidget(workspace_browse, 3, 1)
        select_layout.addWidget(QLabel("Ren'Py SDK (kaynak oyun için)"), 2, 2)
        self.sdk_path = QLineEdit()
        self.sdk_path.setPlaceholderText("renpy-sdk klasörü")
        select_layout.addWidget(self.sdk_path, 3, 2)
        self.prepare_button = QPushButton("Güvenli Kopyayı Hazırla")
        self.prepare_button.setObjectName("secondary")
        self.prepare_button.clicked.connect(self._prepare_game)
        select_layout.addWidget(self.prepare_button, 3, 3)
        layout.addWidget(select_card)

        status_row = QHBoxLayout()
        self.mode_value = self._status_card(status_row, "Oyun modu", "—")
        self.units_value = self._status_card(status_row, "Toplam birim", "0")
        self.provider_units_value = self._status_card(status_row, "AI adayı", "0")
        self.safety_value = self._status_card(status_row, "Orijinal oyun", "Dokunulmayacak")
        layout.addLayout(status_row)

        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QGridLayout(controls)
        controls_layout.addWidget(QLabel("Çeviri sağlayıcısı"), 0, 0)
        self.provider = QComboBox()
        self.provider.addItems(("Yerel Ollama — ücretsiz", "Haricî API — kendi anahtarın"))
        controls_layout.addWidget(self.provider, 1, 0)
        controls_layout.addWidget(QLabel("Kalite"), 0, 1)
        self.quality = QComboBox()
        self.quality.addItems(("Dengeli", "Hızlı", "Yüksek kalite"))
        controls_layout.addWidget(self.quality, 1, 1)
        controls_layout.addWidget(QLabel("Model"), 0, 2)
        self.model = QLineEdit("qwen2.5:7b")
        controls_layout.addWidget(self.model, 1, 2)
        layout.addWidget(controls)

        action_row = QHBoxLayout()
        self.preview_button = QPushButton("Çevir ve Önizle")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._preview_translation)
        action_row.addWidget(self.preview_button)
        self.apply_button = QPushButton("Onayla ve Oyuna Kur")
        self.apply_button.setObjectName("secondary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_preview)
        action_row.addWidget(self.apply_button)
        self.rollback_button = QPushButton("Son Kurulumu Geri Al")
        self.rollback_button.setObjectName("secondary")
        self.rollback_button.setEnabled(False)
        self.rollback_button.clicked.connect(self._rollback_install)
        action_row.addWidget(self.rollback_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.review_table = QTableWidget(0, 4)
        self.review_table.setObjectName("reviewTable")
        self.review_table.setHorizontalHeaderLabels(("Risk", "Konuşmacı", "Kaynak", "Türkçe"))
        header = self.review_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.review_table, 1)

        self.activity = QTextEdit()
        self.activity.setObjectName("activityLog")
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(105)
        layout.addWidget(self.activity)
        self.setCentralWidget(root)

    @staticmethod
    def _status_card(row: QHBoxLayout, label: str, value: str) -> QLabel:
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        caption = QLabel(label)
        caption.setObjectName("muted")
        result = QLabel(value)
        card_layout.addWidget(caption)
        card_layout.addWidget(result)
        row.addWidget(card)
        return result

    def _choose_game(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Ren'Py oyun klasörünü seç")
        if selected:
            self.game_path.setText(selected)
            game = Path(selected)
            self.workspace_path.setText(str(game.parent / f"{game.name}-RenTR-Work"))

    def _choose_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Çalışma alanının üst klasörünü seç")
        if selected:
            game_name = Path(self.game_path.text().strip() or "RenPy-Game").name
            self.workspace_path.setText(str(Path(selected) / f"{game_name}-RenTR-Work"))

    def _inspect_game(self) -> None:
        path = self.game_path.text().strip()
        if not path:
            QMessageBox.warning(self, "RenTR", "Önce oyun klasörünü seç.")
            return
        self._prepared_project = None
        self._pending_preview = None
        try:
            snapshot = self.controller.inspect(Path(path))
        except (OSError, UnicodeError, ValueError) as error:
            snapshot = self.controller.set_state(DesktopState.ERROR, str(error))
        self._render(snapshot)

    def _prepare_game(self) -> None:
        game_text = self.game_path.text().strip()
        workspace_text = self.workspace_path.text().strip()
        if not game_text or not workspace_text:
            QMessageBox.warning(self, "RenTR", "Oyun ve izole çalışma alanını seç.")
            return
        self._prepared_project = None
        self._pending_preview = None
        self.progress.setRange(0, 0)
        QApplication.processEvents()
        try:
            prepared = prepare_game_for_desktop(
                Path(game_text),
                Path(workspace_text),
                sdk_root=Path(self.sdk_path.text()) if self.sdk_path.text().strip() else None,
                target_platform=(
                    TargetPlatform.WINDOWS if os.name == "nt" else TargetPlatform.POSIX
                ),
            )
            self._prepared_project = prepared
            snapshot = self.controller.load_templates(prepared.templates)
        except (OSError, UnicodeError, ValueError) as error:
            snapshot = self.controller.set_state(DesktopState.ERROR, str(error))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._render(snapshot)

    def _quality_profile(self) -> QualityProfile:
        return {
            0: QualityProfile.BALANCED,
            1: QualityProfile.FAST,
            2: QualityProfile.HIGH,
        }[self.quality.currentIndex()]

    def _preview_translation(self) -> None:
        snapshot = self.controller.snapshot
        if snapshot.template_path is None or not self.workspace_path.text().strip():
            QMessageBox.warning(self, "RenTR", "Önce güvenli çalışma kopyasını hazırla.")
            return
        provider_units = sum(
            requires_provider_translation(unit.source_text) for unit in snapshot.units
        )
        if provider_units > 500:
            QMessageBox.warning(
                self,
                "RenTR — Pilot gerekli",
                f"{provider_units} AI adayı bulundu. Tam çeviri güvenlik nedeniyle başlatılmadı. "
                "Önce pilot-report ve pilot-translate ile en fazla 100 birimlik kabul testi yap.",
            )
            return
        self.progress.setRange(0, 0)
        self._pending_preview = None
        QApplication.processEvents()
        provider: OllamaProvider | OpenAICompatibleProvider | None = None
        try:
            if self.provider.currentIndex() == 0:
                provider = build_ollama_provider(
                    model=self.model.text().strip(),
                    quality=self._quality_profile(),
                )
            else:
                api_key = os.environ.get("RENTR_API_KEY", "")
                base_url = os.environ.get("RENTR_PROVIDER_URL", "")
                if not api_key or not base_url:
                    raise ValueError("Haricî API için RENTR_API_KEY ve RENTR_PROVIDER_URL gerekli")
                provider = OpenAICompatibleProvider(
                    base_url=base_url,
                    api_key=api_key,
                    model=self.model.text().strip(),
                )
            templates = (
                self._prepared_project.templates
                if self._prepared_project is not None
                else (snapshot.template_path,)
            )
            self._pending_preview = preview_project_translation(
                templates,
                Path(self.workspace_path.text()),
                provider=provider,
            )
            self.controller.set_state(DesktopState.PREVIEW, "Çeviri önizlemesi hazır")
            self._render_review(self._pending_preview)
            self.activity.setPlainText(self._pending_preview.preview_diff)
            self.apply_button.setEnabled(True)
        except (OSError, UnicodeError, ValueError) as error:
            self.controller.set_state(DesktopState.ERROR, str(error))
            self.activity.setPlainText(str(error))
        finally:
            if provider is not None:
                provider.close()
            self.progress.setRange(0, 100)
            self.progress.setValue(100 if self._pending_preview is not None else 0)

    def _render_review(self, preview: DesktopProjectPreview) -> None:
        self.review_table.setRowCount(len(preview.review_queue))
        for row, item in enumerate(preview.review_queue):
            speaker = item.unit_id.split("_")[0] if "_" in item.unit_id else "—"
            values = (str(item.score), speaker, item.source_text, item.translated_text)
            for column, value in enumerate(values):
                self.review_table.setItem(row, column, QTableWidgetItem(value))

    def _apply_preview(self) -> None:
        if self._pending_preview is None:
            return
        try:
            receipts = apply_desktop_project_preview(self._pending_preview)
            built = build_translation_package(Path(self.workspace_path.text()))
            install_plan = plan_package_install(
                built.package_path,
                Path(self.game_path.text()),
                replace_existing=True,
            )
            collision_note = (
                f"\n{len(install_plan.collisions)} mevcut dosya önce yedeklenecek."
                if install_plan.collisions
                else ""
            )
            answer = QMessageBox.question(
                self,
                "RenTR — Oyuna kur",
                f"{len(install_plan.targets)} doğrulanmış dosya gerçek oyuna kurulacak."
                f"{collision_note}\nKurulum kaydıyla geri alınabilir. Devam edilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is QMessageBox.StandardButton.Yes:
                self._last_install = apply_package_install(install_plan)
                message = (
                    f"Türkçe paket oyuna kuruldu. Kayıt: "
                    f"{self._last_install.receipt_path}"
                )
                self.safety_value.setText("Yedekli kurulum")
                self.rollback_button.setEnabled(True)
            else:
                message = f"Paket hazır, oyun değiştirilmedi: {built.package_path}"
            self.controller.set_state(DesktopState.COMPLETE, message)
            self.activity.setPlainText(
                f"{message}\nÇalışma alanında hazırlanan dosya: {receipts[0].output_path}"
            )
            self.apply_button.setEnabled(False)
        except (OSError, ValueError) as error:
            self.controller.set_state(DesktopState.ERROR, str(error))
            self.activity.setPlainText(str(error))

    def _rollback_install(self) -> None:
        if self._last_install is None:
            return
        answer = QMessageBox.question(
            self,
            "RenTR — Geri al",
            "Son RenTR kurulumu geri alınacak. Kurulan dosyalar sonradan değiştiyse işlem "
            "güvenlik için reddedilir. Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            rollback_package_install(self._last_install)
            self._last_install = None
            self.rollback_button.setEnabled(False)
            self.safety_value.setText("Kurulum geri alındı")
            self.controller.set_state(DesktopState.COMPLETE, "Son kurulum güvenle geri alındı")
            self.activity.setPlainText(self.controller.snapshot.message)
        except (OSError, ValueError) as error:
            self.controller.set_state(DesktopState.ERROR, str(error))
            self.activity.setPlainText(str(error))

    def _render(self, snapshot: DesktopSnapshot) -> None:
        mode = snapshot.game.mode.value if snapshot.game is not None else "—"
        self.mode_value.setText(mode)
        self.units_value.setText(str(len(snapshot.units)))
        provider_units = sum(
            requires_provider_translation(unit.source_text)
            for unit in snapshot.units
            if unit.translated_text is None
        )
        self.provider_units_value.setText(str(provider_units))
        self.preview_button.setEnabled(snapshot.state is DesktopState.READY)
        self.activity.setPlainText(snapshot.message)
        self.review_table.setRowCount(len(snapshot.units))
        for row, unit in enumerate(snapshot.units):
            values = ("—", unit.speaker or "Anlatıcı", unit.source_text, unit.translated_text or "")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.review_table.setItem(row, column, item)


def _dark_palette(application: QApplication) -> None:
    palette = application.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#111318"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eef0f5"))
    application.setPalette(palette)


def create_application() -> QApplication:
    instance = QApplication.instance()
    application = cast(QApplication, instance) if instance is not None else QApplication(sys.argv)
    _dark_palette(application)
    return application


def run() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    application = create_application()
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(run())
