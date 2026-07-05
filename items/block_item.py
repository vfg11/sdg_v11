"""
items/block_item.py — Bloque central con puertos izq/der.
Fuentes con setPixelSize.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsItem,
                              QGraphicsTextItem)
from PyQt6.QtGui import QPen, QBrush, QColor, QFont
from PyQt6.QtCore import QRectF, QPointF
from const import (BLOCK_MIN_W, BLOCK_MIN_H, BLOCK_PORT_SEP,
                   F_BLOCK_TYPE, F_BLOCK_KKS, F_PORT_LABEL,
                   COLOR_BLOCK_BDR, mm)
from model import BlockData, PortData, LIBRARY_BY_ID
from items.port_item import PortItem
from symbols import parse_inscription, draw_symbol_qt


class BlockItem(QGraphicsRectItem):

    def __init__(self, data: BlockData, scene):
        super().__init__()
        self.data   = data
        self._scene = scene
        self.port_items_in:  list[PortItem] = []
        self.port_items_out: list[PortItem] = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self._compute_size()
        self._build()

    def _compute_size(self):
        n_max = max(len(self.data.inputs), len(self.data.outputs), 1)
        h = max(BLOCK_MIN_H, mm(5) + n_max * BLOCK_PORT_SEP)
        if self.data.w > 0:
            w = self.data.w
        else:
            bt = LIBRARY_BY_ID.get(self.data.type_id)
            w = mm(getattr(bt, 'width_mm', 0)) if bt and getattr(bt, 'width_mm', 0) > 0 else BLOCK_MIN_W
        h = self.data.h if self.data.h > 0 else h
        self.data.w = w; self.data.h = h
        self.setRect(0, 0, w, h)
        self.setPos(self.data.x, self.data.y)

    def _build(self):
        bt = LIBRARY_BY_ID.get(self.data.type_id)
        bg_color = bt.color if bt else '#E8F0FE'
        self.setBrush(QBrush(QColor(bg_color)))
        self.setPen(QPen(QColor(COLOR_BLOCK_BDR), mm(0.5)))

        r = self.rect()

        # ── Etiqueta de tipo (parte superior) — solo si show_type_label ──
        type_name = bt.name if bt else self.data.type_id
        show_lbl  = getattr(self.data, 'show_type_label', False)
        if show_lbl:
            f_type = QFont('Segoe UI')
            f_type.setPixelSize(F_BLOCK_TYPE)
            f_type.setBold(True)
            self._lbl_type = QGraphicsTextItem(type_name, self)
            self._lbl_type.setFont(f_type)
            self._lbl_type.setDefaultTextColor(QColor('#1a2a4a'))
            tw = self._lbl_type.boundingRect().width()
            self._lbl_type.setPos(r.width()/2 - tw/2, mm(1))

        # ── Inscripción centrada (texto, símbolo /NNN o mezcla) ──
        insc = self.data.inscription or (getattr(bt, 'inscription', '') if bt else '')
        if insc:
            from symbols import tokenize_inscription
            tokens = tokenize_inscription(insc)
            # Caso simple: un único token símbolo → dibujo vectorial
            if len(tokens) == 1 and tokens[0][0] == 'symbol':
                self._lbl_insc = _SymbolItem(tokens[0][1], r.width(), r.height(), self)
                self._lbl_insc.setPos(0, 0)
            else:
                # Mezcla símbolo+texto o texto puro
                from symbols import SYMBOLS as _SYMS
                sym_tokens = [t for t in tokens if t[0] == 'symbol']
                txt_tokens = [t for t in tokens if t[0] == 'text']
                txt_str = ''.join(t[1] for t in txt_tokens).strip()
                if sym_tokens and txt_str:
                    # Símbolo vectorial en parte izquierda + texto a la derecha
                    sym_w = r.width() * 0.55
                    self._lbl_insc = _SymbolItem(
                        sym_tokens[0][1], sym_w, r.height(), self)
                    self._lbl_insc.setPos(0, 0)
                    f_insc = QFont('Segoe UI')
                    f_insc.setPixelSize(int(F_BLOCK_TYPE * 1.5))
                    self._lbl_txt_suffix = QGraphicsTextItem(txt_str, self)
                    self._lbl_txt_suffix.setFont(f_insc)
                    self._lbl_txt_suffix.setDefaultTextColor(QColor('#334466'))
                    sw = self._lbl_txt_suffix.boundingRect().width()
                    sh = self._lbl_txt_suffix.boundingRect().height()
                    self._lbl_txt_suffix.setPos(
                        sym_w + (r.width() - sym_w) / 2 - sw / 2,
                        r.height() / 2 - sh / 2)
                else:
                    # Solo texto
                    val = ''.join(t[1] for t in tokens)
                    f_insc = QFont('Segoe UI')
                    f_insc.setPixelSize(int(F_BLOCK_TYPE * 1.5))
                    self._lbl_insc = QGraphicsTextItem(val, self)
                    self._lbl_insc.setFont(f_insc)
                    self._lbl_insc.setDefaultTextColor(QColor('#334466'))
                    iw = self._lbl_insc.boundingRect().width()
                    ih = self._lbl_insc.boundingRect().height()
                    self._lbl_insc.setPos(
                        r.width()/2 - iw/2, r.height()/2 - ih/2)

        # ── Etiqueta (centrado, parte inferior) — KKS no se muestra en canvas ──
        kks_txt = self.data.label if (self.data.label and self.data.label != type_name) else ''
        _ = LIBRARY_BY_ID  # evitar warning de import no usado
        if kks_txt:
            f_kks = QFont('Courier New')
            f_kks.setPixelSize(F_BLOCK_KKS)
            self._lbl_kks = QGraphicsTextItem(kks_txt, self)
            self._lbl_kks.setFont(f_kks)
            self._lbl_kks.setDefaultTextColor(QColor('#334466'))
            kw = self._lbl_kks.boundingRect().width()
            kh = self._lbl_kks.boundingRect().height()
            self._lbl_kks.setPos(r.width()/2 - kw/2,
                                  r.height() - kh - mm(1))

        # ── Puertos ──
        self._build_ports()

    def _build_ports(self):
        r     = self.rect()
        n_in  = len(self.data.inputs)
        n_out = len(self.data.outputs)
        for i, pd in enumerate(self.data.inputs):
            py = self._port_y(i, n_in, r.height())
            p  = PortItem('in', i, pd.name, self,
                          signal_type=getattr(pd, 'signal_type', 'analog'),
                          negated=getattr(pd, 'negated', False))
            p.setPos(0, py)
            self._port_label(p, pd.label(), 'in', r)
            self.port_items_in.append(p)
        for i, pd in enumerate(self.data.outputs):
            py = self._port_y(i, n_out, r.height())
            p  = PortItem('out', i, pd.name, self,
                          signal_type=getattr(pd, 'signal_type', 'analog'),
                          negated=getattr(pd, 'negated', False))
            p.setPos(r.width(), py)
            self._port_label(p, pd.label(), 'out', r)
            self.port_items_out.append(p)

    def _port_label(self, port_item: PortItem, text: str, side: str, r):
        if not text: return
        f = QFont('Segoe UI')
        f.setPixelSize(F_PORT_LABEL)
        lbl = QGraphicsTextItem(text, self)
        lbl.setFont(f)
        lbl.setDefaultTextColor(QColor('#334466'))
        lw = lbl.boundingRect().width()
        lh = lbl.boundingRect().height()
        px = port_item.pos().x()
        py = port_item.pos().y() - lh/2
        if side == 'in':
            lbl.setPos(px + mm(1.5), py)
        else:
            lbl.setPos(px - lw - mm(1.5), py)

    def _port_y(self, i, n, h):
        total = n * BLOCK_PORT_SEP
        start = (h - total) / 2 + BLOCK_PORT_SEP / 2
        return start + i * BLOCK_PORT_SEP

    def in_port_scene_pos(self, idx) -> QPointF:
        if 0 <= idx < len(self.port_items_in):
            return self.port_items_in[idx].scenePos()
        return self.scenePos()

    def out_port_scene_pos(self, idx) -> QPointF:
        if 0 <= idx < len(self.port_items_out):
            return self.port_items_out[idx].scenePos()
        return self.scenePos()

    def _port_connections(self):
        """Todas las conexiones que tocan algún puerto de este bloque."""
        seen = set()
        result = []
        for p in self.port_items_in + self.port_items_out:
            for conn in p.connections:
                if id(conn) not in seen:
                    seen.add(id(conn))
                    result.append(conn)
        return result

    def mousePressEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            # Activar routing live en todas las conexiones del bloque
            for conn in self._port_connections():
                try:
                    conn.save_branch_t()
                    conn._routing_live   = True
                    conn._user_waypoints = False
                    conn.waypoints.clear()
                    conn._route_cache    = None
                except Exception:
                    pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            sc = self.scene()
            # Desactivar live y persistir ruta final en conexiones propias
            port_conns = self._port_connections()
            for conn in port_conns:
                try:
                    conn._routing_live   = False
                    conn._user_waypoints = False
                    conn.waypoints.clear()
                    conn._route_cache    = None
                    conn.update_path()   # también reposiciona BranchNodes via _update_branch_nodes
                except Exception:
                    pass
            # Persistir rutas de las conexiones hijo de cualquier BranchNode
            # que viva sobre una conexión del bloque (update_path en modo live
            # solo hace _redraw_path_only, no persiste waypoints)
            if sc and hasattr(sc, 'branch_nodes'):
                already = set(id(c) for c in port_conns)
                for bn in list(sc.branch_nodes):
                    try:
                        if bn.parent_conn not in port_conns:
                            continue
                        for child_conn in list(bn.connections):
                            if id(child_conn) in already:
                                continue
                            already.add(id(child_conn))
                            child_conn._routing_live   = False
                            child_conn._user_waypoints = False
                            child_conn.waypoints.clear()
                            child_conn._route_cache    = None
                            child_conn.update_path()
                    except Exception:
                        pass
            if sc and hasattr(sc, 'rebuild_junctions'):
                sc.rebuild_junctions()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data.x = self.pos().x()
            self.data.y = self.pos().y()
            # Invalidar caché global de obstáculos
            sc = self.scene()
            if sc and hasattr(sc, 'conn_items'):
                for ci in sc.conn_items:
                    try:
                        ci._route_cache = None
                        ci._route_cache_key = None
                    except Exception:
                        pass
            # Redibujar conexiones propias en modo live (o normal si no está en drag)
            for conn in self._port_connections():
                try:
                    conn.update_path(invalidate_cache=True)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor('#0033AA'), mm(0.8)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor(COLOR_BLOCK_BDR), mm(0.5)))
        super().hoverLeaveEvent(event)

    def refresh(self):
        """Reconstruye el bloque conservando las referencias de ConnItems a sus puertos."""
        # 1. Capturar qué ConnItems tocan cada puerto, identificando si es src o dst
        def _conn_role(ci, port):
            """Devuelve 'src', 'dst' o None según qué extremo del ConnItem es port."""
            if getattr(ci, 'src_item', None) is port:
                return 'src'
            if getattr(ci, 'dst_item', None) is port:
                return 'dst'
            return None

        in_snapshot  = [(list(p.connections), p) for p in self.port_items_in]
        out_snapshot = [(list(p.connections), p) for p in self.port_items_out]

        # 2. Desconectar ConnItems de los puertos viejos sin destruirlos aún
        for conns, p in in_snapshot + out_snapshot:
            for ci in conns:
                try: p.connections.remove(ci)
                except ValueError: pass

        # 3. Destruir children y listas de puertos
        for child in self.childItems():
            child.setParentItem(None)
        self.port_items_in.clear()
        self.port_items_out.clear()

        # 4. Reconstruir
        self._compute_size()
        self._build()

        # 5. Reasignar ConnItems a los puertos nuevos (mismos índices)
        affected = set()
        for i, (conns, _old_port) in enumerate(in_snapshot):
            if i >= len(self.port_items_in):
                continue
            new_p = self.port_items_in[i]
            for ci in conns:
                role = _conn_role(ci, _old_port)
                if role == 'src':
                    ci.src_item = new_p
                elif role == 'dst':
                    ci.dst_item = new_p
                if ci not in new_p.connections:
                    new_p.connections.append(ci)
                affected.add(ci)

        for i, (conns, _old_port) in enumerate(out_snapshot):
            if i >= len(self.port_items_out):
                continue
            new_p = self.port_items_out[i]
            for ci in conns:
                role = _conn_role(ci, _old_port)
                if role == 'src':
                    ci.src_item = new_p
                elif role == 'dst':
                    ci.dst_item = new_p
                if ci not in new_p.connections:
                    new_p.connections.append(ci)
                affected.add(ci)

        # 6. Redibujar todas las conexiones afectadas
        for ci in affected:
            try:
                ci._route_cache = None
                ci.update_path(invalidate_cache=True)
            except Exception:
                pass

    def save(self) -> dict:
        return {
            'block_id':       self.data.block_id,
            'type_id':        self.data.type_id,
            'kks':            self.data.kks,
            'label':          self.data.label,
            'inscription':    self.data.inscription,
            'show_type_label':getattr(self.data, 'show_type_label', False),
            'x': self.data.x, 'y': self.data.y,
            'w': self.data.w, 'h': self.data.h,
            'inputs':  [{'name': p.name, 'number': p.number,
                         'signal_type': getattr(p, 'signal_type', 'analog'),
                         'negated':     getattr(p, 'negated', False)}
                        for p in self.data.inputs],
            'outputs': [{'name': p.name, 'number': p.number,
                         'signal_type': getattr(p, 'signal_type', 'analog'),
                         'negated':     getattr(p, 'negated', False)}
                        for p in self.data.outputs],
        }


# ── Item gráfico para símbolo /NNN dentro de un bloque ───────────────────

class _SymbolItem(QGraphicsItem):
    """Dibuja un símbolo del catálogo centrado en el área del bloque."""

    def __init__(self, sym_idx: int, bw: float, bh: float, parent=None):
        super().__init__(parent)
        self._idx = sym_idx
        self._bw  = bw
        self._bh  = bh

    def boundingRect(self):
        return QRectF(0, 0, self._bw, self._bh)

    def paint(self, painter, option, widget=None):
        from PyQt6.QtGui import QPen
        from PyQt6.QtCore import Qt
        # Área del símbolo: 62 % del lado menor, centrada
        margin = 0.19
        side   = min(self._bw, self._bh) * (1 - 2 * margin)
        x = (self._bw - side) / 2
        y = (self._bh - side) / 2
        pen = QPen(QColor('#334466'), mm(0.4))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        draw_symbol_qt(painter, self._idx, x, y, side, side)
