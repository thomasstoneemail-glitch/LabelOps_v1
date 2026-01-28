"""LabelOps PySide6 GUI for parsing and processing address batches."""
from __future__ import annotations

import csv
import os
import re
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from PySide6.QtCore import QThread, Qt, QObject, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressDialog,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from app import address_ai, address_parser, clickdrop_xlsx, config, logging_utils, manifest

AI_RISK_LEVELS = ["low", "medium", "high"]
SERVICE_TAG_RE = re.compile(r"\bSERVICE\s*=\s*(\w+)\b", re.IGNORECASE)


@dataclass
class ParsedRecord:
    """Container for parsed record details."""

    record: dict
    matched_tag: Optional[str] = None


def _split_chunks(raw_text: str) -> list[str]:
    return [
        chunk
        for chunk in re.split(r"\n\s*\n+", raw_text.strip())
        if chunk.strip()
    ]


def _find_service_tag(chunk: str, services: Iterable[dict]) -> tuple[str | None, str | None]:
    upper_chunk = chunk.upper()

    service_override = SERVICE_TAG_RE.search(chunk)
    if service_override:
        tag_value = service_override.group(1).strip()
        for service in services:
            trigger = service.get("trigger", {})
            if trigger.get("type") == "tag" and str(trigger.get("tag", "")).upper() == tag_value.upper():
                return service.get("name"), trigger.get("tag")

    for service in services:
        trigger = service.get("trigger", {})
        if trigger.get("type") != "tag":
            continue
        tag = str(trigger.get("tag", "")).strip()
        if not tag:
            continue
        patterns = [
            rf"\b{re.escape(tag)}\b",
            rf"\[{re.escape(tag)}\]",
        ]
        for pattern in patterns:
            if re.search(pattern, upper_chunk, re.IGNORECASE):
                return service.get("name"), tag

    return None, None


def _default_service(services: Iterable[dict], fallback: str) -> str:
    for service in services:
        trigger = service.get("trigger", {})
        if trigger.get("type") == "default":
            return str(service.get("name", fallback))
    return fallback


def parse_records(
    raw_text: str,
    services: list[dict],
    defaults: dict,
) -> list[ParsedRecord]:
    """Parse raw input text into records with service tagging."""
    if not raw_text.strip():
        return []

    parsed: list[ParsedRecord] = []
    fallback_service = str(defaults.get("service", ""))
    default_service = _default_service(services, fallback_service)
    default_weight = defaults.get("weight_kg", 1.0)

    for chunk in _split_chunks(raw_text):
        record_list = address_parser.parse_batch(chunk)
        if not record_list:
            continue
        record = record_list[0]
        service_name, matched_tag = _find_service_tag(chunk, services)
        record["service"] = service_name or default_service
        record["weight_kg"] = default_weight
        if matched_tag:
            existing_notes = record.get("notes", "").strip()
            tag_note = f"Tag matched: {matched_tag}"
            record["notes"] = f"{existing_notes} {tag_note}".strip()
        parsed.append(ParsedRecord(record=record, matched_tag=matched_tag))

    return parsed


def write_tracking_csv(records: list[dict], output_path: str) -> str:
    """Write a tracking CSV for downstream tracking systems."""
    if not records:
        raise ValueError("No records provided for tracking CSV.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "full_name",
        "postcode",
        "service",
        "weight_kg",
        "reference",
        "notes",
        "ai_flag",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})

    return str(path)


def _render_ai_flag(ai_result: address_ai.AIResult | None) -> str:
    if not ai_result or not ai_result.suggestions:
        return "No"
    return "Yes"


def _format_notes(record: dict, ai_result: address_ai.AIResult | None) -> str:
    notes = str(record.get("notes", "")).strip()
    if ai_result and ai_result.suggestions and ai_result.overall_risk in {"medium", "high"}:
        risk_note = f"AI review: {ai_result.overall_risk}"
        notes = f"{notes} {risk_note}".strip()
    return notes


def _now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _log_dir() -> str:
    return os.getenv("LABELOPS_LOG_DIR", r"D:\LabelOps\Logs")


class Worker(QObject):
    """Worker that runs parsing and pipeline operations in a background thread."""

    progress = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        *,
        client_id: str,
        client_settings: dict,
        raw_text: str,
        input_files: list[str],
        use_ai: bool,
        auto_apply_max_risk: str,
        max_ai_calls: int,
        dry_run: bool,
    ) -> None:
        super().__init__()
        self.client_id = client_id
        self.client_settings = client_settings
        self.raw_text = raw_text
        self.input_files = input_files
        self.use_ai = use_ai
        self.auto_apply_max_risk = auto_apply_max_risk
        self.max_ai_calls = max_ai_calls
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            result = self._run_pipeline()
        except Exception as exc:
            detail = "\n".join([
                str(exc),
                traceback.format_exc(),
            ])
            self.failed.emit(detail)
            return
        self.finished.emit(result)

    def _run_pipeline(self) -> dict:
        self.progress.emit("Parsing...")
        parsed = parse_records(
            self.raw_text,
            services=self.client_settings.get("services", []),
            defaults=self.client_settings.get("defaults", {}),
        )
        if not parsed:
            raise ValueError("No valid records were parsed from the input.")

        records = [entry.record for entry in parsed]
        ai_results: list[address_ai.AIResult] = []
        flagged_count = 0
        applied_count = 0

        if self.use_ai:
            self.progress.emit("AI assist...")
            records, ai_results = address_ai.process_batch(
                records,
                max_calls=self.max_ai_calls,
                auto_apply_max_risk=self.auto_apply_max_risk,
            )

            for ai_result in ai_results:
                if ai_result.suggestions:
                    if ai_result.overall_risk in {"medium", "high"}:
                        flagged_count += 1
                    if address_ai.RISK_ORDER.get(ai_result.overall_risk, 2) <= address_ai.RISK_ORDER.get(
                        self.auto_apply_max_risk,
                        0,
                    ):
                        applied_count += 1

        timestamp = _now_timestamp()
        base_name = f"{self.client_id}_{timestamp}"
        folders = self.client_settings.get("folders", {})
        output_xlsx = os.path.join(folders.get("ready_xlsx", ""), f"{base_name}.xlsx")
        tracking_csv = os.path.join(folders.get("tracking_out", ""), f"{base_name}_tracking.csv")
        log_dir = _log_dir()

        if not self.dry_run:
            logging_utils.setup_logging(log_dir)
            self.progress.emit("Writing XLSX...")
            template_path = self.client_settings.get("clickdrop", {}).get("template_path")
            if not template_path:
                template_path = clickdrop_xlsx.generate_clickdrop_xlsx.__defaults__[0]
            clickdrop_xlsx.generate_clickdrop_xlsx(
                records,
                output_xlsx,
                template_path=template_path,
                defaults=self.client_settings.get("defaults", {}),
            )

            self.progress.emit("Writing tracking CSV...")
            ai_lookup = {result.record_id: result for result in ai_results}
            for idx, record in enumerate(records):
                ai_result = ai_lookup.get(str(idx))
                record["ai_flag"] = "Yes" if ai_result and ai_result.suggestions else "No"
            write_tracking_csv(records, tracking_csv)

            self.progress.emit("Writing manifest...")
            ai_summary = manifest.AiSummary(
                enabled=self.use_ai,
                auto_apply_max_risk=self.auto_apply_max_risk,
                flagged_count=flagged_count,
                applied_count=applied_count,
            )
            batch_manifest = manifest.BatchManifest(
                manifest_version="1.0",
                batch_id=str(uuid.uuid4()),
                created_utc=datetime.now(timezone.utc).isoformat(),
                client_id=self.client_id,
                source="gui",
                input_files=self.input_files,
                input_text_sha256=manifest.sha256_text(self.raw_text),
                output_xlsx=output_xlsx,
                output_pdf="",
                record_count=len(records),
                defaults_used=self.client_settings.get("defaults", {}),
                services_used_summary=manifest.compute_services_summary(records),
                ai=ai_summary,
                notes=["Dry run"] if self.dry_run else [],
            )
            manifest_path = manifest.write_manifest(batch_manifest, log_dir)
        else:
            manifest_path = ""

        self.progress.emit("Done")
        return {
            "records": records,
            "ai_results": ai_results,
            "output_xlsx": output_xlsx,
            "tracking_csv": tracking_csv,
            "manifest_path": manifest_path,
            "record_count": len(records),
            "flagged_count": flagged_count,
            "applied_count": applied_count,
            "dry_run": self.dry_run,
        }


class LabelOpsMainWindow(QMainWindow):
    """Main application window for LabelOps GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LabelOps GUI")
        self.setMinimumSize(960, 720)

        self._config: dict[str, Any] | None = None
        self._client_settings: dict[str, Any] | None = None
        self._client_id: str | None = None
        self._selected_input_file: str | None = None
        self._last_output_dir: str | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._worker_thread: QThread | None = None
        self._worker: Worker | None = None

        self._setup_ui()
        self._refresh_clients()

    def _setup_ui(self) -> None:
        central = QWidget(self)
        main_layout = QVBoxLayout(central)

        top_row = QHBoxLayout()
        self.client_combo = QComboBox(self)
        self.refresh_button = QPushButton("Refresh clients", self)
        self.refresh_button.clicked.connect(self._refresh_clients)
        top_row.addWidget(QLabel("Client:", self))
        top_row.addWidget(self.client_combo)
        top_row.addWidget(self.refresh_button)
        top_row.addStretch()

        self.tabs = QTabWidget(self)
        self._setup_input_tabs()

        options_group = QGroupBox("Options", self)
        options_layout = QFormLayout(options_group)
        self.use_ai_checkbox = QCheckBox("Use AI assist", self)
        self.risk_combo = QComboBox(self)
        self.risk_combo.addItems(AI_RISK_LEVELS)
        self.risk_combo.setCurrentText("low")
        self.max_ai_spin = QSpinBox(self)
        self.max_ai_spin.setRange(0, 500)
        self.max_ai_spin.setValue(50)
        self.dry_run_checkbox = QCheckBox("Dry run", self)
        options_layout.addRow(self.use_ai_checkbox)
        options_layout.addRow("Auto-apply max risk", self.risk_combo)
        options_layout.addRow("Max AI calls", self.max_ai_spin)
        options_layout.addRow(self.dry_run_checkbox)

        buttons_row = QHBoxLayout()
        self.preview_button = QPushButton("Parse Preview", self)
        self.process_button = QPushButton("Process Batch", self)
        self.preview_button.clicked.connect(self._handle_preview)
        self.process_button.clicked.connect(self._handle_process)
        buttons_row.addWidget(self.preview_button)
        buttons_row.addWidget(self.process_button)
        buttons_row.addStretch()

        self.table = QTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["#", "Name", "Postcode", "Service", "Weight", "AI Flag", "Notes"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        output_group = QGroupBox("Output", self)
        output_layout = QGridLayout(output_group)
        self.xlsx_label = QLabel("—", self)
        self.tracking_label = QLabel("—", self)
        self.manifest_label = QLabel("—", self)
        output_layout.addWidget(QLabel("XLSX:"), 0, 0)
        output_layout.addWidget(self.xlsx_label, 0, 1)
        output_layout.addWidget(QLabel("Tracking CSV:"), 1, 0)
        output_layout.addWidget(self.tracking_label, 1, 1)
        output_layout.addWidget(QLabel("Manifest:"), 2, 0)
        output_layout.addWidget(self.manifest_label, 2, 1)
        self.open_folder_button = QPushButton("Open Output Folder", self)
        self.copy_paths_button = QPushButton("Copy Paths", self)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.copy_paths_button.clicked.connect(self._copy_paths)
        output_layout.addWidget(self.open_folder_button, 3, 0)
        output_layout.addWidget(self.copy_paths_button, 3, 1)

        main_layout.addLayout(top_row)
        main_layout.addWidget(self.tabs)
        main_layout.addWidget(options_group)
        main_layout.addLayout(buttons_row)
        main_layout.addWidget(self.table)
        main_layout.addWidget(output_group)
        self.setCentralWidget(central)

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.client_combo.currentIndexChanged.connect(self._on_client_change)
        self.tabs.currentChanged.connect(self._update_process_enabled)
        self.paste_input.textChanged.connect(self._update_process_enabled)
        self.file_preview.textChanged.connect(self._update_process_enabled)

    def _setup_input_tabs(self) -> None:
        paste_tab = QWidget(self)
        paste_layout = QVBoxLayout(paste_tab)
        self.paste_input = QPlainTextEdit(self)
        self.paste_input.setPlaceholderText("Paste raw Telegram addresses here...")
        paste_layout.addWidget(self.paste_input)
        self.tabs.addTab(paste_tab, "Paste Input")

        file_tab = QWidget(self)
        file_layout = QVBoxLayout(file_tab)
        file_picker_layout = QHBoxLayout()
        self.file_path_display = QLineEdit(self)
        self.file_path_display.setReadOnly(True)
        self.file_button = QPushButton("Browse...", self)
        self.file_button.clicked.connect(self._load_file)
        file_picker_layout.addWidget(self.file_path_display)
        file_picker_layout.addWidget(self.file_button)
        self.file_preview = QPlainTextEdit(self)
        self.file_preview.setReadOnly(True)
        self.file_preview.setPlaceholderText("Loaded file preview will appear here...")
        file_layout.addLayout(file_picker_layout)
        file_layout.addWidget(self.file_preview)
        self.tabs.addTab(file_tab, "Load File")

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def _refresh_clients(self) -> None:
        try:
            cfg = config.load_config()
            config.validate_config(cfg)
        except FileNotFoundError:
            self._show_error(
                "Missing clients.yaml",
                (
                    f"No clients.yaml found at {config.DEFAULT_CONFIG_PATH}.\n"
                    "Create the file or update the default path in app/config.py."
                ),
            )
            return
        except Exception as exc:
            self._show_error("Config error", str(exc))
            return

        self._config = cfg
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        for client_id in config.list_clients(cfg):
            client_cfg = config.get_client(cfg, client_id)
            display_name = str(client_cfg.get("display_name", client_id))
            self.client_combo.addItem(f"{display_name} ({client_id})", userData=client_id)
        self.client_combo.blockSignals(False)
        if self.client_combo.count() > 0:
            self.client_combo.setCurrentIndex(0)
            self._on_client_change()
        else:
            self._show_error("No clients", "No clients were found in clients.yaml.")

    def _on_client_change(self) -> None:
        client_id = self.client_combo.currentData()
        if not client_id or not self._config:
            return
        self._client_id = str(client_id)
        self._client_settings = config.resolve_client_settings(self._config, self._client_id)

    def _load_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select input file", "", "Text Files (*.txt)")
        if not file_path:
            return
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except Exception as exc:
            self._show_error("File error", f"Failed to read file: {exc}")
            return
        self._selected_input_file = file_path
        self.file_path_display.setText(file_path)
        self.file_preview.setPlainText(text)
        self.tabs.setCurrentIndex(1)
        self._update_process_enabled()

    def _get_input_text(self) -> str:
        if self.tabs.currentIndex() == 0:
            return self.paste_input.toPlainText().strip()
        return self.file_preview.toPlainText().strip()

    def _update_process_enabled(self) -> None:
        has_text = bool(self._get_input_text())
        self.process_button.setEnabled(has_text)
        self.preview_button.setEnabled(has_text)

    def _build_records_for_preview(self) -> list[ParsedRecord]:
        if not self._client_settings:
            raise ValueError("Client configuration is not loaded.")
        return parse_records(
            self._get_input_text(),
            services=self._client_settings.get("services", []),
            defaults=self._client_settings.get("defaults", {}),
        )

    def _handle_preview(self) -> None:
        try:
            parsed = self._build_records_for_preview()
        except Exception as exc:
            self._show_error("Preview error", str(exc))
            return

        if not parsed:
            self._show_info("Preview", "No records were parsed from the input.")
            return

        sample = parsed[0].record
        self._populate_table([entry.record for entry in parsed], [])
        message = (
            f"Parsed {len(parsed)} records.\n"
            f"Sample: {sample.get('full_name', '')} ({sample.get('postcode', '')})"
        )
        self.status_bar.showMessage(message)
        self._show_info("Preview", message)

    def _handle_process(self) -> None:
        if not self._client_settings or not self._client_id:
            self._show_error("Missing client", "Select a client before processing.")
            return
        raw_text = self._get_input_text()
        if not raw_text:
            self._show_error("Input required", "Provide address input before processing.")
            return
        if not self.dry_run_checkbox.isChecked():
            template_path = self._client_settings.get("clickdrop", {}).get("template_path")
            if not template_path:
                template_path = clickdrop_xlsx.generate_clickdrop_xlsx.__defaults__[0]
            if not Path(template_path).exists():
                self._show_error(
                    "Missing template",
                    f"Click & Drop template not found at: {template_path}",
                )
                return

        input_files = [self._selected_input_file] if self._selected_input_file else []

        self._progress_dialog = QProgressDialog("Starting...", None, 0, 0, self)
        self._progress_dialog.setWindowTitle("Processing")
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setCancelButton(None)
        self._progress_dialog.show()

        self.process_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        self._worker_thread = QThread(self)
        self._worker = Worker(
            client_id=self._client_id,
            client_settings=self._client_settings,
            raw_text=raw_text,
            input_files=input_files,
            use_ai=self.use_ai_checkbox.isChecked(),
            auto_apply_max_risk=self.risk_combo.currentText(),
            max_ai_calls=self.max_ai_spin.value(),
            dry_run=self.dry_run_checkbox.isChecked(),
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _on_worker_progress(self, message: str) -> None:
        self.status_bar.showMessage(message)
        if self._progress_dialog:
            self._progress_dialog.setLabelText(message)

    def _cleanup_worker(self) -> None:
        if self._worker:
            self._worker.deleteLater()
        if self._worker_thread:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None
        if self._progress_dialog:
            self._progress_dialog.close()
        self._progress_dialog = None
        self._update_process_enabled()

    def _on_worker_failed(self, message: str) -> None:
        self._show_error("Processing failed", message)

    def _on_worker_finished(self, result: dict) -> None:
        records = result.get("records", [])
        ai_results = result.get("ai_results", [])
        self._populate_table(records, ai_results)

        self.xlsx_label.setText(result.get("output_xlsx", "—"))
        self.tracking_label.setText(result.get("tracking_csv", "—"))
        self.manifest_label.setText(result.get("manifest_path", "—"))
        output_path = result.get("output_xlsx") or result.get("tracking_csv")
        if output_path:
            self._last_output_dir = str(Path(output_path).parent)

        if self.use_ai_checkbox.isChecked() and result.get("flagged_count", 0) > 0:
            flagged = result.get("flagged_count", 0)
            QMessageBox.warning(
                self,
                "AI Review Needed",
                f"AI flagged {flagged} record(s) as medium/high risk.",
            )

        summary = (
            f"Processed {result.get('record_count', 0)} records. "
            f"XLSX: {result.get('output_xlsx', 'n/a')}"
        )
        self.status_bar.showMessage(summary)
        self._show_info("Done", summary)

    def _populate_table(
        self,
        records: list[dict],
        ai_results: list[address_ai.AIResult],
    ) -> None:
        self.table.setRowCount(0)
        ai_lookup = {result.record_id: result for result in ai_results}

        for idx, record in enumerate(records, start=1):
            self.table.insertRow(self.table.rowCount())
            ai_result = ai_lookup.get(str(idx - 1))
            items = [
                QTableWidgetItem(str(idx)),
                QTableWidgetItem(str(record.get("full_name", ""))),
                QTableWidgetItem(str(record.get("postcode", ""))),
                QTableWidgetItem(str(record.get("service", ""))),
                QTableWidgetItem(str(record.get("weight_kg", ""))),
                QTableWidgetItem(_render_ai_flag(ai_result)),
                QTableWidgetItem(_format_notes(record, ai_result)),
            ]
            for column, item in enumerate(items):
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(self.table.rowCount() - 1, column, item)

    def _open_output_folder(self) -> None:
        if not self._last_output_dir:
            self._show_info("No output", "No output folder is available yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_dir))

    def _copy_paths(self) -> None:
        paths = [
            self.xlsx_label.text(),
            self.tracking_label.text(),
            self.manifest_label.text(),
        ]
        clipboard = QGuiApplication.clipboard()
        clipboard.setText("\n".join(path for path in paths if path and path != "—"))
        self.status_bar.showMessage("Output paths copied to clipboard")


def main() -> None:
    """Entry point for the LabelOps GUI."""
    app = QApplication(sys.argv)
    window = LabelOpsMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
