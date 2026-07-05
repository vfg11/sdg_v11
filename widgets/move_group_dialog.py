"""
widgets/move_group_dialog.py — Diálogo para mover un grupo a otra posición.

Permite seleccionar el grupo a mover y el número de hoja de destino
(número de la primera hoja del grupo tras el movimiento).
Muestra en tiempo real si el destino colisiona y si se abrirá hueco.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QDialogButtonBox,
    QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MoveGroupDialog(QDialog):

    def __init__(self, document, current_group_id: str = '', parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle('Mover grupo a otra posición')
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Título ──────────────────────────────────────────────────────
        title = QLabel('Mover grupo')
        f = QFont(); f.setBold(True); f.setPointSize(11)
        title.setFont(f)
        layout.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #ccc')
        layout.addWidget(sep)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        layout.addLayout(form)

        # ── Selector de grupo ───────────────────────────────────────────
        self._cb_group = QComboBox()
        self._cb_group.setMinimumWidth(300)
        self._groups = []   # lista paralela de GroupData
        selected_i = 0
        for i, g in enumerate(document.groups):
            last = g.sheet_number_base + len(g.sheets) - 1
            rng  = (f'H{g.sheet_number_base:02d}' if len(g.sheets) == 1
                    else f'H{g.sheet_number_base:02d}–H{last:02d}')
            label = f'{g.description or g.kks or "(sin nombre)"}  [{rng}]'
            self._cb_group.addItem(label)
            self._groups.append(g)
            if g.group_id == current_group_id:
                selected_i = i
        self._cb_group.setCurrentIndex(selected_i)
        form.addRow('Grupo a mover:', self._cb_group)

        # ── Número de hoja destino ───────────────────────────────────────
        self._sb_dest = QSpinBox()
        self._sb_dest.setRange(1, 9999)
        self._sb_dest.setFixedWidth(90)
        form.addRow('Primera hoja en destino:', self._sb_dest)

        # ── Info de destino (actualiza en tiempo real) ───────────────────
        self._lbl_info = QLabel()
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet('color: #555; font-size: 11px;')
        layout.addWidget(self._lbl_info)

        # ── Botones ─────────────────────────────────────────────────────
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        # Init destino con un valor razonable
        self._cb_group.currentIndexChanged.connect(self._update_info)
        self._sb_dest.valueChanged.connect(self._update_info)
        self._init_dest()
        self._update_info()

    # ────────────────────────────────────────────────────────────────────

    def _selected_group(self):
        i = self._cb_group.currentIndex()
        if 0 <= i < len(self._groups):
            return self._groups[i]
        return None

    def _init_dest(self):
        """Propone un número de destino: décena libre por encima del último."""
        doc = self.document
        max_num = 0
        for g in doc.groups:
            last = g.sheet_number_base + len(g.sheets) - 1
            if last > max_num:
                max_num = last
        decade = (max_num // 10 + 1) * 10
        g = self._selected_group()
        if g and g.sheet_number_base == decade:
            decade += 10
        self._sb_dest.setValue(decade)

    def _update_info(self):
        g    = self._selected_group()
        dest = self._sb_dest.value()
        ok, msg = self.validate(silent=True)
        if g is None:
            self._lbl_info.setText('')
            self._buttons.button(
                QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        n    = len(g.sheets)
        last = dest + n - 1
        rng  = f'H{dest:02d}' if n == 1 else f'H{dest:02d}–H{last:02d}'

        # Detectar grupos que se desplazarán
        to_shift = [
            gr for gr in self.document.groups
            if gr is not g and gr.sheet_number_base <= last
            and gr.sheet_number_base + len(gr.sheets) - 1 >= dest
        ]
        lines = [f'El grupo ocupará {rng}.']
        if to_shift:
            names = ', '.join(
                f'"{gr.description or gr.kks or gr.group_id[:6]}"'
                for gr in to_shift[:3]
            )
            if len(to_shift) > 3:
                names += ' …'
            lines.append(f'Se abrirá hueco desplazando: {names}.')
        else:
            lines.append('No hay conflicto: el destino está libre.')

        if not ok:
            lines.append(f'⚠ {msg}')
            self._lbl_info.setStyleSheet('color: #cc2200; font-size: 11px;')
        else:
            self._lbl_info.setStyleSheet('color: #555; font-size: 11px;')

        self._lbl_info.setText('\n'.join(lines))
        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def validate(self, silent: bool = False) -> tuple[bool, str]:
        """Comprueba si el movimiento es válido. Devuelve (ok, mensaje)."""
        g    = self._selected_group()
        dest = self._sb_dest.value()
        if g is None:
            return False, 'Selecciona un grupo.'

        # No moverse a la misma posición
        if g.sheet_number_base == dest:
            return False, 'El grupo ya está en esa posición.'

        # El destino no puede caer dentro del propio grupo (solapamiento consigo)
        own_range = range(g.sheet_number_base, g.sheet_number_base + len(g.sheets))
        if dest in own_range:
            return False, 'El destino solapa con el rango actual del propio grupo.'

        return True, ''

    # ── Resultado ────────────────────────────────────────────────────────

    def selected_group(self):
        return self._selected_group()

    def dest_base(self) -> int:
        return self._sb_dest.value()
