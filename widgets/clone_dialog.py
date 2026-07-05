"""
widgets/clone_dialog.py — Diálogo para clonar un grupo del documento.

Controles:
  - Selector de grupo a clonar
  - SpinBox editable para el número de hoja inicial del clon
  - Rejilla N×2 de reglas búsqueda→reemplazo (wildcard * y ?)
  - Botón "Añadir fila" y Cancelar / Ejecutar
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QSizePolicy, QSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

_INIT_ROWS = 5


class CloneGroupDialog(QDialog):

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Clonar grupo")
        self.setMinimumWidth(640)
        self.setMinimumHeight(460)
        self._build()

    # ── Construcción UI ──────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # Selectores
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._cb_src = QComboBox()
        self._populate_combo()
        form.addRow("Grupo a clonar:", self._cb_src)

        # SpinBox para hoja inicial del clon
        self._spin_base = QSpinBox()
        self._spin_base.setRange(1, 9999)
        self._spin_base.setPrefix("H")
        self._spin_base.setToolTip(
            "Número de hoja de la primera hoja del grupo clonado.\n"
            "Si ya existe un grupo en ese número, los grupos afectados\n"
            "se desplazarán automáticamente para hacer hueco.")
        self._spin_base.setStyleSheet(
            "color:#1a6e3c; font-weight:bold; min-width:80px;")
        self._lbl_info = QLabel()
        self._lbl_info.setStyleSheet("color:#555;")
        hbox_base = QHBoxLayout()
        hbox_base.addWidget(self._spin_base)
        hbox_base.addWidget(self._lbl_info)
        hbox_base.addStretch()
        form.addRow("Hoja inicial del clon:", hbox_base)

        lay.addLayout(form)
        self._cb_src.currentIndexChanged.connect(self._update_suggestion)
        self._spin_base.valueChanged.connect(self._update_info)
        self._update_suggestion()

        # Etiqueta rejilla
        lbl = QLabel(
            "Reglas de sustitución de texto  "
            "<small>(patrón: <b>*</b> = cualquier secuencia, "
            "<b>?</b> = un carácter)</small>")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(lbl)

        # Tabla
        self._table = QTableWidget(_INIT_ROWS, 2)
        self._table.setHorizontalHeaderLabels(["Buscar", "Reemplazar por"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setFont(QFont("Consolas", 9))
        for r in range(_INIT_ROWS):
            for c in range(2):
                self._table.setItem(r, c, QTableWidgetItem(''))
        lay.addWidget(self._table)

        # Botón añadir fila
        btn_add = QPushButton("+ Añadir fila")
        btn_add.setFixedWidth(120)
        btn_add.clicked.connect(self._add_row)
        lay.addWidget(btn_add, alignment=Qt.AlignmentFlag.AlignLeft)

        # Botones OK / Cancelar
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Ejecutar")
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _populate_combo(self):
        doc = self.document
        self._cb_src.clear()
        for gi, g in enumerate(doc.groups):
            base  = g.sheet_number_base
            label = (f"H{base:02d}  "
                     f"{g.description or g.system or g.kks or '(sin título)'}")
            self._cb_src.addItem(label, userData=gi)
        if self._cb_src.count() > 0:
            self._cb_src.setCurrentIndex(0)

    def _update_suggestion(self):
        """Sugiere hoja inicial = última hoja + 1 del documento."""
        doc    = self.document
        src_gi = self._cb_src.currentData()
        if src_gi is None or not doc.groups:
            return
        last = doc.groups[-1]
        suggested = last.sheet_number_base + len(last.sheets)
        self._spin_base.setValue(suggested)
        self._update_info()

    def _update_info(self):
        """Muestra tamaño del grupo a clonar e indica si habrá desplazamiento."""
        doc    = self.document
        src_gi = self._cb_src.currentData()
        if src_gi is None or src_gi >= len(doc.groups):
            self._lbl_info.setText('')
            return

        src_count = len(doc.groups[src_gi].sheets)
        new_base  = self._spin_base.value()
        new_end   = new_base + src_count - 1

        # Buscar conflictos
        conflict_base = None
        for g in doc.groups:
            g_end = g.sheet_number_base + len(g.sheets) - 1
            if g.sheet_number_base <= new_end and g_end >= new_base:
                if conflict_base is None or g.sheet_number_base < conflict_base:
                    conflict_base = g.sheet_number_base

        size_txt = f"{src_count} hoja{'s' if src_count != 1 else ''}"
        if conflict_base is not None:
            shift = new_base + src_count - conflict_base
            self._lbl_info.setText(
                f"({size_txt} — desplaza grupos desde H{conflict_base:02d} +{shift})")
            self._lbl_info.setStyleSheet("color:#b05000; font-style:italic;")
        else:
            self._lbl_info.setText(f"({size_txt} — sin desplazamiento)")
            self._lbl_info.setStyleSheet("color:#1a6e3c; font-style:italic;")

    def _add_row(self):
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(''))
        self._table.setItem(r, 1, QTableWidgetItem(''))

    # ── Acceso a resultados ──────────────────────────────────────────────

    def src_group_idx(self) -> int:
        return self._cb_src.currentData()

    def override_sheet_base(self) -> int:
        return self._spin_base.value()

    def rules(self) -> list[tuple[str, str]]:
        result = []
        for r in range(self._table.rowCount()):
            pat = (self._table.item(r, 0) or QTableWidgetItem('')).text().strip()
            rep = (self._table.item(r, 1) or QTableWidgetItem('')).text().strip()
            if pat or rep:
                result.append((pat, rep))
        return result

    # ── Validación y aceptación ─────────────────────────────────────────

    def _on_accept(self):
        from io_utils.clone_group import validate_rules
        errs = validate_rules(self.rules())
        if errs:
            QMessageBox.warning(self, "Reglas inválidas",
                                "Corrige los siguientes errores:\n\n" +
                                "\n".join(errs))
            return
        self.accept()
