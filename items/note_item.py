"""
items/note_item.py — Texto libre sobre el canvas.
Doble clic → edición inline multilinea.
Clic derecho → tamaño de fuente / eliminar.
Arrastra el borde derecho (handle azul) para ajustar el ancho.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QGraphicsTextItem, QGraphicsItem,
                              QGraphicsRectItem,
                              QInputDialog, QGraphicsSceneContextMenuEvent)
from PyQt6.QtGui  import QFont, QColor, QPainter, QPainterPath, QPen, QBrush, QCursor
from PyQt6.QtCore import Qt, QRectF, QPointF
from const import mm
import uuid

_F_DEF  = int(mm(3.5))
_F_MIN  = int(mm(2.0))
_F_MAX  = int(mm(9.0))
_PAD    = mm(1.5)
_W_DEF  = mm(60)
_W_MIN  = mm(20)
_W_MAX  = mm(300)
_HANDLE_W = mm(4)   # ancho del handle de resize


class NoteItem(QGraphicsTextItem):
    """Texto libre sin marco. Doble clic para editar (multilinea con Enter).
    Arrastra el borde derecho para cambiar el ancho."""

    def __init__(self, text: str = 'Nota…',
                 x: float = 0, y: float = 0,
                 font_size_px: int = _F_DEF,
                 note_id: str | None = None,
                 text_width: float = _W_DEF):
        super().__init__()
        self.note_id      = note_id or str(uuid.uuid4())
        self.font_size_px = max(_F_MIN, min(_F_MAX, int(font_size_px or _F_DEF)))
        self._text_width  = max(_W_MIN, min(_W_MAX, float(text_width or _W_DEF)))
        self._resizing    = False
        self._resize_start_x   = 0.0
        self._resize_start_w   = 0.0

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(15)
        self._apply_font()
        self.setTextWidth(self._text_width)
        self.setPlainText(text)
        self.setPos(x, y)

    def _apply_font(self):
        f = QFont('Segoe UI')
        f.setPixelSize(self.font_size_px)
        self.setFont(f)
        self.setDefaultTextColor(QColor('#1a2a3a'))

    def _handle_rect(self) -> QRectF:
        """Rectángulo del handle de resize (borde derecho), en coordenadas locales."""
        br = super().boundingRect()
        return QRectF(br.right() - _HANDLE_W/2, br.top(),
                      _HANDLE_W, br.height())

    def boundingRect(self) -> QRectF:
        br = super().boundingRect()
        return br.adjusted(-_PAD, -_PAD, _PAD + _HANDLE_W/2, _PAD)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            # Marco de selección
            p = QPen(QColor('#2244CC'), mm(0.18))
            p.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(p)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            br = super().boundingRect().adjusted(-_PAD, -_PAD, _PAD, _PAD)
            painter.drawRect(br)
            # Handle de resize (borde derecho)
            hr = self._handle_rect()
            painter.setPen(QPen(QColor('#2244CC'), mm(0.15)))
            painter.setBrush(QBrush(QColor('#4488FF')))
            painter.drawRect(hr)
            painter.restore()

    def _in_handle(self, pos: QPointF) -> bool:
        return self._handle_rect().contains(pos)

    def mousePressEvent(self, event):
        if (self.isSelected() and
                event.button() == Qt.MouseButton.LeftButton and
                self._in_handle(event.pos())):
            self._resizing = True
            self._resize_start_x = event.scenePos().x()
            self._resize_start_w = self._text_width
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            dx = event.scenePos().x() - self._resize_start_x
            new_w = max(_W_MIN, min(_W_MAX, self._resize_start_w + dx))
            self._text_width = new_w
            self.setTextWidth(new_w)
            self.update()
            event.accept()
            return
        # Cambiar cursor al pasar sobre el handle
        if self.isSelected() and self._in_handle(event.pos()):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.isSelected() and self._in_handle(event.pos()):
            event.accept()
            return
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        c = self.textCursor(); c.clearSelection(); self.setTextCursor(c)
        self._text_width = self.textWidth()
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        """Rueda del ratón → ajustar tamaño de fuente (sin modificar ancho)."""
        if not self.isSelected():
            event.ignore(); return
        delta = event.angleDelta().y()
        step  = int(mm(0.3)) if delta > 0 else -int(mm(0.3))
        self.font_size_px = max(_F_MIN, min(_F_MAX, self.font_size_px + step))
        self._apply_font()
        self.update()
        event.accept()

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        from PyQt6.QtWidgets import QMenu, QApplication
        in_edit = bool(self.textInteractionFlags() &
                       Qt.TextInteractionFlag.TextEditorInteraction)
        menu = QMenu()

        if in_edit:
            cursor = self.textCursor()
            has_sel = cursor.hasSelection()
            a_cut   = menu.addAction('✂  Cortar')
            a_copy  = menu.addAction('📋  Copiar')
            a_paste = menu.addAction('📌  Pegar')
            a_selall= menu.addAction('☰  Seleccionar todo')
            a_cut.setEnabled(has_sel)
            a_copy.setEnabled(has_sel)
            menu.addSeparator()

        a_sz  = menu.addAction('📝  Cambiar tamaño de fuente…')
        a_del = menu.addAction('🗑  Eliminar nota')

        act = menu.exec(event.screenPos())

        if in_edit:
            if act == a_cut:
                QApplication.clipboard().setText(self.textCursor().selectedText())
                self.textCursor().removeSelectedText()
            elif act == a_copy:
                QApplication.clipboard().setText(self.textCursor().selectedText())
            elif act == a_paste:
                c = self.textCursor()
                c.insertText(QApplication.clipboard().text())
                self.setTextCursor(c)
            elif act == a_selall:
                c = self.textCursor()
                c.select(c.SelectionType.Document)
                self.setTextCursor(c)

        if act == a_sz:
            cur_pt = max(4, round(self.font_size_px * 0.75))
            new_pt, ok = QInputDialog.getInt(None, 'Tamaño', 'Puntos (4–24):',
                                             cur_pt, 4, 24, 1)
            if ok:
                self.font_size_px = max(_F_MIN, min(_F_MAX, int(round(new_pt / 0.75))))
                self._apply_font()
                self.update()
        elif act == a_del:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            sc = self.scene()
            if sc and hasattr(sc, 'remove_note'):
                sc.remove_note(self)
        event.accept()

    @property
    def text(self) -> str: return self.toPlainText()
    @text.setter
    def text(self, v: str): self.setPlainText(v)

    def save(self) -> dict:
        p = self.pos()
        return {'note_id': self.note_id, 'text': self.toPlainText(),
                'font_size_px': self.font_size_px,
                'text_width': self._text_width,
                'x': p.x(), 'y': p.y()}

    @staticmethod
    def from_dict(d: dict) -> 'NoteItem':
        return NoteItem(text=d.get('text', ''), x=d.get('x', 0), y=d.get('y', 0),
                        font_size_px=d.get('font_size_px', _F_DEF),
                        note_id=d.get('note_id'),
                        text_width=d.get('text_width', _W_DEF))
