"""
widgets/library_panel.py — Panel lateral de biblioteca.
Contiene: bloques lógicos/control + símbolos de campo + herramienta de nota.
Drag & drop al área de dibujo.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget,
                              QTreeWidgetItem, QLabel, QLineEdit,
                              QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QFont, QDrag, QPixmap, QPainter, QColor, QBrush, QPen
import json
from model import BLOCK_LIBRARY, LIBRARY_CATEGORIES, LIBRARY_BY_ID
from items.symbol_item import SYM_CIRCLE, SYM_SENSOR, SYM_ACTUATOR, SYM_NAMES

# Payload type discriminator
_KIND_BLOCK  = 'block'
_KIND_SYMBOL = 'symbol'
_KIND_NOTE   = 'note'

_SYM_ENTRIES = [
    # (sym_type, port_side, label)
    (SYM_CIRCLE,   'out', '○  Círculo — salida'),
    (SYM_CIRCLE,   'in',  '○  Círculo — entrada'),
    (SYM_SENSOR,   'out', '⊙  Instrumento — salida'),
    (SYM_SENSOR,   'in',  '⊙  Instrumento — entrada'),
    (SYM_ACTUATOR, 'out', '⬡  Actuador — salida'),
    (SYM_ACTUATOR, 'in',  '⬡  Actuador — entrada'),
]


class LibraryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(190)
        self.setMaximumWidth(230)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        title = QLabel('BIBLIOTECA')
        title.setFont(QFont('Segoe UI', 9, QFont.Weight.Bold))
        title.setStyleSheet('color:#1a2a4a; padding:4px 0;')
        lay.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar bloques…')
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setFont(QFont('Segoe UI', 8))
        self.tree.itemPressed.connect(self._on_pressed)
        lay.addWidget(self.tree)

        # Botón de nota rápida (drag o clic para insertar)
        note_btn = QPushButton('✎  Añadir nota de texto')
        note_btn.setToolTip(
            'Arrastra o haz clic para insertar una nota en el diagrama')
        note_btn.setStyleSheet(
            'background:#FFFBE8; color:#334; border:1px dashed #AABB88;'
            'padding:4px; border-radius:3px; text-align:left;')
        note_btn.clicked.connect(self._emit_note_drop)
        note_btn.setProperty('_kind', _KIND_NOTE)
        # También permite drag
        note_btn.mousePressEvent = self._note_btn_press
        lay.addWidget(note_btn)
        self._note_btn = note_btn

        tbox_btn = QPushButton('□  Caja de texto con puerto')
        tbox_btn.setToolTip('Arrastra o clic para insertar un rectángulo de texto con puerto de salida')
        tbox_btn.setStyleSheet(
            'background:#F0F8FF; color:#334; border:1px dashed #88AACC;'
            'padding:4px; border-radius:3px; text-align:left;')
        tbox_btn.clicked.connect(self._emit_textbox_drop)
        tbox_btn.mousePressEvent = self._textbox_btn_press
        lay.addWidget(tbox_btn)
        self._tbox_btn = tbox_btn

        self._build_tree()

    # ── construcción del árbol ────────────────────────────────────────────

    def _build_tree(self, filter_txt: str = ''):
        self.tree.clear()

        # ── Sección: Símbolos de campo ───────────────────────────────────
        sym_root = QTreeWidgetItem(['Símbolos de campo'])
        sym_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        f = sym_root.font(0); f.setBold(True); sym_root.setFont(0, f)
        for sym_type, port_side, label in _SYM_ENTRIES:
            if filter_txt and filter_txt.lower() not in label.lower():
                continue
            child = QTreeWidgetItem([label])
            child.setData(0, Qt.ItemDataRole.UserRole, json.dumps({
                'kind':      _KIND_SYMBOL,
                'sym_type':  sym_type,
                'port_side': port_side,
            }))
            child.setToolTip(0, f'{SYM_NAMES[sym_type]} — puerto de {port_side}')
            sym_root.addChild(child)
        if sym_root.childCount() > 0:
            self.tree.addTopLevelItem(sym_root)
            sym_root.setExpanded(True)

        # ── Sección: Bloques lógicos ─────────────────────────────────────
        for cat in LIBRARY_CATEGORIES:
            cat_item = QTreeWidgetItem([cat])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = cat_item.font(0); f.setBold(True); cat_item.setFont(0, f)
            added = 0
            for bt in BLOCK_LIBRARY:
                if bt.category != cat:
                    continue
                if (filter_txt
                        and filter_txt.lower() not in bt.name.lower()
                        and filter_txt.lower() not in bt.description.lower()):
                    continue
                child = QTreeWidgetItem([f'{bt.name}  —  {bt.description}'])
                child.setData(0, Qt.ItemDataRole.UserRole, json.dumps({
                    'kind':         _KIND_BLOCK,
                    'type_id':      bt.type_id,
                    'default_ins':  bt.default_ins,
                    'default_outs': bt.default_outs,
                    'has_kks':      bt.has_kks,
                }))
                child.setToolTip(0, bt.description)
                cat_item.addChild(child)
                added += 1
            if added > 0:
                self.tree.addTopLevelItem(cat_item)
                cat_item.setExpanded(bool(filter_txt))

    def _filter(self, txt: str):
        self._build_tree(txt)

    # ── drag desde árbol ─────────────────────────────────────────────────

    def _on_pressed(self, item: QTreeWidgetItem):
        raw = item.data(0, Qt.ItemDataRole.UserRole)
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except Exception:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(json.dumps(payload))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    # ── nota: drag desde botón ────────────────────────────────────────────

    def _note_btn_press(self, event):
        drag = QDrag(self._note_btn)
        mime = QMimeData()
        mime.setText(json.dumps({'kind': _KIND_NOTE, 'text': 'Nota…'}))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def _emit_note_drop(self):
        """Clic directo: emitir señal al padre si lo implementa."""
        parent = self.parent()
        if hasattr(parent, 'insert_note_center'):
            parent.insert_note_center()

    def _emit_textbox_drop(self):
        parent = self.parent()
        if hasattr(parent, 'insert_textbox_center'):
            parent.insert_textbox_center()

    def _textbox_btn_press(self, event):
        import json
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        drag = QDrag(self._tbox_btn)
        mime = QMimeData()
        mime.setText(json.dumps({'kind': 'textbox', 'text': 'Texto'}))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
