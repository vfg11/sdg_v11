"""
widgets/coherence_dialog.py — Diálogo de análisis de coherencia del documento.

Muestra la lista de incidencias detectadas, permite navegar a cada una
y reparar automáticamente las que tienen corrección clara.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressDialog, QMessageBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon

_ICONS = {'error': '🔴', 'warning': '🟡', 'info': '🔵'}
_COLORS = {
    'error':   QColor('#FFF0F0'),
    'warning': QColor('#FFFBEC'),
    'info':    QColor('#F0F4FF'),
}
_COL_SEV  = 0
_COL_CAT  = 1
_COL_MSG  = 2
_COL_FIX  = 3


class CoherenceDialog(QDialog):
    """
    Señales:
        navigate_requested(sheet_idx, slot_side, slot_idx)
    """
    navigate_requested = pyqtSignal(int, str, int)

    def __init__(self, document, scene, navigate_fn, parent=None):
        super().__init__(parent)
        self._doc      = document
        self._scene    = scene
        self._nav_fn   = navigate_fn   # callable(flat_idx)
        self._issues   = []

        self.setWindowTitle('Análisis de coherencia del documento')
        self.setMinimumSize(820, 520)
        self._build()
        self._run_analysis()

    # ── Construcción UI ───────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # Cabecera
        hdr = QHBoxLayout()
        self._lbl_summary = QLabel('Analizando…')
        self._lbl_summary.setFont(QFont('Segoe UI', 10))
        hdr.addWidget(self._lbl_summary)
        hdr.addStretch()
        btn_rerun = QPushButton('🔄  Volver a analizar')
        btn_rerun.clicked.connect(self._run_analysis)
        hdr.addWidget(btn_rerun)
        lay.addLayout(hdr)

        # Tabla
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ['Severidad', 'Categoría', 'Descripción', 'Acción'])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.setSortingEnabled(False)
        self._table.setFont(QFont('Segoe UI', 9))
        self._table.doubleClicked.connect(self._on_double_click)
        lay.addWidget(self._table)

        # Botones inferiores
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)
        bot = QHBoxLayout()
        self._btn_fix_all = QPushButton('🔧  Reparar todo lo reparable')
        self._btn_fix_all.clicked.connect(self._fix_all)
        bot.addWidget(self._btn_fix_all)
        bot.addStretch()
        btn_close = QPushButton('Cerrar')
        btn_close.clicked.connect(self.accept)
        bot.addWidget(btn_close)
        lay.addLayout(bot)

    # ── Análisis ──────────────────────────────────────────────────────────

    def _run_analysis(self):
        from io_utils.coherence import analyze
        from io_utils.db_io import load_sheet_content

        # Asegurar que todas las hojas están cargadas
        for sheet, _ in self._doc.flat_sheets():
            if not getattr(sheet, '_loaded', False):
                load_sheet_content(sheet)

        self._issues = analyze(self._doc)
        self._populate_table()
        self._update_summary()

    def _populate_table(self):
        self._table.setRowCount(0)
        for row, issue in enumerate(self._issues):
            self._table.insertRow(row)
            bg = _COLORS.get(issue.severity, QColor('#FFFFFF'))

            # Severidad
            sev_item = QTableWidgetItem(
                _ICONS.get(issue.severity, '⚪') + ' ' + issue.severity.capitalize())
            sev_item.setBackground(bg)
            self._table.setItem(row, _COL_SEV, sev_item)

            # Categoría
            cat_item = QTableWidgetItem(issue.category)
            cat_item.setBackground(bg)
            self._table.setItem(row, _COL_CAT, cat_item)

            # Mensaje
            msg_item = QTableWidgetItem(issue.message)
            msg_item.setBackground(bg)
            self._table.setItem(row, _COL_MSG, msg_item)

            # Botones acción
            btn_lay = QHBoxLayout()
            btn_lay.setContentsMargins(4, 2, 4, 2)
            btn_lay.setSpacing(4)

            # Ir → navegar a la hoja
            if issue.sheet_idx >= 0:
                btn_go = QPushButton('→ Ir')
                btn_go.setFixedWidth(54)
                btn_go.setToolTip('Navegar a la hoja afectada')
                _idx = issue.sheet_idx
                btn_go.clicked.connect(lambda _, i=_idx: self._navigate(i))
                btn_lay.addWidget(btn_go)

            # Reparar
            if issue.is_fixable:
                btn_fix = QPushButton(f'🔧 {issue.fix_label}')
                btn_fix.setToolTip('Aplicar corrección automática')
                _row = row
                btn_fix.clicked.connect(
                    lambda _, r=_row: self._fix_one(r))
                btn_lay.addWidget(btn_fix)

            btn_lay.addStretch()
            cell_w = self._make_cell_widget(btn_lay)
            self._table.setCellWidget(row, _COL_FIX, cell_w)
            self._table.setRowHeight(row, 34)

    def _make_cell_widget(self, layout):
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w.setLayout(layout)
        return w

    def _update_summary(self):
        n = len(self._issues)
        if n == 0:
            self._lbl_summary.setText('✅  No se detectaron incidencias.')
            self._btn_fix_all.setEnabled(False)
            return
        errors   = sum(1 for i in self._issues if i.severity == 'error')
        warnings = sum(1 for i in self._issues if i.severity == 'warning')
        infos    = sum(1 for i in self._issues if i.severity == 'info')
        fixable  = sum(1 for i in self._issues if i.is_fixable)
        parts = []
        if errors:   parts.append(f'🔴 {errors} error(es)')
        if warnings: parts.append(f'🟡 {warnings} aviso(s)')
        if infos:    parts.append(f'🔵 {infos} informativo(s)')
        self._lbl_summary.setText('  '.join(parts) +
                                  f'   —   {fixable} reparable(s)')
        self._btn_fix_all.setEnabled(fixable > 0)

    # ── Acciones ──────────────────────────────────────────────────────────

    def _navigate(self, sheet_idx: int):
        if self._nav_fn:
            self._nav_fn(sheet_idx)

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._issues):
            issue = self._issues[row]
            if issue.sheet_idx >= 0:
                self._navigate(issue.sheet_idx)

    def _fix_one(self, row: int):
        if not (0 <= row < len(self._issues)):
            return
        issue = self._issues[row]
        from io_utils.coherence import apply_fix
        from io_utils.db_io import sync_sheet, sync_document
        ok = apply_fix(issue, self._doc, self._scene)
        if ok:
            _persist(self._doc, issue)
            self._run_analysis()   # re-analizar
        else:
            QMessageBox.warning(self, 'Error',
                                'No se pudo aplicar la corrección.')

    def _fix_all(self):
        fixable = [i for i in self._issues if i.is_fixable]
        if not fixable:
            return
        reply = QMessageBox.question(
            self, 'Reparar todo',
            f'Se aplicarán {len(fixable)} correcciones automáticas.\n'
            f'¿Continuar?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        from io_utils.coherence import apply_fix
        n_ok = 0
        for issue in fixable:
            if apply_fix(issue, self._doc, self._scene):
                n_ok += 1
        _persist_all(self._doc)
        self._run_analysis()
        QMessageBox.information(
            self, 'Reparación completada',
            f'Se aplicaron {n_ok} de {len(fixable)} correcciones.')


# ── Persistencia post-reparación ──────────────────────────────────────────

def _persist(doc, issue):
    """Persiste las hojas afectadas por un issue."""
    from io_utils.db_io import sync_sheet, sync_document
    flat = list(doc.flat_sheets())
    affected = set()
    if issue.sheet_idx >= 0:
        affected.add(issue.sheet_idx)
    # Si el issue afecta a slots enlazados, también persistir la hoja remota
    if issue.sheet_idx >= 0 and issue.slot_side == 'left':
        sheet = flat[issue.sheet_idx][0] if issue.sheet_idx < len(flat) else None
        if sheet and issue.slot_idx >= 0:
            sd = sheet.slots_left[issue.slot_idx] if issue.slot_idx < len(sheet.slots_left) else None
            if sd:
                for r_fi in sd.linked_sheets:
                    affected.add(r_fi)
    for fi in affected:
        if 0 <= fi < len(flat):
            try: sync_sheet(flat[fi][0])
            except Exception: pass
    try: sync_document(doc)
    except Exception: pass


def _persist_all(doc):
    """Persiste todas las hojas del documento."""
    from io_utils.db_io import sync_sheet, sync_document
    for sheet, _ in doc.flat_sheets():
        try: sync_sheet(sheet)
        except Exception: pass
    try: sync_document(doc)
    except Exception: pass
