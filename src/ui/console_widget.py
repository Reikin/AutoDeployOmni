from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import pyqtSlot, Qt

class ConsoleWidget(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("background-color: black; color: white;")
        font = QFont("Consolas", 10)
        self.setFont(font)
    
    @pyqtSlot(str)
    def append_log(self, text):
        self.appendPlainText(text)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear_log(self):
        self.clear()
