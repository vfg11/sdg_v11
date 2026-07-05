"""
items/branch_node.py — Nodo de bifurcación sobre una conexión existente.

Un BranchNode es un punto en el path de un ConnItem desde el que puede
originarse una o más conexiones adicionales. El usuario lo crea con
Shift+clic sobre la conexión.

El nodo se consolida (se mantiene) cuando al menos una conexión lo usa
como src_item. Si se cancela la conexión sin completar, el nodo
se elimina automáticamente.
"""
from __future__ import annotations
import uuid
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import QPointF, Qt
from const import mm, CONN_COLOR

_R = mm(0.9)   # radio visual del nodo (mitad del junction dot)
_R_HIT = mm(3.0)   # radio de detección para clic


class BranchNode(QGraphicsEllipseItem):
    """
    Nodo de bifurcación que vive en la escena (NO como hijo del ConnItem
    para no heredar su transformación) y se posiciona en scenePos.

    Atributos compatibles con PortItem/SlotItem para ser src/dst de ConnItem:
      - side: siempre 'out' (origina conexiones salientes)
      - connections: lista de ConnItem que salen de este nodo
      - port_scene_pos(): posición escena del nodo
      - seg_is_h: orientación del segmento padre (True=horizontal, False=vertical)
    """
    def __init__(self, parent_conn, scene_pos: QPointF, scene,
                 branch_id: str = ''):
        super().__init__(-_R, -_R, 2 * _R, 2 * _R)
        self.branch_id   = branch_id or str(uuid.uuid4())
        self.parent_conn = parent_conn   # ConnItem al que pertenece
        self.side        = 'out'
        self.connections: list = []
        self.seg_is_h: bool = True       # orientación del segmento padre

        self._dragging: bool = False

        self.setPos(scene_pos)
        self.setPen(QPen(QColor('#000000'), mm(0.15)))
        self.setBrush(QBrush(QColor('#000000')))
        self.setZValue(11)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        scene.addItem(self)

    # ── API compatible con PortItem ──────────────────────────────────────

    def port_scene_pos(self) -> QPointF:
        return self.scenePos()

    # ── Hover ────────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self.setScale(1.4)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # ── Drag a lo largo del path padre ───────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        from items.conn_item import ConnItem
        ci = self.parent_conn
        if not isinstance(ci, ConnItem):
            return
        pts  = ci._full_pts()
        segs = ci._path_segments(pts, skip_stubs=True)
        if not segs:
            return
        scene_pos = event.scenePos()
        t       = ci._t_of_point(scene_pos, segs)
        new_pos = ci._point_at_t(t, segs)
        self.setPos(new_pos)
        # Actualizar orientación
        seg_idx = min(int(t * len(segs)), len(segs)-1)
        a, b = segs[seg_idx]
        self.seg_is_h = abs(b.x()-a.x()) > abs(b.y()-a.y())
        # Redibujar conexiones hijo en tiempo real
        for conn in list(self.connections):
            try:
                conn._user_waypoints = False
                conn.waypoints.clear()
                conn._route_cache = None
                conn._redraw_path_only(conn._full_pts())
            except Exception:
                pass
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            # Persistir ruta final de todas las conexiones hijo
            for conn in list(self.connections):
                try:
                    conn._user_waypoints = False
                    conn.waypoints.clear()
                    conn._route_cache = None
                    conn.update_path()
                except Exception:
                    pass
            sc = self.scene()
            if sc and hasattr(sc, 'rebuild_junctions'):
                sc.rebuild_junctions()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ── Hit-area ampliada ────────────────────────────────────────────────

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        p = QPainterPath()
        p.addEllipse(-_R_HIT, -_R_HIT, 2 * _R_HIT, 2 * _R_HIT)
        return p

    # ── Limpieza ─────────────────────────────────────────────────────────

    def remove(self):
        """Elimina el nodo y todas las conexiones que salgan de él."""
        for conn in list(self.connections):
            try: conn.remove()
            except Exception: pass
        self.connections.clear()
        try:
            if self.scene():
                self.scene().removeItem(self)
        except RuntimeError:
            pass

    def is_orphan(self) -> bool:
        """True si no tiene ninguna conexión consolidada."""
        return len(self.connections) == 0
