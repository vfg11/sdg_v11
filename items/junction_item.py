"""
items/junction_item.py — Punto negro de derivación (junction dot).

Un BranchNode consolidado ES en sí mismo un junction.
También se detectan T-junctions clásicas.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import QPointF
from const import CONN_DOT_R, mm

_TOL = mm(2.0)


def _eq(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) < _TOL and abs(a.y() - b.y()) < _TOL


def _seg_contains(a: QPointF, b: QPointF, p: QPointF) -> bool:
    dx = abs(b.x() - a.x()); dy = abs(b.y() - a.y())
    if dx < _TOL:
        if abs(p.x() - a.x()) > _TOL: return False
        lo = min(a.y(), b.y()); hi = max(a.y(), b.y())
        return lo + _TOL < p.y() < hi - _TOL
    elif dy < _TOL:
        if abs(p.y() - a.y()) > _TOL: return False
        lo = min(a.x(), b.x()); hi = max(a.x(), b.x())
        return lo + _TOL < p.x() < hi - _TOL
    return False


class JunctionOverlay(QGraphicsEllipseItem):
    def __init__(self, pos: QPointF, scene):
        r = CONN_DOT_R
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPos(pos)
        self.setPen(QPen(QColor('#000000'), mm(0.15)))
        self.setBrush(QBrush(QColor('#000000')))
        self.setZValue(13)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)
        scene.addItem(self)


def compute_junctions(conn_items: list,
                      branch_nodes: list | None = None) -> list[QPointF]:
    """Devuelve posiciones (escena) para junction dots.

    - BranchNodes consolidados son siempre junctions.
    - T-junctions clásicas (extremo sobre segmento interior de otra) también.
    """
    jpts: list[QPointF] = []

    def add(p: QPointF):
        if not any(_eq(p, j) for j in jpts):
            jpts.append(QPointF(p))

    def segs(ci):
        try:
            pts = ci._full_pts()
            return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        except Exception:
            return []

    # 1. BranchNodes consolidados
    for bn in (branch_nodes or []):
        try:
            if not bn.is_orphan():
                add(bn.scenePos())
        except Exception:
            pass

    # 2. T-junctions clásicas (por si existen sin BranchNode)
    for i, ci in enumerate(conn_items):
        try:
            sp = ci.src_item.scenePos()
            dp = ci.dst_item.scenePos()
        except Exception:
            continue
        for j, cj in enumerate(conn_items):
            if i == j: continue
            for a, b in segs(cj):
                for ep in (sp, dp):
                    if _seg_contains(a, b, ep):
                        add(ep)

    return jpts
