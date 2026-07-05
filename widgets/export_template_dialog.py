"""
widgets/export_template_dialog.py — Selección de grupos para exportar plantilla Excel.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import Qt


class ExportTemplateDialog(QDialog):
    """Permite al usuario elegir qué grupos incluir en la plantilla."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("Exportar plantilla de clonación")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        lbl = QLabel(
            "Selecciona los grupos que quieres incluir en la plantilla Excel.\n"
            "Cada grupo exportado genera una fila de ejemplo (origen) con sus "
            "datos actuales, lista para duplicar y rellenar como destino.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#1a2a3a; padding:4px;")
        lay.addWidget(lbl)

        # Botones seleccionar todo / ninguno
        hbox = QHBoxLayout()
        btn_all  = QPushButton("Seleccionar todos")
        btn_none = QPushButton("Deseleccionar todos")
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._select_none)
        hbox.addWidget(btn_all)
        hbox.addWidget(btn_none)
        hbox.addStretch()
        lay.addLayout(hbox)

        # Lista de grupos
        self._lst = QListWidget()
        self._lst.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)

        for g in self.doc.groups:
            base  = g.sheet_number_base
            n     = len(g.sheets)
            label = (f"H{base:02d}"
                     + (f"–H{base+n-1:02d}" if n > 1 else "")
                     + f"  |  {g.kks or '—'}"
                     + (f"  –  {g.description}" if g.description else ""))
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, g.group_id)
            self._lst.addItem(item)

        lay.addWidget(self._lst, stretch=1)

        # Contador
        self._lbl_count = QLabel()
        self._update_count()
        self._lst.itemChanged.connect(lambda _: self._update_count())
        lay.addWidget(self._lbl_count)

        # Botones OK / Cancelar
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Exportar plantilla…")
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _select_all(self):
        for i in range(self._lst.count()):
            self._lst.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        for i in range(self._lst.count()):
            self._lst.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _update_count(self):
        n = sum(1 for i in range(self._lst.count())
                if self._lst.item(i).checkState() == Qt.CheckState.Checked)
        self._lbl_count.setText(
            f"<b>{n}</b> grupo(s) seleccionado(s) de {self._lst.count()}")

    def selected_group_ids(self) -> list[str]:
        result = []
        for i in range(self._lst.count()):
            item = self._lst.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _on_accept(self):
        if not self.selected_group_ids():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Sin selección",
                                "Selecciona al menos un grupo para exportar.")
            return
        self.accept()
