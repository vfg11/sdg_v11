"""
items/symbol_item.py — Símbolos de campo en el canvas, tangentes al cajón.

Puerto del símbolo hereda de PortItem para ser compatible con _finish_conn.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsItemGroup,
                              QGraphicsEllipseItem, QGraphicsRectItem,
                              QGraphicsPolygonItem, QGraphicsLineItem,
                              QGraphicsTextItem)
from PyQt6.QtGui  import QPen, QBrush, QColor, QFont, QPolygonF
from PyQt6.QtCore import QPointF, Qt
from const import (SYM_SIZE, PORT_R, COLOR_PORT_IN, COLOR_PORT_OUT,
                   F_BLOCK_KKS, COL_W, COL_R_X, WORK_Y, WORK_H, mm)
from items.port_item import PortItem

_PEN_W = mm(0.6)
_FILL  = QBrush(QColor('#EEF5FF'))

SYM_CIRCLE   = 'CIRCLE'
SYM_SENSOR   = 'SENSOR'
SYM_ACTUATOR = 'ACTUATOR'

SYM_NAMES = {
    SYM_CIRCLE:   'Círculo',
    SYM_SENSOR:   'Instrumento (burbuja ISA)',
    SYM_ACTUATOR: 'Actuador / Válvula',
}


def _pen() -> QPen:
    p = QPen(QColor('#1A2A4A'), _PEN_W)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


def _sym_x(port_side: str) -> float:
    return COL_R_X - SYM_SIZE if port_side == 'out' else COL_W


def _snap_y(drop_y: float, num_slots: int) -> float:
    sh  = WORK_H / max(num_slots, 1)
    idx = int((drop_y - WORK_Y) / sh)
    idx = max(0, min(num_slots - 1, idx))
    return WORK_Y + idx * sh + (sh - SYM_SIZE) / 2


class SymbolPortItem(PortItem):
    """Puerto del símbolo: invisible visualmente, activo para hit-testing."""
    def __init__(self, side: str, parent):
        super().__init__(side, 0, '', parent)
        r = PORT_R * 1.5   # area de hit generosa
        self.setRect(-r, -r, 2*r, 2*r)
        self.setZValue(7)
        # Sin relleno ni borde — invisible pero presente en la escena
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def hoverEnterEvent(self, event): pass
    def hoverLeaveEvent(self, event): pass
    def paint(self, painter, option, widget=None): pass  # no dibujar nada


class SymbolItem(QGraphicsItemGroup):
    """Símbolo de campo anclado en canvas, tangente al cajón."""

    def __init__(self, sym_type: str, port_side: str,
                 x: float = 0.0, y: float = 0.0,
                 kks: str = '', num_slots: int = 12):
        super().__init__()
        import uuid as _uuid
        self.sym_id     = str(_uuid.uuid4())   # ID único para serialización
        self.sym_type   = sym_type
        self.port_side  = port_side
        self.kks        = kks
        self.num_slots  = num_slots
        self.connections: list = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(6)

        fx = _sym_x(port_side)
        fy = _snap_y(y if y != 0.0 else WORK_Y, num_slots)
        self.setPos(fx, fy)
        self._build()

    def _build(self):
        for child in self.childItems():
            child.setParentItem(None)

        s = SYM_SIZE
        h = s / 2
        p = _pen()

        if self.sym_type == SYM_CIRCLE:
            e = QGraphicsEllipseItem(0, 0, s, s, self)
            e.setPen(p); e.setBrush(_FILL)

        elif self.sym_type == SYM_SENSOR:
            r = QGraphicsRectItem(0, 0, s, s, self)
            r.setPen(p); r.setBrush(_FILL)
            m = s * 0.12
            c = QGraphicsEllipseItem(m, m, s-2*m, s-2*m, self)
            c.setPen(p); c.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ln = QGraphicsLineItem(0, h, s, h, self)
            ln.setPen(p)

        elif self.sym_type == SYM_ACTUATOR:
            pts = QPolygonF([
                QPointF(0,       h),
                QPointF(s*0.25,  0),
                QPointF(s*0.75,  0),
                QPointF(s,       h),
                QPointF(s*0.75,  s),
                QPointF(s*0.25,  s),
            ])
            poly = QGraphicsPolygonItem(pts, self)
            poly.setPen(p); poly.setBrush(_FILL)
            ln = QGraphicsLineItem(0, h, s, h, self)
            ln.setPen(p)

        # KKS
        if self.kks:
            f = QFont('Courier New')
            f.setPixelSize(F_BLOCK_KKS)
            lbl = QGraphicsTextItem(self.kks, self)
            lbl.setFont(f)
            lbl.setDefaultTextColor(QColor('#334466'))
            lw = lbl.boundingRect().width()
            lbl.setPos((s - lw) / 2, s + mm(0.5))
            lbl.setZValue(7)

        # Puerto PortItem real
        pside = 'out' if self.port_side == 'out' else 'in'
        px    = s if self.port_side == 'out' else 0
        self._port = SymbolPortItem(pside, self)
        self._port.setPos(px, h)

        self.setAcceptHoverEvents(True)

    def _set_hover(self, on: bool):
        """Resalta o restaura el borde de todos los elementos gráficos hijos."""
        hover_pen = QPen(QColor('#0055CC'), _PEN_W * 1.8)
        hover_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        hover_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        normal_pen = _pen()
        p = hover_pen if on else normal_pen
        for child in self.childItems():
            if hasattr(child, 'setPen') and not isinstance(child, SymbolPortItem):
                try:
                    child.setPen(p)
                except Exception:
                    pass

    def hoverEnterEvent(self, event):
        self._set_hover(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_hover(False)
        super().hoverLeaveEvent(event)

    def port_item(self) -> PortItem:
        return self._port

    def port_scene_pos(self) -> QPointF:
        return self._port.scenePos()

    def snap_to_slot(self, scene_y: float, num_slots: int | None = None):
        ns = num_slots or self.num_slots
        self.setPos(_sym_x(self.port_side), _snap_y(scene_y, ns))
        for c in self.connections:
            try: c.update_path()
            except Exception: pass

    def save(self) -> dict:
        p = self.pos()
        return {'sym_id': self.sym_id, 'sym_type': self.sym_type,
                'port_side': self.port_side, 'kks': self.kks,
                'x': p.x(), 'y': p.y()}

    @staticmethod
    def from_dict(d: dict, num_slots: int = 12) -> 'SymbolItem':
        si = SymbolItem(d['sym_type'], d.get('port_side', 'out'),
                        d.get('x', 0), d.get('y', 0),
                        d.get('kks', ''), num_slots)
        if d.get('sym_id'):
            si.sym_id = d['sym_id']
        return si
