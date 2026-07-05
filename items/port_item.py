"""
items/port_item.py — Puerto de bloque.

Puerto visual reducido (PORT_R=1.1mm). Soporta flag 'negated' para digitales:
dibuja un pequeño círculo vacío tangente al exterior del bloque.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QRectF
from const import PORT_R, COLOR_PORT_IN, COLOR_PORT_OUT, mm


class PortItem(QGraphicsEllipseItem):

    def __init__(self, side: str, index: int, name: str, parent,
                 signal_type: str = 'analog', negated: bool = False):
        r = PORT_R
        super().__init__(-r, -r, 2*r, 2*r, parent)
        self.side        = side
        self.index       = index
        self.name        = name
        self.signal_type = signal_type   # 'digital' | 'analog'
        self.negated     = negated
        self.connections: list = []

        # Color por tipo: digital=verde, analog=azul/rojo
        if signal_type == 'digital':
            color = '#2a8a2a' if side == 'in' else '#1a6a1a'
        else:
            color = COLOR_PORT_IN if side == 'in' else COLOR_PORT_OUT
        self.setPen(QPen(QColor(color), mm(0.35)))
        self.setBrush(QBrush(QColor(color)))
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setAcceptHoverEvents(True)
        self._neg_circle = None
        if negated and signal_type == 'digital':
            self._build_neg_circle(color)

    def _build_neg_circle(self, color: str):
        """Círculo de negación: borde interior tangente al PortItem,
        borde exterior hacia afuera del bloque.
        La conexión llega al PortItem y el círculo queda por encima de la línea."""
        nr  = PORT_R * 0.9          # radio del círculo de negación
        r   = PORT_R
        # Centro del círculo: desplazado nr+r desde el centro del puerto
        # → el borde interior del círculo toca el centro del puerto
        cx  = -(r + nr) if self.side == 'in' else +(r + nr)
        nc  = QGraphicsEllipseItem(-nr, -nr, 2*nr, 2*nr, self)
        nc.setPos(cx, 0)
        nc.setPen(QPen(QColor(color), mm(0.45)))
        nc.setBrush(QBrush(QColor('#FFFFFF')))   # fondo blanco
        nc.setZValue(50)                          # por encima de conexiones (zValue=30)
        nc.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        nc.setAcceptHoverEvents(False)
        self._neg_circle = nc

    def label(self) -> str:
        return self.name

    def shape(self):
        """Hit-area = círculo visual exacto."""
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    def hoverEnterEvent(self, event):
        self.setScale(1.5)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            for conn in self.connections:
                try: conn.update_path()
                except Exception: pass
        return super().itemChange(change, value)
