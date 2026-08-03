from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget
from mcw_core import CorePaths, MCWCore, LaunchRequest

class Worker(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    progress = Signal(object)

    def __init__(self, task):
        super().__init__()
        self.task = task

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(self.task(self.progress.emit))
        except Exception as error:
            self.failed.emit(error)

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
        self.instances = QComboBox()
        self.instances.addItems([item.name for item in self.core.instances.list()])
        self.status = QLabel("Ready")
        self.launch = QPushButton("Launch")
        self.launch.clicked.connect(self.start_launch)
        layout = QVBoxLayout(self)
        layout.addWidget(self.instances)
        layout.addWidget(self.status)
        layout.addWidget(self.launch)

    def start_launch(self):
        name = self.instances.currentText()
        self.thread = QThread(self)
        self.worker = Worker(lambda progress: self._launch(name, progress))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(lambda event: self.status.setText(f"{event.stage.value}: {event.message}"))
        self.worker.succeeded.connect(lambda result: self.status.setText(f"Started {result.minecraft_version}"))
        self.worker.failed.connect(lambda error: self.status.setText(f"{type(error).__name__}: {error}"))
        self.worker.succeeded.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.start()

    def _launch(self, name, progress):
        self.core.operations.begin()
        try:
            return self.core.launch(LaunchRequest(instance=name, offline_username="Player", on_progress=progress))
        finally:
            self.core.operations.finish()

app = QApplication([])
window = Window()
window.show()
app.exec()
