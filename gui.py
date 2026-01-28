import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class LabelOpsMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LabelOps")

        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_status_bar()

    def _setup_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)
        file_menu = QMenu("File", self)
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        help_menu = QMenu("Help", self)
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._handle_about)

        menu_bar.addMenu(file_menu)
        menu_bar.addMenu(help_menu)
        self.setMenuBar(menu_bar)

    def _setup_tool_bar(self) -> None:
        tool_bar = QToolBar("Main", self)
        tool_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        import_action = tool_bar.addAction("Import")
        import_action.triggered.connect(lambda: self._log_action("Import"))

        process_action = tool_bar.addAction("Process")
        process_action.triggered.connect(lambda: self._log_action("Process"))

        settings_action = tool_bar.addAction("Settings")
        settings_action.triggered.connect(lambda: self._log_action("Settings"))

        self.addToolBar(tool_bar)

    def _setup_central_widget(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        self.address_text = QTextEdit(central_widget)
        self.address_text.setPlaceholderText("Paste raw address text here...")

        generate_button = QPushButton("Generate XLSX", central_widget)
        generate_button.clicked.connect(lambda: self._log_action("Generate XLSX"))

        layout.addWidget(self.address_text)
        layout.addWidget(generate_button)
        self.setCentralWidget(central_widget)

    def _setup_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)

    def _handle_about(self) -> None:
        self._log_action("About")
        self.statusBar().showMessage("LabelOps GUI prototype")

    def _log_action(self, action: str) -> None:
        print(f"{action} clicked")
        self.statusBar().showMessage(f"{action} clicked")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LabelOpsMainWindow()
    window.show()
    sys.exit(app.exec())
