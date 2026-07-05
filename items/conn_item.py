"""
items/conn_item.py — Conexión ortogonal con stub horizontal en extremos.

REGLA DE ENRUTAMIENTO:
  src_pos → stub_src (horizontal) → waypoints → stub_dst (horizontal) → dst_pos

  El stub garantiza que la línea siempre sale/llega horizontalmente desde el puerto.
  CONN_STUB = longitud del tramo horizontal fijo (5 mm).

INTERACCIÓN:
  Ctrl+Click    → insertar nodo en el segmento más cercano.
  Click+Drag    → arrastrar segmento H/V en paralelo.
  Doble clic en handle → eliminar nodo.
  Seleccionado  → cuadrados naranjas en nodos internos.
"""
from __future__ import annotations
import math
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem, QGraphicsRectItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QPainterPathStroker
from PyQt6.QtCore import QPointF, Qt
from const import CONN_PEN_W, CONN_COLOR, CONN_SEL_COLOR, WP_HANDLE_R, CONN_STUB, CONN_SEP, mm

_AXIS_TOL = 1.0
_HIT_SEG  = mm(2.5)
_MIN_SEG  = mm(1.0)


# ── Handle de nodo ────────────────────────────────────────────────────────

class WaypointHandle(QGraphicsRectItem):
    """Cuadrado naranja en cada vértice de la conexión.
    Invisible por defecto; visible+arrastrable cuando la conexión está seleccionada.
    """

    # Tamaño en pixels de pantalla (invariante al zoom)
    _S_NORMAL = 6.0
    _S_HOVER  = 8.0

    def __init__(self, conn: "ConnItem", idx: int):
        s = self._S_NORMAL
        super().__init__(-s, -s, 2*s, 2*s)
        self.conn      = conn
        self.idx       = idx
        self._updating = False
        self._dragging = False
        self.setPen(QPen(QColor("#C04000"), 1.0))
        self.setBrush(QBrush(QColor("#FF7733")))
        # Sin ItemIsMovable: drag gestionado manualmente en mouseMoveEvent
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(35)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAcceptHoverEvents(True)
        self.setVisible(False)   # oculto hasta que la conexión se seleccione

    def hoverEnterEvent(self, event):
        s = self._S_HOVER
        self.setRect(-s, -s, 2*s, 2*s)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        s = self._S_NORMAL
        self.setRect(-s, -s, 2*s, 2*s)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.scenePos()
            if 0 <= self.idx < len(self.conn.waypoints):
                self.conn._user_waypoints = True
                self.conn.waypoints[self.idx] = QPointF(new_pos)
                self._updating = True
                self.setPos(new_pos)
                self._updating = False
                self.conn._redraw_path_only()
                self.conn._update_branch_nodes(self.conn._full_pts())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.conn.update_path(invalidate_cache=False)
            try:
                if self.conn._scene:
                    self.conn._scene.rebuild_junctions()
            except Exception:
                pass
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.conn._remove_node(self.idx)
        event.accept()


# ── Conexión ──────────────────────────────────────────────────────────────

class ConnItem(QGraphicsPathItem):
    """
    src/dst pueden ser SlotItem (is_slot=True) o PortItem (is_slot=False).
    Los stubs horizontales se calculan automáticamente a partir de la dirección
    de salida de cada extremo.
    """

    def __init__(self, src_item, src_is_slot: bool,
                 dst_item, dst_is_slot: bool, scene,
                 waypoints: list[QPointF] | None = None):
        super().__init__(None)
        import uuid as _uuid
        self.conn_id     = str(_uuid.uuid4())   # ID persistente
        self.src_item    = src_item
        self.src_is_slot = src_is_slot
        self.dst_item    = dst_item
        self.dst_is_slot = dst_is_slot
        self._scene      = scene

        self.waypoints: list[QPointF] = list(waypoints) if waypoints else []
        self._user_waypoints: bool = bool(waypoints)  # True solo si el usuario los definió
        self._routing_live: bool = False  # True durante drag: ruta dinámica, no persistir
        self._handles:  list[WaypointHandle] = []
        self._seg_drag: dict | None = None
        # Caché de la última ruta A* calculada
        self._route_cache: list[QPointF] | None = None
        self._route_cache_key: tuple | None = None

        pen = QPen(QColor(CONN_COLOR), CONN_PEN_W)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setZValue(2)   # por debajo de símbolos (z=6)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        src_item.connections.append(self)
        dst_item.connections.append(self)
        scene.addItem(self)
        self.update_path()

    # ── posiciones y stubs ───────────────────────────────────────────────

    def _src_pos(self) -> QPointF:
        p = (self.src_item.port_scene_pos() if self.src_is_slot
             else self.src_item.scenePos())
        off = self._field_sym_offset(self.src_item, self.src_is_slot, self._src_dir())
        return QPointF(p.x() + self._src_dir() * off, p.y()) if off else p

    def _dst_pos(self) -> QPointF:
        p = (self.dst_item.port_scene_pos() if self.dst_is_slot
             else self.dst_item.scenePos())
        off = self._field_sym_offset(self.dst_item, self.dst_is_slot, self._dst_dir())
        return QPointF(p.x() + self._dst_dir() * off, p.y()) if off else p

    @staticmethod
    def _port_dir(item, is_slot: bool) -> int:
        """
        Dirección del stub: hacia afuera del cajón/símbolo (hacia el canvas).

        Slot left  (puerto en borde DER de col izq) → stub va a la DER  → +1
        Slot right (puerto en borde IZQ de col der) → stub va a la IZQ  → -1
        Port 'out' (borde derecho del bloque)       → stub va a la DER  → +1
        Port 'in'  (borde izquierdo del bloque)     → stub va a la IZQ  → -1
        SymbolPort 'out' (borde der símbolo, toca col SALIDAS) → stub IZQ → -1
        SymbolPort 'in'  (borde izq símbolo, toca col ENTRADAS)→ stub DER → +1
        """
        from items.symbol_item import SymbolPortItem
        if is_slot:
            return +1 if getattr(item, 'side', 'right') == 'left' else -1
        if isinstance(item, SymbolPortItem):
            # Invertido respecto a port normal: 'out' toca col der → va izq
            return -1 if item.side == 'out' else +1
        return +1 if getattr(item, 'side', 'out') == 'out' else -1

    def _src_dir(self) -> int:
        return self._port_dir(self.src_item, self.src_is_slot)

    def _dst_dir(self) -> int:
        return self._port_dir(self.dst_item, self.dst_is_slot)

    def _branch_stub_src(self) -> QPointF:
        """Stub de salida desde un BranchNode, estrictamente perpendicular
        al segmento del padre. Cuando hay varias derivaciones desde el mismo
        nodo, cada una recibe un carril único para no solaparse.
        """
        bn  = self.src_item
        pos = bn.scenePos()
        base_off = CONN_SEP * 2   # distancia mínima del stub desde el nodo

        # ── Detectar orientación del segmento padre ──────────────────────
        seg_h = getattr(bn, 'seg_is_h', True)
        try:
            p = bn.parent_conn.path()
            n = p.elementCount()
            best_dist = float('inf')
            for i in range(n - 1):
                ax = p.elementAt(i).x;   ay = p.elementAt(i).y
                bx = p.elementAt(i+1).x; by = p.elementAt(i+1).y
                seg_dx = bx - ax; seg_dy = by - ay
                seg_len2 = seg_dx*seg_dx + seg_dy*seg_dy
                if seg_len2 < 1:
                    continue
                t = max(0.0, min(1.0,
                    ((pos.x()-ax)*seg_dx + (pos.y()-ay)*seg_dy) / seg_len2))
                proj_x = ax + t*seg_dx; proj_y = ay + t*seg_dy
                d = ((pos.x()-proj_x)**2 + (pos.y()-proj_y)**2)**0.5
                if d < best_dist:
                    best_dist = d
                    seg_h = abs(by - ay) < _AXIS_TOL
            bn.seg_is_h = seg_h
        except Exception:
            pass

        # ── Obtener todos los hermanos que salen del mismo nodo ──────────
        siblings = list(bn.connections)   # todos los ConnItem con src=bn

        if seg_h:
            # Padre horizontal → derivaciones salen en vertical
            # Separar las que van arriba (dst.y < pos.y) de las que van abajo
            def _dst_y(c):
                try: return c._dst_pos().y()
                except: return pos.y()

            above = [c for c in siblings if _dst_y(c) < pos.y()]
            below = [c for c in siblings if _dst_y(c) >= pos.y()]

            # Si todos van al mismo lado, repartirlos igualmente entre los dos
            if not above:
                half = len(siblings) // 2
                above = siblings[:half]; below = siblings[half:]
            elif not below:
                half = len(siblings) // 2
                above = siblings[:half]; below = siblings[half:]

            if self in above:
                idx = above.index(self)
                off = -(base_off + idx * CONN_SEP)
            else:
                idx = below.index(self) if self in below else 0
                off = base_off + idx * CONN_SEP

            return QPointF(pos.x(), pos.y() + off)

        else:
            # Padre vertical → derivaciones salen en horizontal
            def _dst_x(c):
                try: return c._dst_pos().x()
                except: return pos.x()

            left  = [c for c in siblings if _dst_x(c) < pos.x()]
            right = [c for c in siblings if _dst_x(c) >= pos.x()]

            if not left:
                half = len(siblings) // 2
                left = siblings[:half]; right = siblings[half:]
            elif not right:
                half = len(siblings) // 2
                left = siblings[:half]; right = siblings[half:]

            if self in left:
                idx = left.index(self)
                off = -(base_off + idx * CONN_SEP)
            else:
                idx = right.index(self) if self in right else 0
                off = base_off + idx * CONN_SEP

            return QPointF(pos.x() + off, pos.y())

    @staticmethod
    def _field_sym_offset(item, is_slot: bool, direction: int) -> float:
        """
        Si el item es un SlotItem con símbolo de campo adyacente, devuelve
        SYM_SIZE para extender el stub hasta el borde exterior del símbolo.
        El símbolo siempre está del lado del canvas (mismo sentido que direction).
        """
        if not is_slot:
            return 0.0
        from items.slot_item import SlotItem
        from const import SYM_SIZE as _SS
        if not isinstance(item, SlotItem):
            return 0.0
        sc = item.scene()
        if sc is None:
            return 0.0
        sym = sc.symbol_for_slot(item)
        return _SS if sym is not None else 0.0

    def _stub_src(self) -> QPointF:
        from items.branch_node import BranchNode as _BN
        if isinstance(self.src_item, _BN):
            return self._branch_stub_src()
        p = self._src_pos()
        return QPointF(p.x() + self._src_dir() * CONN_STUB, p.y())

    def _stub_dst(self) -> QPointF:
        p = self._dst_pos()
        return QPointF(p.x() + self._dst_dir() * CONN_STUB, p.y())

    # ── normalización ortogonal ──────────────────────────────────────────

    @staticmethod
    def _normalize(pts: list[QPointF]) -> list[QPointF]:
        """Inserta esquinas H→V donde los puntos no son colineales."""
        if len(pts) < 2:
            return [QPointF(p) for p in pts]
        result = [QPointF(pts[0])]
        for i in range(1, len(pts)):
            a = result[-1]
            b = pts[i]
            if abs(b.x()-a.x()) > _AXIS_TOL and abs(b.y()-a.y()) > _AXIS_TOL:
                result.append(QPointF(b.x(), a.y()))
            result.append(QPointF(b))
        return result

    @staticmethod
    def _cleanup(pts: list[QPointF]) -> list[QPointF]:
        if len(pts) <= 2:
            return pts
        result = [QPointF(pts[0])]
        for i in range(1, len(pts) - 1):
            prev, curr, nxt = result[-1], pts[i], pts[i+1]
            if _dist(prev, curr) < _MIN_SEG:
                continue
            h_pp = abs(curr.y()-prev.y()) < _AXIS_TOL
            h_cn = abs(nxt.y()-curr.y())  < _AXIS_TOL
            v_pp = abs(curr.x()-prev.x()) < _AXIS_TOL
            v_cn = abs(nxt.x()-curr.x())  < _AXIS_TOL
            if (h_pp and h_cn) or (v_pp and v_cn):
                continue
            result.append(QPointF(curr))
        result.append(QPointF(pts[-1]))
        return result

    def _full_pts(self) -> list[QPointF]:
        """
        Lista normalizada: src → stub_src → waypoints → stub_dst → dst

        Si el usuario no ha arrastrado manualmente ningún segmento,
        usa el router Hanan-grid + A* para encontrar la ruta óptima.
        Si tiene waypoints de usuario, los respeta.
        """
        if not self._user_waypoints:
            return self._route_optimal()
        # waypoints contiene [stub_src, ...interior..., stub_dst] — la ruta
        # completa entre los puertos. Solo añadimos src_pos y dst_pos en
        # los extremos (calculados dinámicamente desde la posición actual).
        raw = ([self._src_pos()]
               + list(self.waypoints)
               + [self._dst_pos()])
        return self._normalize(raw)

    # ── enrutamiento Hanan-grid + A* ─────────────────────────────────────

    def _route_optimal(self) -> list[QPointF]:
        """Enruta con Hanan-grid + A*, garantizando stub perpendicular en src y dst.

        El stub (tramo perpendicular fijo) se calcula antes de llamar a Hanan y
        se añade como segmentos fijos al inicio y al final del path.  El router
        solo decide la ruta interior entre stub_src y stub_dst.

        Usa caché: si src/dst no cambiaron significativamente, devuelve el
        resultado anterior sin relanzar A*.
        """
        from routing.hanan_router import route as hanan_route
        from const import CANVAS_X, CANVAS_Y, CANVAS_W, CANVAS_H

        src_p = self._src_pos()
        dst_p = self._dst_pos()
        ss    = self._stub_src()   # punto fijo tras el stub de origen
        sd    = self._stub_dst()   # punto fijo antes del stub de destino

        # Clave de caché: posición de stub_src y stub_dst redondeados a 5u
        _R = 5
        cache_key = (
            round(ss.x() / _R) * _R, round(ss.y() / _R) * _R,
            round(sd.x() / _R) * _R, round(sd.y() / _R) * _R,
        )
        if (self._route_cache is not None and
                self._route_cache_key == cache_key):
            return self._route_cache

        canvas = (CANVAS_X, CANVAS_Y,
                  CANVAS_X + CANVAS_W, CANVAS_Y + CANVAS_H)

        # Obstáculos: bloques de la escena
        obstacles = []
        if hasattr(self, '_scene') and self._scene:
            for bi in self._scene.block_items:
                try:
                    r = bi.mapToScene(bi.boundingRect()).boundingRect()
                    obstacles.append((r.left(), r.top(),
                                      r.right(), r.bottom()))
                except Exception:
                    pass

        # Rutas existentes: limitar a las más cercanas al segmento src→dst
        # para no penalizar el A* con docenas de conexiones lejanas.
        existing = []
        if hasattr(self, '_scene') and self._scene:
            _MAX_EX = 20
            # Bounding box del trayecto actual
            bx0 = min(ss.x(), sd.x()); bx1 = max(ss.x(), sd.x())
            by0 = min(ss.y(), sd.y()); by1 = max(ss.y(), sd.y())
            margin = 500.0  # ~50mm de margen
            bx0 -= margin; by0 -= margin; bx1 += margin; by1 += margin
            count = 0
            for other in self._scene.conn_items:
                if other is self or count >= _MAX_EX:
                    continue
                try:
                    p = other.path()
                    n = p.elementCount()
                    if n < 2:
                        continue
                    # Comprobar si la conexión está en el área de interés
                    pr = p.boundingRect()
                    if (pr.right()  < bx0 or pr.left()  > bx1 or
                            pr.bottom() < by0 or pr.top()   > by1):
                        continue
                    existing.append([
                        (p.elementAt(i).x, p.elementAt(i).y)
                        for i in range(n)
                    ])
                    count += 1
                except Exception:
                    pass

        # Router trabaja entre stub_src y stub_dst
        if abs(ss.x()-sd.x()) < 1 and abs(ss.y()-sd.y()) < 1:
            inner = [(ss.x(), ss.y())]
        else:
            inner = hanan_route(
                (ss.x(), ss.y()),
                (sd.x(), sd.y()),
                obstacles, existing, canvas
            )

        # Construir path completo: src → stub_src → [hanan] → stub_dst → dst
        # ss y sd (stubs) se protegen del _cleanup para que nunca desaparezcan:
        # se aplica cleanup solo a los puntos interiores [ss..inner..sd].
        inner_pts = [QPointF(x, y) for (x, y) in inner]
        mid = self._cleanup(self._normalize([ss] + inner_pts + [sd]))
        # mid[0]=ss, mid[-1]=sd garantizados (son extremos, _cleanup los preserva)
        result = self._normalize([src_p] + mid + [dst_p])

        # Guardar en caché
        self._route_cache     = result
        self._route_cache_key = cache_key
        return result

    def _inner_pts(self) -> list[QPointF]:
        """Solo los puntos internos entre stub_src y stub_dst (= waypoints normalizados)."""
        pts = self._full_pts()
        # pts[0]=src, pts[1]=stub_src, …, pts[-2]=stub_dst, pts[-1]=dst
        return pts[2:-2]

    # ── dibujado ─────────────────────────────────────────────────────────

    def _avoid_overlaps(self, pts: list[QPointF]) -> list[QPointF]:
        """
        Separa segmentos que se solapan con los de otras conexiones insertando
        un pequeño detour ortogonal (sin romper la geometría).

        Para cada segmento de esta conexión que se superponga exactamente con
        un segmento de otra, se inserta un desvío de CONN_SEP unidades en la
        dirección perpendicular, creando cuatro puntos extra que forman un
        rectángulo delgado y mantienen la ortogonalidad del resto del path.
        """
        if not hasattr(self, '_scene') or self._scene is None:
            return pts
        try:
            others = [c for c in self._scene.conn_items if c is not self]
        except Exception:
            return pts
        if not others or len(pts) < 2:
            return pts

        # Número de conexiones que comparten el mismo src_item (para el signo del offset)
        try:
            siblings = [c for c in self._scene.conn_items
                        if c.src_item is self.src_item and c is not self]
            offset_sign = 1 if (id(self) % 2 == 0 or not siblings) else -1
        except Exception:
            offset_sign = 1

        result: list[QPointF] = list(pts)   # trabajamos sobre copia
        i = 0
        while i < len(result) - 1:
            a = result[i]; b = result[i + 1]
            is_h = abs(b.y() - a.y()) < _AXIS_TOL
            is_v = abs(b.x() - a.x()) < _AXIS_TOL
            if not (is_h or is_v):
                i += 1; continue

            overlapped = False
            for other in others:
                if overlapped: break
                try:
                    ops = other._full_pts()
                except Exception:
                    continue
                for oi in range(len(ops) - 1):
                    oa = ops[oi]; ob = ops[oi + 1]
                    oh = abs(ob.y() - oa.y()) < _AXIS_TOL
                    ov = abs(ob.x() - oa.x()) < _AXIS_TOL
                    if is_h and oh and abs(a.y() - oa.y()) < CONN_SEP * 0.6:
                        # Solapamiento horizontal: comprobar rangos X
                        ax0, ax1 = min(a.x(), b.x()), max(a.x(), b.x())
                        ox0, ox1 = min(oa.x(), ob.x()), max(oa.x(), ob.x())
                        overlap_x = max(0, min(ax1, ox1) - max(ax0, ox0))
                        if overlap_x > CONN_SEP:
                            # Insertar detour: a → (a.x, a.y+off) → (b.x, b.y+off) → b
                            off = CONN_SEP * offset_sign
                            result = (result[:i+1]
                                      + [QPointF(a.x(), a.y() + off),
                                         QPointF(b.x(), b.y() + off)]
                                      + result[i+1:])
                            i += 2   # saltar los dos puntos insertados
                            overlapped = True; break
                    elif is_v and ov and abs(a.x() - oa.x()) < CONN_SEP * 0.6:
                        # Solapamiento vertical: comprobar rangos Y
                        ay0, ay1 = min(a.y(), b.y()), max(a.y(), b.y())
                        oy0, oy1 = min(oa.y(), ob.y()), max(oa.y(), ob.y())
                        overlap_y = max(0, min(ay1, oy1) - max(ay0, oy0))
                        if overlap_y > CONN_SEP:
                            off = CONN_SEP * offset_sign
                            result = (result[:i+1]
                                      + [QPointF(a.x() + off, a.y()),
                                         QPointF(b.x() + off, b.y())]
                                      + result[i+1:])
                            i += 2
                            overlapped = True; break
            i += 1
        return result

    def update_path(self, invalidate_cache: bool = True):
        if self._seg_drag is not None:
            return
        if invalidate_cache:
            self._route_cache = None     # forzar recálculo A*
        pts = self._full_pts()
        if self._routing_live:
            # Durante drag de grupo: dibujar y actualizar branches, NO persistir.
            self._redraw_path_only(pts)
            self._update_branch_nodes(pts)   # branches siguen al path en tiempo real
            return
        self.waypoints = [QPointF(p) for p in pts[1:-1]]
        self._user_waypoints = True
        self._redraw_path_only(pts)
        self._sync_handles()
        # Actualizar posición de BranchNodes cuyo padre es esta conexión
        self._update_branch_nodes(pts)
        try:
            if self._scene:
                self._scene.rebuild_junctions()
        except Exception:
            pass

    # ── Utilidades de parámetro t sobre el path interior ────────────────

    @staticmethod
    def _path_segments(pts: list[QPointF], skip_stubs: bool = True):
        """
        Devuelve los segmentos del path como lista de (a, b).
        Si skip_stubs=True excluye el primer y último segmento (los stubs),
        de modo que el BranchNode no puede caer fuera del tramo real.
        """
        if len(pts) < 2:
            return []
        segs = [(pts[i], pts[i+1]) for i in range(len(pts)-1)]
        if skip_stubs and len(segs) >= 3:
            segs = segs[1:-1]   # quitar stub_src y stub_dst
        return segs

    @staticmethod
    def _t_of_point(pos: QPointF, segs) -> float:
        """
        Parámetro t ∈ [0,1] del punto del path (definido por segs)
        más cercano a pos. t se mide sobre la longitud total de segs.
        """
        if not segs:
            return 0.5
        total_len = 0.0
        seg_lens  = []
        for a, b in segs:
            d = ((b.x()-a.x())**2 + (b.y()-a.y())**2) ** 0.5
            seg_lens.append(d)
            total_len += d
        if total_len < 1e-6:
            return 0.5
        best_t   = 0.0
        best_d   = float('inf')
        arc      = 0.0
        for (a, b), seg_len in zip(segs, seg_lens):
            if seg_len < 1e-6:
                arc += seg_len
                continue
            dx_ = b.x()-a.x(); dy_ = b.y()-a.y()
            t_seg = ((pos.x()-a.x())*dx_ + (pos.y()-a.y())*dy_) / (seg_len*seg_len)
            t_seg = max(0.0, min(1.0, t_seg))
            proj  = QPointF(a.x()+t_seg*dx_, a.y()+t_seg*dy_)
            dist  = ((proj.x()-pos.x())**2 + (proj.y()-pos.y())**2) ** 0.5
            if dist < best_d:
                best_d = dist
                best_t = (arc + t_seg * seg_len) / total_len
            arc += seg_len
        return best_t

    @staticmethod
    def _point_at_t(t: float, segs) -> QPointF:
        """Punto en el path (definido por segs) al parámetro t ∈ [0,1]."""
        if not segs:
            return QPointF()
        total_len = 0.0
        seg_lens  = []
        for a, b in segs:
            d = ((b.x()-a.x())**2 + (b.y()-a.y())**2) ** 0.5
            seg_lens.append(d)
            total_len += d
        if total_len < 1e-6:
            return segs[0][0]
        target = max(0.0, min(1.0, t)) * total_len
        arc    = 0.0
        for (a, b), seg_len in zip(segs, seg_lens):
            if arc + seg_len >= target or seg_len < 1e-6:
                if seg_len < 1e-6:
                    return a
                frac = (target - arc) / seg_len
                return QPointF(a.x() + frac*(b.x()-a.x()),
                               a.y() + frac*(b.y()-a.y()))
            arc += seg_len
        return segs[-1][1]

    def _update_branch_nodes(self, pts: list[QPointF]):
        """Reposiciona los BranchNodes cuyo parent_conn es esta conexión.

        Usa el parámetro t (fracción de longitud sobre el tramo interior,
        excluyendo stubs) para preservar la posición relativa del nodo
        independientemente de cómo cambie la topología del path.
        """
        if not (hasattr(self, '_scene') and self._scene):
            return
        from items.branch_node import BranchNode as _BN
        segs = self._path_segments(pts, skip_stubs=True)
        if not segs:
            return
        for bn in list(self._scene.branch_nodes):
            try:
                if bn.parent_conn is not self:
                    continue
                # Si el nodo tiene t guardado (puesto por pre_update_t),
                # usarlo directamente; si no, calcularlo desde la posición actual.
                t = getattr(bn, '_path_t', None)
                if t is None:
                    t = self._t_of_point(bn.scenePos(), segs)
                new_pos = self._point_at_t(t, segs)
                bn._path_t = None   # consumir
                bn.setPos(new_pos)
                # Actualizar orientación del segmento padre
                # (para que las conexiones hijo salgan perpendiculares)
                seg_idx = min(int(t * len(segs)), len(segs)-1)
                a, b = segs[seg_idx]
                bn.seg_is_h = abs(b.x()-a.x()) > abs(b.y()-a.y())
                # Actualizar las conexiones que salen del BranchNode
                for conn in list(bn.connections):
                    conn._user_waypoints = False
                    conn.waypoints.clear()
                    conn._route_cache = None
                    conn._redraw_path_only(conn._full_pts())
            except Exception:
                pass

    def save_branch_t(self):
        """Guarda el parámetro t de todos los BranchNodes de esta conexión
        ANTES de recalcular el path, para que _update_branch_nodes lo restaure.
        Llamar antes de limpiar waypoints en conexiones parciales.
        """
        if not (hasattr(self, '_scene') and self._scene):
            return
        pts  = self._full_pts()
        segs = self._path_segments(pts, skip_stubs=True)
        if not segs:
            return
        from items.branch_node import BranchNode as _BN
        for bn in self._scene.branch_nodes:
            try:
                if bn.parent_conn is not self:
                    continue
                bn._path_t = self._t_of_point(bn.scenePos(), segs)
            except Exception:
                pass

    def shape(self) -> QPainterPath:
        """Área de hit ampliada (~4mm) para facilitar click y drag."""
        stroker = QPainterPathStroker()
        stroker.setWidth(mm(4.0))
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return stroker.createStroke(self.path())

    def _redraw_path_only(self, pts: list[QPointF] | None = None):
        if pts is None:
            pts = self._full_pts()
        path = QPainterPath()
        path.moveTo(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        self.setPath(path)

    # ── handles ──────────────────────────────────────────────────────────

    def _sync_handles(self):
        wps = self.waypoints
        while len(self._handles) > len(wps):
            h = self._handles.pop()
            try:
                if h.scene(): h.scene().removeItem(h)
            except RuntimeError:
                pass
        visible = self.isSelected()
        for i, wp in enumerate(wps):
            if i < len(self._handles):
                h = self._handles[i]
                h.idx = i
                h._updating = True
                h.setPos(wp)
                h._updating = False
            else:
                h = WaypointHandle(self, i)
                self._scene.addItem(h)
                h.setPos(wp)
                self._handles.append(h)
            h.setVisible(visible)

    def _set_handles_visible(self, v: bool):
        for h in self._handles:
            try: h.setVisible(v)
            except RuntimeError: pass

    # ── hit-test ─────────────────────────────────────────────────────────

    def _find_segment(self, pos: QPointF, pts: list[QPointF]) -> int:
        """Devuelve índice del segmento más cercano en pts, o -1."""
        best_i, best_d = -1, float("inf")
        for i in range(len(pts) - 1):
            d = _dist_pt_seg(pos, pts[i], pts[i+1])
            if d < best_d:
                best_d, best_i = d, i
        return best_i if best_d < _HIT_SEG else -1

    @staticmethod
    def _seg_is_h(pts, i) -> bool:
        return abs(pts[i].y() - pts[i+1].y()) < _AXIS_TOL

    # ── insertar / eliminar nodo ─────────────────────────────────────────

    def _insert_node(self, scene_pos: QPointF):
        pts = self._full_pts()
        seg = self._find_segment(scene_pos, pts)
        if seg < 0:
            return
        a, b = pts[seg], pts[seg+1]
        is_h = self._seg_is_h(pts, seg)
        if is_h:
            new_wp = QPointF(
                max(min(scene_pos.x(), max(a.x(),b.x())), min(a.x(),b.x())),
                a.y())
        else:
            new_wp = QPointF(
                a.x(),
                max(min(scene_pos.y(), max(a.y(),b.y())), min(a.y(),b.y())))
        # pts[0]=src_pos, pts[1]=waypoints[0](=stub_src),...
        # seg 0 = src_pos→waypoints[0], seg 1 = waypoints[0]→waypoints[1], ...
        # → insertar antes de waypoints[seg-1], mínimo posición 0
        wp_idx = max(0, seg - 1)
        self._user_waypoints = True
        self.waypoints.insert(wp_idx, QPointF(new_wp))
        self.update_path()

    def _remove_node(self, idx: int):
        if not (0 <= idx < len(self.waypoints)):
            return
        self.waypoints.pop(idx)
        if idx < len(self._handles):
            h = self._handles.pop(idx)
            try:
                if h.scene(): h.scene().removeItem(h)
            except RuntimeError:
                pass
        for i, h in enumerate(self._handles):
            h.idx = i
        self.update_path()

    # ── arrastre de segmento ─────────────────────────────────────────────

    def _start_seg_drag(self, seg_idx: int, pts: list[QPointF], start: QPointF):
        n = len(pts)
        if seg_idx == 0 or seg_idx + 1 == n - 1:
            return   # stub de origen/destino — no arrastrable
        is_h = self._seg_is_h(pts, seg_idx)
        self._seg_drag = {
            "seg":   seg_idx,
            "is_h":  is_h,
            "orig":  [QPointF(p) for p in pts],
            "start": QPointF(start),
        }
        self.setCursor(Qt.CursorShape.SizeVerCursor if is_h
                       else Qt.CursorShape.SizeHorCursor)

    def _apply_seg_drag(self, mouse: QPointF):
        if self._seg_drag is None:
            return
        d    = self._seg_drag
        seg  = d["seg"]
        is_h = d["is_h"]
        orig = d["orig"]          # snapshot original — nunca modificar
        n    = len(orig)

        a, b = seg, seg + 1
        if a == 0 or b == n - 1:
            return  # seg 0 y último son los stubs — longitud fija

        # Solo componente perpendicular al segmento
        delta = (mouse.y() - d["start"].y()) if is_h else (mouse.x() - d["start"].x())
        if abs(delta) < 0.5:
            return

        # Nuevos extremos del segmento arrastrado (sólo eje perpendicular)
        if is_h:
            new_a = QPointF(orig[a].x(), orig[a].y() + delta)
            new_b = QPointF(orig[b].x(), orig[b].y() + delta)
        else:
            new_a = QPointF(orig[a].x() + delta, orig[a].y())
            new_b = QPointF(orig[b].x() + delta, orig[b].y())

        # ── Lado izquierdo: tramo prev (a-1 → a) ─────────────────────────
        # Colineal con el segmento arrastrado = misma orientación
        prev = orig[a - 1]
        if is_h:
            prev_colinear = abs(prev.y() - orig[a].y()) < _AXIS_TOL
        else:
            prev_colinear = abs(prev.x() - orig[a].x()) < _AXIS_TOL

        # ── Lado derecho: tramo next (b → b+1) ───────────────────────────
        nxt = orig[b + 1]
        if is_h:
            nxt_colinear = abs(nxt.y() - orig[b].y()) < _AXIS_TOL
        else:
            nxt_colinear = abs(nxt.x() - orig[b].x()) < _AXIS_TOL

        # ── Construir nueva lista de puntos ───────────────────────────────
        # Reglas:
        #   Adyacente perpendicular → el punto compartido sigue al segmento
        #                             (el tramo adyacente se estira/encoge)
        #   Adyacente colineal      → el punto compartido se queda fijo y se
        #                             inserta un tramo perpendicular de enlace
        new_pts: list[QPointF] = list(orig[:a])   # puntos antes del segmento

        if prev_colinear:
            # Mantener orig[a] fijo; insertar new_a como nuevo inicio del seg
            new_pts.append(QPointF(orig[a]))
            new_pts.append(new_a)
        else:
            # El punto a sigue al segmento (tramo prev se estira)
            new_pts.append(new_a)

        # Extremo final del segmento arrastrado
        new_pts.append(new_b)

        if nxt_colinear:
            # Mantener orig[b] fijo; new_b ya está añadido como puente
            new_pts.append(QPointF(orig[b]))

        new_pts.extend(orig[b + 1:])              # puntos después del segmento

        cleaned = self._cleanup(new_pts)
        self.waypoints = [QPointF(p) for p in cleaned[1:-1]]
        self._redraw_path_only(cleaned)
        self._sync_handles()
        self._update_branch_nodes(cleaned)

    def _end_seg_drag(self):
        if self._seg_drag is None:
            return
        # Guardar los waypoints actuales ANTES de limpiar el drag
        final_wps = [QPointF(p) for p in self.waypoints]
        self._seg_drag = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        # Marcar ruta como manual y conservar los waypoints resultantes del drag
        self._user_waypoints = True
        self.waypoints = final_wps
        # Reconstruir path: waypoints ya incluye stubs, solo añadir extremos
        raw = ([self._src_pos()]
               + list(self.waypoints)
               + [self._dst_pos()])
        pts = self._cleanup(self._normalize(raw))
        self.waypoints = [QPointF(p) for p in pts[1:-1]]
        self._redraw_path_only(pts)
        self._sync_handles()
        # Actualizar bifurcaciones adheridas a esta conexión
        self._update_branch_nodes(pts)
        try:
            if self._scene:
                self._scene.rebuild_junctions()
        except Exception:
            pass

    # ── eventos ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            sp  = event.scenePos()
            mod = event.modifiers()
            # Shift+clic → dejar que el view cree el BranchNode (no consumir)
            if mod & Qt.KeyboardModifier.ShiftModifier:
                event.ignore()
                return
            # Alt+clic → liberar ruta manual para que Hanan la recalcule
            if mod & Qt.KeyboardModifier.AltModifier:
                self._user_waypoints = False
                self.waypoints.clear()
                self.update_path()
                event.accept()
                return
            # Ctrl+click → insertar nodo (solo si ya seleccionada)
            if mod & Qt.KeyboardModifier.ControlModifier:
                if not self.isSelected():
                    # Primero seleccionar
                    sc = self.scene()
                    if sc: sc.clearSelection()
                    self.setSelected(True)
                else:
                    self._insert_node(sp)
                event.accept()
                return
            # Drag de segmento → solo si ya seleccionada
            if self.isSelected():
                pts = self._full_pts()
                seg = self._find_segment(sp, pts)
                if seg >= 0:
                    self._start_seg_drag(seg, pts, sp)
                    event.accept()
                    return
            # Clic simple → seleccionar esta conexión, deseleccionar resto
            sc = self.scene()
            if sc:
                sc.clearSelection()
            self.setSelected(True)
            # Forzar visibilidad de handles: itemChange puede no disparar si
            # clearSelection() ya había deseleccionado esta conexión antes
            self._set_handles_visible(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._seg_drag is not None:
            self._apply_seg_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (self._seg_drag is not None
                and event.button() == Qt.MouseButton.LeftButton):
            self._end_seg_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        pts = self._full_pts()
        seg = self._find_segment(event.scenePos(), pts)
        n = len(pts)
        if seg >= 0 and 0 < seg < n - 1:
            self.setCursor(Qt.CursorShape.SizeVerCursor
                           if self._seg_is_h(pts, seg)
                           else Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    # ── tipo de señal ────────────────────────────────────────────────────

    def signal_type(self) -> str:
        """Devuelve 'digital' o 'analog' según el tipo del puerto conectado.
        Prioridad: src → dst → parent_conn de BranchNode → 'analog'.
        """
        from items.branch_node import BranchNode as _BN
        for item, is_slot in ((self.src_item, self.src_is_slot),
                              (self.dst_item, self.dst_is_slot)):
            if is_slot:
                continue
            if isinstance(item, _BN):
                try:
                    st = item.parent_conn.signal_type()
                    if st in ('digital', 'analog'): return st
                except Exception:
                    pass
                continue
            st = getattr(item, 'signal_type', None)
            if st in ('digital', 'analog'):
                return st
        return 'analog'

    # ── selección / pintura ──────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self._set_handles_visible(bool(value))
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        pen = QPen(self.pen())
        # Tipo de señal: trazos = digital, continuo = analog
        if self.signal_type() == 'digital':
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([4.0, 3.0])
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        if self.isSelected():
            pen.setColor(QColor(CONN_SEL_COLOR))
            pen.setWidthF(CONN_PEN_W * 1.8)
        painter.setPen(pen)
        painter.drawPath(self.path())
        # Cuando está seleccionada, mostrar puntos en los extremos src y dst
        if self.isSelected():
            from PyQt6.QtGui import QBrush as _Brush
            solid = QPen(QColor(CONN_SEL_COLOR), mm(0.3))
            solid.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(solid)
            painter.setBrush(_Brush(QColor(CONN_SEL_COLOR)))
            r = mm(1.0)
            for pt in (self._src_pos(), self._dst_pos()):
                painter.drawEllipse(pt, r, r)

    # ── limpieza ─────────────────────────────────────────────────────────

    def remove(self):
        if self._seg_drag is not None:
            try: self.ungrabMouse()
            except RuntimeError: pass
        for h in self._handles:
            try:
                if h.scene(): h.scene().removeItem(h)
            except RuntimeError: pass
        self._handles.clear()
        for item in (self.src_item, self.dst_item):
            try:
                if self in item.connections:
                    item.connections.remove(self)
            except (ValueError, AttributeError, RuntimeError):
                pass
        try:
            if self.scene(): self.scene().removeItem(self)
        except RuntimeError:
            pass

    def waypoints_as_tuples(self) -> list[tuple]:
        """Serializa siempre: la ruta fijada (stub_src → interior → stub_dst)."""
        return [(wp.x(), wp.y()) for wp in self.waypoints]


# ── helpers ───────────────────────────────────────────────────────────────

def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(b.x()-a.x(), b.y()-a.y())

def _dist_pt_seg(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x()-a.x(), b.y()-a.y()
    if dx == 0 and dy == 0:
        return _dist(p, a)
    t = max(0.0, min(1.0,
        ((p.x()-a.x())*dx + (p.y()-a.y())*dy) / (dx*dx+dy*dy)))
    return _dist(p, QPointF(a.x()+t*dx, a.y()+t*dy))
