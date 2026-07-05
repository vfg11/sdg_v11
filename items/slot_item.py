"""
items/slot_item.py  —  Conector de columna lateral (v8, nuevo layout).

LAYOUT IZQUIERDA (entradas) — de izquierda a derecha:
  ┌──────┬─────────────────────────────┬──────────────┬──────────────┐  2/3 h
  │ NUM  │  DESCRIPCION EQUIPO (50%)   │ SENAL (21%)  │  KKS  (21%)  │
  │  8%  │  max 2 lineas x 35 ch       │ 2l x 15 ch   │  2l x 15 ch  │
  │      ├─────────────────────────────┴──────────────┴──────────────┤  1/3 h
  │      │  REFERENCIA AUTO (92%, zona inferior)                     │
  └──────┴───────────────────────────────────────────────────────────┘
  Puerto = punto medio del borde DERECHO del conector (sin circulo).

LAYOUT DERECHA (salidas) — espejo horizontal:
  ┌──────────────┬──────────────┬─────────────────────────────┬──────┐
  │  KKS  (21%)  │ SENAL (21%)  │  DESCRIPCION EQUIPO (50%)   │ NUM  │
  │              │              │                             │  8%  │
  ├──────────────┴──────────────┴─────────────────────────────┤      │
  │  REFERENCIA AUTO                                          │      │
  └──────────────────────────────────────────────────────────-┴──────┘
  Puerto = punto medio del borde IZQUIERDO del conector (sin circulo).

Porcentajes relativos al ancho TOTAL del conector (COL_W).
Zona inferior de referencia: 92% del ancho (excluye celda numero).
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsItem,
                              QGraphicsTextItem, QGraphicsLineItem)
from PyQt6.QtGui  import QPen, QBrush, QColor, QFont
from PyQt6.QtCore import QRectF, QPointF, Qt
from const import (COL_W,
                   COLOR_SLOT_USED, COLOR_SLOT_EMPTY, COLOR_SLOT_LINE,
                   COLOR_SLOT_LINKED, COLOR_SLOT_PENDING, mm)
from model import SlotData

# ── Proporciones (respecto al ancho total COL_W) ──────────────────────────
# Proporciones importadas de const.py (editarlas allí)
from const import (CONN_NUM_PCT  as _NUM_W,
                   CONN_DESC_PCT as _DESC_W,
                   CONN_SIG_PCT  as _SIG_W,
                   CONN_KKS_PCT  as _KKS_W)
_UPPER_H = 2 / 3
_LOWER_H = 1 / 3

# ── Fuentes ───────────────────────────────────────────────────────────────
# Altura disponible por linea en la zona superior: slot_h * 2/3 / 2
# Con 23 conectores: 110u * 2/3 / 2 = 36.7u → fuente max ~26-28 px
# Courier New 10px ≈ 7px por caracter → 35 ch * 7 = 245u < desc_w(310u) OK
# Una sola fuente para todo el conector (= fuente del número)
_F_PT      = 18   # puntos — misma para número, textos y referencia
_F_REF_PT  = 18   # referencia igual que el resto

_LINE_PEN_W = mm(0.22)
_PAD        = mm(1.2)   # padding interno de celdas


def _vline(parent, x, y0, length, pen):
    li = QGraphicsLineItem(x, y0, x, y0 + length, parent)
    li.setPen(pen)
    return li


def _hline(parent, x0, x1, y, pen):
    li = QGraphicsLineItem(x0, y, x1, y, parent)
    li.setPen(pen)
    return li


class SlotItem(QGraphicsRectItem):

    def __init__(self, data: SlotData, index: int, side: str,
                 x, y, w, h, scene):
        super().__init__(x, y, w, h)
        self.data        = data
        self.index       = index     # 0-based
        self.side        = side      # 'left' | 'right'
        self._scene      = scene
        self.connections: list = []
        self._pending    = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._build()

    # ── geometria auxiliar ────────────────────────────────────────────────

    def _geo(self):
        """Devuelve (x0, y0, w, h, num_w, desc_w, sig_w, kks_w, upper_h, lower_h)."""
        r   = self.rect()
        w   = r.width(); h = r.height()
        x0  = r.x();     y0 = r.y()
        return (x0, y0, w, h,
                w * _NUM_W,   w * _DESC_W, w * _SIG_W,   w * _KKS_W,
                h * _UPPER_H, h * _LOWER_H)

    # ── construccion ──────────────────────────────────────────────────────

    def _build(self):
        self._apply_style()
        self._draw_grid()
        self._draw_texts()

    def _clear_children(self):
        for ch in self.childItems():
            try:
                ch.setParentItem(None)
            except RuntimeError:
                pass

    def _apply_style(self):
        if self._pending:
            bg = COLOR_SLOT_PENDING
        elif self.data.is_linked():
            bg = COLOR_SLOT_LINKED
        elif not self.data.is_empty():
            bg = '#FFFFFF'
        else:
            bg = '#FFFFFF'
        self.setBrush(QBrush(QColor(bg)))
        pw = mm(0.5) if self._pending else mm(0.30)
        pc = '#CC8800' if self._pending else '#000000'
        self.setPen(QPen(QColor(pc), pw))

    def _draw_grid(self):
        """Divisores internos de celdas."""
        x0, y0, w, h, nw, dw, sw, kw, uh, lh = self._geo()
        pen = QPen(QColor('#000000'), _LINE_PEN_W)

        if self.side == 'left':
            # Borde derecho celda numero (altura completa)
            _vline(self, x0 + nw, y0, h, pen)
            # Divisor upper / lower (desde celda numero hasta borde der)
            _hline(self, x0 + nw, x0 + w, y0 + uh, pen)
            # Divisores desc | sig | kks (solo zona upper)
            _vline(self, x0 + nw + dw,      y0, uh, pen)
            _vline(self, x0 + nw + dw + sw, y0, uh, pen)
        else:
            # Borde izquierdo celda numero (altura completa)
            _vline(self, x0 + w - nw, y0, h, pen)
            # Divisor upper / lower
            _hline(self, x0, x0 + w - nw, y0 + uh, pen)
            # Divisores kks | sig | desc (solo zona upper)
            _vline(self, x0 + kw,      y0, uh, pen)
            _vline(self, x0 + kw + sw, y0, uh, pen)

    def _draw_texts(self):
        x0, y0, w, h, nw, dw, sw, kw, uh, lh = self._geo()
        p = _PAD

        # Fuente única: Segoe UI 18pt — igual para todos los campos
        f_num = QFont('Segoe UI')
        f_num.setPointSize(_F_PT)
        f_num.setBold(True)

        f_txt = QFont('Segoe UI')
        f_txt.setPointSize(_F_PT)

        f_ref = QFont('Segoe UI')
        f_ref.setPointSize(_F_REF_PT)

        lbl_num = f'{self.index + 1:02d}'

        if self.side == 'left':
            # Numero (celda izquierda, centrado verticalmente)
            self._txt(lbl_num, f_num, '#1a2a4a', x0, y0, nw, h,
                      Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            # Zona upper: desc | sig | kks+kks2
            rest_x = x0 + nw
            self._txt(self.data.description, f_txt, '#0a1a2a',
                      rest_x + p, y0 + p, dw - 2*p, uh - 2*p)
            self._txt(self.data.signal_desc, f_txt, '#0a1a2a',
                      rest_x + dw + p, y0 + p, sw - 2*p, uh - 2*p)
            # KKS: linea superior; KKS2: linea inferior
            kx = rest_x + dw + sw + p
            line_h = (uh - 2*p) / 2
            self._txt(self.data.kks,  f_txt, '#0a1a2a', kx, y0 + p,        kw - 2*p, line_h)
            self._txt(self.data.kks2, f_txt, '#224488', kx, y0 + p + line_h, kw - 2*p, line_h)
            # Zona lower: referencia auto
            if self.data.sub_text:
                self._txt(self.data.sub_text, f_ref, '#003388',
                          rest_x + p, y0 + uh + p/2, w - nw - 2*p, lh - p,
                          Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            # Numero (celda derecha, centrado)
            self._txt(lbl_num, f_num, '#1a2a4a',
                      x0 + w - nw, y0, nw, h,
                      Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            # Zona upper (espejo): kks+kks2 | sig | desc
            kx = x0 + p
            line_h = (uh - 2*p) / 2
            self._txt(self.data.kks,  f_txt, '#0a1a2a', kx, y0 + p,        kw - 2*p, line_h)
            self._txt(self.data.kks2, f_txt, '#224488', kx, y0 + p + line_h, kw - 2*p, line_h)
            self._txt(self.data.signal_desc, f_txt, '#0a1a2a',
                      x0 + kw + p, y0 + p, sw - 2*p, uh - 2*p)
            self._txt(self.data.description, f_txt, '#0a1a2a',
                      x0 + kw + sw + p, y0 + p, dw - 2*p, uh - 2*p)
            # Zona lower
            if self.data.sub_text:
                self._txt(self.data.sub_text, f_ref, '#003388',
                          x0 + p, y0 + uh + p/2, w - nw - 2*p, lh - p,
                          Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _txt(self, text, font, color, x, y, max_w, max_h,
             align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop):
        if not text:
            return
        t = QGraphicsTextItem(self)
        t.setFont(font)
        t.setDefaultTextColor(QColor(color))
        t.setTextWidth(max_w)
        t.setPos(x, y)
        # Interlineado compacto: 85% de la altura normal
        from PyQt6.QtGui import QTextBlockFormat
        fmt = QTextBlockFormat()
        fmt.setLineHeight(85, 1)   # 1 = ProportionalHeight
        cursor = t.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.setBlockFormat(fmt)
        # Alineacion
        doc = t.document()
        opt = doc.defaultTextOption()
        if align & Qt.AlignmentFlag.AlignHCenter:
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        elif align & Qt.AlignmentFlag.AlignRight:
            opt.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            opt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        doc.setDefaultTextOption(opt)
        t.setPlainText(text)

    # ── puerto (sin circulo, solo posicion) ───────────────────────────────

    def port_scene_pos(self) -> QPointF:
        r  = self.rect()
        py = r.y() + r.height() / 2          # mitad exacta de la altura
        px = r.right() if self.side == 'left' else r.left()
        return self.mapToScene(QPointF(px, py))

    # ── estado pending ────────────────────────────────────────────────────

    def set_pending(self, pending: bool):
        self._pending = pending
        self._apply_style()

    # ── refresco ──────────────────────────────────────────────────────────

    def refresh(self):
        self._clear_children()
        self._apply_style()
        self._draw_grid()
        self._draw_texts()
        for conn in self.connections:
            try:
                conn.update_path()
            except Exception:
                pass
