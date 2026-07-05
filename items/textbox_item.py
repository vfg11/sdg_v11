"""
items/textbox_item.py — Rectángulo de texto libre con puerto de salida.

Comportamiento:
  - Rectángulo sin relleno (solo marco) que se adapta al texto.
  - Doble clic → modo edición inline; al salir el rectángulo se redimensiona.
  - Puerto de salida en el borde derecho, igual que los PortItem de bloque.
  - Clic derecho → tamaño de fuente / tipo de señal del puerto / eliminar.
  - Posición libre en el canvas (arrastrable).
  - Guardado/cargado con la hoja.
"""
from __future__ import annotations
import uuid

from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsRectItem,
                              QGraphicsTextItem, QInputDialog, QMenu)
from PyQt6.QtGui  import (QPen, QBrush, QColor, QFont, QPainterPath,
                          QPainter)
from PyQt6.QtCore import Qt, QRectF, QPointF

from const import mm, F_PORT_LABEL, COLOR_BLOCK_BDR
from items.port_item import PortItem

_PAD      = mm(2.0)   # padding interior
_F_DEF    = int(mm(3.5))
_F_MIN    = int(mm(2.0))
_F_MAX    = int(mm(9.0))
_MIN_W    = mm(20)
_BDR_W    = mm(0.5)


class TextBoxItem(QGraphicsRectItem):
    """Rectángulo de texto libre con un puerto de salida a la derecha."""

    def __init__(self, text: str = 'Texto',
                 x: float = 0, y: float = 0,
                 font_size_px: int = _F_DEF,
                 signal_type: str = 'analog',
                 textbox_id: str | None = None,
                 scene=None):
        super().__init__()
        self.textbox_id   = textbox_id or str(uuid.uuid4())
        self.font_size_px = max(_F_MIN, min(_F_MAX, int(font_size_px or _F_DEF)))
        self._sig_type    = signal_type
        self._scene_ref   = scene

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)

        # Marco
        self.setPen(QPen(QColor('#000000'), _BDR_W))
        self.setBrush(QBrush(QColor('#FFFFFF')))

        # Texto interior (hijo) — sin interacción por defecto para no bloquear drag
        self._txt = QGraphicsTextItem(self)
        self._txt.setPlainText(text)
        self._txt.setDefaultTextColor(QColor('#1a2a3a'))
        self._txt.setZValue(6)
        self._txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._apply_font()

        # Puerto de salida (hijo, se crea tras calcular tamaño)
        self.port_item: PortItem | None = None
        # Atributos mínimos para que ConnItem/editor lo reconozca como fuente
        self.port_items_in:  list = []
        self.port_items_out: list = []

        self.setPos(x, y)
        self._fit()
        self._build_port()

    # ── Apariencia ────────────────────────────────────────────────────────

    def _apply_font(self):
        f = QFont('Segoe UI')
        f.setPixelSize(self.font_size_px)
        self._txt.setFont(f)

    def _fit(self):
        """Redimensiona el rectángulo para envolver el texto con padding."""
        br = self._txt.boundingRect()
        w  = max(_MIN_W, br.width()  + 2 * _PAD)
        h  = max(mm(8),  br.height() + 2 * _PAD)
        self.setRect(0, 0, w, h)
        self._txt.setPos(_PAD, (h - br.height()) / 2)
        # Reubicar puerto si ya existe
        if self.port_item is not None:
            self.port_item.setPos(w, h / 2)

    def _build_port(self):
        """Crea el único puerto de salida en el borde derecho."""
        r = self.rect()
        self.port_item = PortItem('out', 0, '', self,
                                  signal_type=self._sig_type)
        self.port_item.setPos(r.width(), r.height() / 2)
        self.port_items_out = [self.port_item]
        # Compatibilidad con ConnItem: connections en el propio puerto
        self.connections: list = []   # conexiones que salen de aquí (via port)

    # ── Edición inline ───────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        self._txt.setAcceptedMouseButtons(Qt.MouseButton.AllButtons)
        self._txt.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self._txt.setFocus(Qt.FocusReason.MouseFocusReason)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._txt.focusOutEvent = self._on_text_focus_out
        super().mouseDoubleClickEvent(event)

    def _on_text_focus_out(self, event):
        self._txt.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        c = self._txt.textCursor(); c.clearSelection(); self._txt.setTextCursor(c)
        self._fit()
        QGraphicsTextItem.focusOutEvent(self._txt, event)

    # ── Menú contextual ──────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QApplication
        in_edit = bool(self._txt.textInteractionFlags() &
                       Qt.TextInteractionFlag.TextEditorInteraction)
        menu = QMenu()

        if in_edit:
            cur    = self._txt.textCursor()
            has_sel = cur.hasSelection()
            a_cut  = menu.addAction('✂  Cortar');       a_cut.setEnabled(has_sel)
            a_copy = menu.addAction('📋  Copiar');       a_copy.setEnabled(has_sel)
            a_paste= menu.addAction('📌  Pegar')
            a_selall=menu.addAction('☰  Seleccionar todo')
            menu.addSeparator()
        else:
            a_cut = a_copy = a_paste = a_selall = None

        a_sz   = menu.addAction('📝  Cambiar tamaño de fuente…')
        # Tipo de señal del puerto
        a_dig  = menu.addAction('⚡  Puerto: Digital')
        a_ana  = menu.addAction('〰  Puerto: Analógico')
        a_dig.setCheckable(True); a_dig.setChecked(self._sig_type == 'digital')
        a_ana.setCheckable(True); a_ana.setChecked(self._sig_type == 'analog')
        menu.addSeparator()
        a_del  = menu.addAction('🗑  Eliminar')

        act = menu.exec(event.screenPos())
        if not act:
            return

        if in_edit:
            if act == a_cut:
                QApplication.clipboard().setText(self._txt.textCursor().selectedText())
                self._txt.textCursor().removeSelectedText()
            elif act == a_copy:
                QApplication.clipboard().setText(self._txt.textCursor().selectedText())
            elif act == a_paste:
                c = self._txt.textCursor()
                c.insertText(QApplication.clipboard().text())
                self._txt.setTextCursor(c)
            elif act == a_selall:
                c = self._txt.textCursor()
                c.select(c.SelectionType.Document)
                self._txt.setTextCursor(c)

        if act == a_sz:
            cur_pt = max(4, round(self.font_size_px * 0.75))
            new_pt, ok = QInputDialog.getInt(None, 'Tamaño', 'Puntos (4–24):',
                                             cur_pt, 4, 24, 1)
            if ok:
                self.font_size_px = max(_F_MIN, min(_F_MAX,
                                        int(round(new_pt / 0.75))))
                self._apply_font(); self._fit(); self.update()
        elif act == a_dig:
            self._set_signal_type('digital')
        elif act == a_ana:
            self._set_signal_type('analog')
        elif act == a_del:
            sc = self.scene()
            if sc:
                sc.remove_textbox(self)
        event.accept()

    def _set_signal_type(self, sig: str):
        self._sig_type = sig
        if self.port_item:
            self.port_item.signal_type = sig
            # Refrescar conexiones del puerto
            for conn in list(self.port_item.connections):
                try: conn.update_path()
                except Exception: pass
            self.port_item.update()

    # ── Movimiento → actualizar conexiones ────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.port_item:
                for conn in list(self.port_item.connections):
                    try: conn.update_path()
                    except Exception: pass
        return super().itemChange(change, value)

    # ── Hover ─────────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor('#0033AA'), mm(0.8)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor(COLOR_BLOCK_BDR), _BDR_W))
        super().hoverLeaveEvent(event)

    # ── Selección ────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            p = QPen(QColor('#2244CC'), mm(0.2))
            p.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(p)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.rect())
            painter.restore()

    # ── Propiedades ───────────────────────────────────────────────────────

    @property
    def text(self) -> str:
        return self._txt.toPlainText()

    @text.setter
    def text(self, v: str):
        self._txt.setPlainText(v)
        self._fit()

    # ── Serialización ─────────────────────────────────────────────────────

    def save(self) -> dict:
        p = self.pos()
        return {
            'textbox_id':   self.textbox_id,
            'text':         self.text,
            'font_size_px': self.font_size_px,
            'signal_type':  self._sig_type,
            'x': p.x(), 'y': p.y(),
        }

    @staticmethod
    def from_dict(d: dict, scene=None) -> 'TextBoxItem':
        return TextBoxItem(
            text         = d.get('text', 'Texto'),
            x            = d.get('x', 0),
            y            = d.get('y', 0),
            font_size_px = d.get('font_size_px', _F_DEF),
            signal_type  = d.get('signal_type', 'analog'),
            textbox_id   = d.get('textbox_id'),
            scene        = scene,
        )
