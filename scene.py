"""
scene.py — QGraphicsScene para una hoja del documento.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QFont
from PyQt6.QtCore import QRectF, QPointF, Qt

from const import (PAGE_W, PAGE_H, HEADER_H, TB_Y, TB_H,
                   WORK_Y, WORK_H, COL_W, COL_L_X, COL_R_X,
                   CANVAS_X, CANVAS_Y, CANVAS_W, CANVAS_H,
                   GRID, mm, COLOR_PAGE, COLOR_COL_BG, COLOR_COL_BORDER,
                   COLOR_GRID, COLOR_HEADER, COLOR_HEADER_TXT,
                   F_HEADER_TITLE, F_HEADER_INFO, F_COL_LABEL)
from model import (SheetData, BlockData, PortData, ConnectionData,
                   EndpointRef, LIBRARY_BY_ID, TitleBlockData, DocumentData)
from items.slot_item import SlotItem
from items.block_item import BlockItem
from items.port_item import PortItem
from items.conn_item import ConnItem
from items.titleblock_item import TitleBlockItem
from items.symbol_item import SymbolItem
from items.note_item import NoteItem
from items.textbox_item import TextBoxItem
from items.junction_item import JunctionOverlay, compute_junctions
from items.branch_node import BranchNode


class DiagramScene(QGraphicsScene):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(0, 0, PAGE_W, PAGE_H)

        self.document:   DocumentData | None = None
        self.sheet_idx:  int = 0

        self.slot_items_left:  list[SlotItem]  = []
        self.slot_items_right: list[SlotItem]  = []
        self.block_items:      list[BlockItem] = []
        self.conn_items:       list[ConnItem]  = []
        self._junction_items:  list             = []
        self.branch_nodes:     list             = []
        self._preview_mode:    bool             = False  # True durante trazado preview
        self.symbol_items:     list[SymbolItem] = []
        self.note_items:       list[NoteItem]    = []
        self.textbox_items:    list               = []
        self._tb_item:         TitleBlockItem | None = None

    @property
    def sheet(self) -> SheetData | None:
        if self.document:
            return self.document.sheet_at(self.sheet_idx)
        return None

    def group(self):
        """Grupo al que pertenece la hoja actual."""
        if self.document:
            return self.document.group_at(self.sheet_idx)
        return None

    # ── carga ─────────────────────────────────────────────────────────────

    def load_sheet(self, document: DocumentData, sheet_idx: int):
        self.document  = document
        self.sheet_idx = sheet_idx
        self.clear_all()
        s = self.sheet
        if s is not None:
            try:
                from io_utils.db_io import load_sheet_content, resolve_sheet_links
                load_sheet_content(s)
                resolve_sheet_links(document, s)   # incremental: solo esta hoja
            except Exception:
                pass
        self._build_page()

    def _build_page(self):
        s = self.sheet
        if s is None: return
        self._draw_background()
        self._draw_header()
        self._draw_columns(s)
        self._draw_grid()
        self._draw_title_block()
        self._restore_blocks(s)
        self._restore_textboxes(s)   # antes de conexiones — textbox puede ser endpoint
        self._restore_connections(s)
        self._restore_symbols(s)
        self._restore_notes(s)

    def _draw_background(self):
        r = self.addRect(0, 0, PAGE_W, PAGE_H,
                         QPen(Qt.PenStyle.NoPen), QBrush(QColor(COLOR_PAGE)))
        r.setZValue(-10)

    def _draw_header(self):
        tb  = self.document.title_block
        hdr = self.addRect(0, 0, PAGE_W, HEADER_H,
                           QPen(Qt.PenStyle.NoPen), QBrush(QColor(COLOR_HEADER)))
        hdr.setZValue(-5)

        ft = QFont('Segoe UI')
        ft.setPixelSize(F_HEADER_TITLE); ft.setBold(True)
        ti = self.addText(tb.title or 'Sin título', ft)
        ti.setDefaultTextColor(QColor(COLOR_HEADER_TXT))
        ti.setPos(mm(4), (HEADER_H - ti.boundingRect().height()) / 2)
        ti.setZValue(-4)

        s   = self.sheet
        num = self.document.sheet_ref(self.sheet_idx) if self.document else str(self.sheet_idx + 1)
        lbl = f"Hoja {num}   {tb.doc_number}"
        ft2 = QFont('Segoe UI'); ft2.setPixelSize(F_HEADER_INFO)
        ri  = self.addText(lbl, ft2)
        ri.setDefaultTextColor(QColor('#aabbcc'))
        ri.setPos(PAGE_W - ri.boundingRect().width() - mm(4),
                  (HEADER_H - ri.boundingRect().height()) / 2)
        ri.setZValue(-4)

    def _draw_columns(self, s: SheetData):
        pen   = QPen(QColor(COLOR_COL_BORDER), mm(0.3))
        brush = QBrush(QColor(COLOR_COL_BG))
        self.addRect(COL_L_X, WORK_Y, COL_W, WORK_H, pen, brush).setZValue(-4)
        self.addRect(COL_R_X, WORK_Y, COL_W, WORK_H, pen, brush).setZValue(-4)

        ft_col = QFont('Segoe UI'); ft_col.setPixelSize(F_COL_LABEL); ft_col.setBold(True)
        for txt, cx in [('ENTRADAS', COL_L_X + mm(2)), ('SALIDAS', COL_R_X + mm(2))]:
            lbl = self.addText(txt, ft_col)
            lbl.setDefaultTextColor(QColor('#445566'))
            lbl.setPos(cx, WORK_Y + mm(0.5))
            lbl.setZValue(-3)

        sh     = WORK_H / s.num_slots
        slot_y = WORK_Y
        for i in range(s.num_slots):
            sl = SlotItem(s.slots_left[i],  i, 'left',  COL_L_X, slot_y, COL_W, sh, self)
            sr = SlotItem(s.slots_right[i], i, 'right', COL_R_X, slot_y, COL_W, sh, self)
            sl.setZValue(1); sr.setZValue(1)
            self.addItem(sl); self.addItem(sr)
            self.slot_items_left.append(sl)
            self.slot_items_right.append(sr)
            slot_y += sh

    def _draw_grid(self):
        pen = QPen(QColor(COLOR_GRID), mm(0.05))
        pen.setStyle(Qt.PenStyle.DotLine)
        x = CANVAS_X
        while x <= CANVAS_X + CANVAS_W:
            self.addLine(x, CANVAS_Y, x, CANVAS_Y + CANVAS_H, pen).setZValue(-8)
            x += GRID
        y = CANVAS_Y
        while y <= CANVAS_Y + CANVAS_H:
            self.addLine(CANVAS_X, y, CANVAS_X + CANVAS_W, y, pen).setZValue(-8)
            y += GRID

    def _draw_title_block(self):
        self._tb_item = TitleBlockItem(
            self.document.title_block, self.sheet, self.sheet_idx, self.document)
        self.addItem(self._tb_item)

    def _restore_blocks(self, s: SheetData):
        for bd in s.blocks:
            bi = BlockItem(bd, self)
            bi.setZValue(3)
            self.addItem(bi)
            self.block_items.append(bi)

    def _restore_connections(self, s: SheetData):
        """Restaura conexiones en 3 pasadas para soportar BranchNodes.

        Pasada 1: conexiones sin endpoints 'branch' → crea ConnItems normales.
        Pasada 2: recrea BranchNodes usando su branch_id, parent_conn_id y posición.
        Pasada 3: conexiones con endpoint 'branch' → usa el mapa branch_id→BranchNode.
        """
        from model import BranchNodeData
        bid_map = {bi.data.block_id: bi for bi in self.block_items}
        sid_map = {si.sym_id: si for si in self.symbol_items}

        # ── Pasada 1: conexiones normales ──────────────────────────────
        conn_id_map: dict = {}    # conn_id → ConnItem
        deferred   : list = []    # ConnectionData con extremo 'branch'

        for cd in s.connections:
            has_branch = (cd.src.kind == 'branch' or cd.dst.kind == 'branch')
            if has_branch:
                deferred.append(cd)
                continue
            try:
                src, src_slot = self._resolve(cd.src, bid_map, sid_map)
                dst, dst_slot = self._resolve(cd.dst, bid_map, sid_map)
                if src and dst:
                    wps = [QPointF(x, y) for x, y in cd.waypoints]
                    ci  = ConnItem(src, src_slot, dst, dst_slot, self, wps)
                    ci.conn_id = cd.conn_id          # asignar el conn_id guardado
                    self.conn_items.append(ci)
                    conn_id_map[cd.conn_id] = ci
            except Exception as e:
                print(f'Conexión no restaurada (pasada 1): {e}')

        # ── Pasada 2: reconstruir BranchNodes ─────────────────────────
        bn_map: dict = {}    # branch_id → BranchNode

        for bnd in getattr(s, 'branch_nodes', []):
            parent_ci = conn_id_map.get(bnd.parent_conn_id)
            if parent_ci is None:
                print(f'BranchNode {bnd.branch_id}: parent_conn no encontrado')
                continue
            pos = QPointF(bnd.x, bnd.y)
            bn  = self.add_branch_node(parent_ci, pos, branch_id=bnd.branch_id)
            bn_map[bnd.branch_id] = bn

        # ── Pasada 3: conexiones con extremo branch ────────────────────
        for cd in deferred:
            try:
                src, src_slot = self._resolve_with_bn(cd.src, bid_map, sid_map, bn_map)
                dst, dst_slot = self._resolve_with_bn(cd.dst, bid_map, sid_map, bn_map)
                if src and dst:
                    wps = [QPointF(x, y) for x, y in cd.waypoints]
                    ci  = ConnItem(src, src_slot, dst, dst_slot, self, wps)
                    ci.conn_id = cd.conn_id
                    self.conn_items.append(ci)
                    conn_id_map[cd.conn_id] = ci
            except Exception as e:
                print(f'Conexión no restaurada (pasada 3): {e}')

    def _resolve(self, ep: EndpointRef, bid_map: dict, sid_map: dict | None = None):
        if ep.kind == 'slot_left':
            return self.slot_items_left[ep.port_idx], True
        elif ep.kind == 'slot_right':
            return self.slot_items_right[ep.port_idx], True
        elif ep.kind == 'block_out':
            bi = bid_map.get(ep.item_id)
            return (bi.port_items_out[ep.port_idx], False) if bi else (None, False)
        elif ep.kind == 'block_in':
            bi = bid_map.get(ep.item_id)
            return (bi.port_items_in[ep.port_idx], False) if bi else (None, False)
        elif ep.kind == 'textbox_out':
            tbx_map = {tb.textbox_id: tb for tb in self.textbox_items}
            tb = tbx_map.get(ep.item_id)
            return (tb.port_item, False) if tb and tb.port_item else (None, False)
        elif ep.kind in ('sym_out', 'sym_in') and sid_map:
            si = sid_map.get(ep.item_id)
            return (si.port_item(), False) if si else (None, False)
        return None, False

    def _resolve_with_bn(self, ep: EndpointRef, bid_map: dict,
                         sid_map: dict | None, bn_map: dict):
        """Como _resolve pero también resuelve endpoints 'branch'."""
        if ep.kind == 'branch':
            bn = bn_map.get(ep.item_id)
            return (bn, False) if bn else (None, False)
        return self._resolve(ep, bid_map, sid_map)

    # ── API pública ───────────────────────────────────────────────────────

    def add_block(self, data: BlockData) -> BlockItem:
        self.sheet.blocks.append(data)
        bi = BlockItem(data, self)
        bi.setZValue(3)
        self.addItem(bi)
        self.block_items.append(bi)
        return bi

    def remove_block(self, bi: BlockItem):
        for p in bi.port_items_in + bi.port_items_out:
            for conn in list(p.connections):
                self.remove_conn(conn)
        self.block_items.remove(bi)
        if bi.data in self.sheet.blocks:
            self.sheet.blocks.remove(bi.data)
        self.removeItem(bi)

    def add_conn(self, src, src_is_slot, dst, dst_is_slot,
                 waypoints=None) -> ConnItem:
        ci = ConnItem(src, src_is_slot, dst, dst_is_slot, self, waypoints)
        self.conn_items.append(ci)
        self.sheet.connections.append(self._conn_to_model(ci))
        self.rebuild_junctions()
        return ci

    def remove_conn(self, ci: ConnItem):
        """Elimina una conexión y todo su árbol de derivaciones (recursivo)."""
        # Recopilar todo el árbol: conn + todos los ConnItems descendientes
        # usando BFS para manejar ramificaciones de cualquier profundidad
        all_conns: list  = []
        all_bns:   list  = []
        queue = [ci]
        visited_conns = set()
        while queue:
            cur = queue.pop(0)
            if id(cur) in visited_conns:
                continue
            visited_conns.add(id(cur))
            all_conns.append(cur)
            # Buscar BranchNodes cuyo parent_conn es este ConnItem
            for bn in list(self.branch_nodes):
                try:
                    if bn.parent_conn is not cur:
                        continue
                    if id(bn) in {id(b) for b in all_bns}:
                        continue
                    all_bns.append(bn)
                    # Encolar las conexiones hijo del branch
                    for child in list(bn.connections):
                        queue.append(child)
                except Exception:
                    pass

        # Eliminar en orden: primero conexiones hoja, luego raíz
        for conn in all_conns:
            try:
                mc = self._find_model_conn(conn)
                if mc and mc in self.sheet.connections:
                    self.sheet.connections.remove(mc)
                if conn in self.conn_items:
                    self.conn_items.remove(conn)
                conn.remove()
            except Exception:
                pass

        # Eliminar los BranchNodes del árbol
        for bn in all_bns:
            try:
                if bn in self.branch_nodes:
                    self.branch_nodes.remove(bn)
                if bn.scene():
                    self.removeItem(bn)
            except (RuntimeError, Exception):
                pass

        self.prune_orphan_branches()
        self.rebuild_junctions()

    def _conn_to_model(self, ci: ConnItem) -> ConnectionData:
        from items.symbol_item import SymbolItem as _SI
        from items.branch_node import BranchNode as _BN
        def ep(item, is_slot) -> EndpointRef:
            if is_slot:
                si = item
                kind = 'slot_left' if si.side == 'left' else 'slot_right'
                return EndpointRef(kind=kind, item_id=si.data.slot_id,
                                   port_idx=si.index)
            # BranchNode: usar su branch_id persistente
            if isinstance(item, _BN):
                return EndpointRef(kind='branch',
                                   item_id=item.branch_id,
                                   port_idx=0)
            pi   = item
            par  = pi.parentItem()
            # Puerto de SymbolItem
            if isinstance(par, _SI):
                kind = 'sym_out' if pi.side == 'out' else 'sym_in'
                return EndpointRef(kind=kind,
                                   item_id=par.sym_id,
                                   port_idx=0)
            # Puerto de TextBoxItem
            from items.textbox_item import TextBoxItem as _TBI
            if isinstance(par, _TBI):
                return EndpointRef(kind='textbox_out',
                                   item_id=par.textbox_id,
                                   port_idx=0)
            # Puerto de BlockItem normal
            if par is None:
                return EndpointRef(kind='unknown', item_id='', port_idx=0)
            bi   = par
            kind = 'block_out' if pi.side == 'out' else 'block_in'
            return EndpointRef(kind=kind, item_id=bi.data.block_id,
                               port_idx=pi.index)
        return ConnectionData(
            conn_id=ci.conn_id,
            src=ep(ci.src_item, ci.src_is_slot),
            dst=ep(ci.dst_item, ci.dst_is_slot),
            waypoints=ci.waypoints_as_tuples(),
        )

    def _find_model_conn(self, ci: ConnItem) -> ConnectionData | None:
        src_key = self._item_ep_key(ci.src_item, ci.src_is_slot)
        dst_key = self._item_ep_key(ci.dst_item, ci.dst_is_slot)
        for cd in self.sheet.connections:
            if (self._ep_key(cd.src) == src_key and
                    self._ep_key(cd.dst) == dst_key):
                return cd
        return None

    def _item_ep_key(self, item, is_slot):
        from items.branch_node import BranchNode as _BN
        if is_slot: return (item.side, item.index)
        if isinstance(item, _BN): return ('branch', id(item))
        pi = item; bi = pi.parentItem()
        from items.textbox_item import TextBoxItem as _TBI
        if isinstance(bi, _TBI): return ('textbox_out', bi.textbox_id, 0)
        if bi is None: return ('unknown', id(item))
        return (pi.side, bi.data.block_id, pi.index)

    def _ep_key(self, ep: EndpointRef):
        if ep.kind in ('slot_left','slot_right'):
            return ('left' if ep.kind=='slot_left' else 'right', ep.port_idx)
        return ('out' if ep.kind=='block_out' else 'in', ep.item_id, ep.port_idx)

    # ── hit-test ──────────────────────────────────────────────────────────

    def item_at_pos(self, pos: QPointF):
        hit = mm(3)
        items = self.items(QRectF(pos.x()-hit, pos.y()-hit, 2*hit, 2*hit))
        # Prioridad 1: ports y slots
        for it in items:
            if isinstance(it, (PortItem, SlotItem)): return it
        # Prioridad 2: items directos conocidos
        for it in items:
            if isinstance(it, (BlockItem, ConnItem, NoteItem, TextBoxItem)): return it
            # hijo de TextBoxItem (QGraphicsTextItem interior)
            p = it.parentItem()
            if isinstance(p, TextBoxItem): return p
        # Prioridad 3: SymbolItem o hijo de SymbolItem
        for it in items:
            if isinstance(it, SymbolItem): return it
            parent = it.parentItem()
            while parent is not None:
                if isinstance(parent, SymbolItem): return parent
                parent = parent.parentItem()
        return None

    def slot_at_pos(self, pos: QPointF) -> SlotItem | None:
        for sl in self.slot_items_left + self.slot_items_right:
            if sl.rect().adjusted(-mm(2),-mm(2),mm(2),mm(2)).contains(
                    sl.mapFromScene(pos)):
                return sl
        return None

    def port_at_pos(self, pos: QPointF):
        """Devuelve PortItem, puerto de SymbolItem, o None."""
        hit = mm(5)
        items = self.items(QRectF(pos.x()-hit, pos.y()-hit, 2*hit, 2*hit))
        # PortItem normal
        for it in items:
            if isinstance(it, PortItem): return it
        # Puerto de símbolo de campo (QGraphicsEllipseItem hijo)
        for si in self.symbol_items:
            try:
                port = si.port_item()
                sp   = port.scenePos()
                if abs(sp.x()-pos.x()) < hit and abs(sp.y()-pos.y()) < hit:
                    return port
            except RuntimeError:
                pass
        return None

    # ── sincronización al modelo ──────────────────────────────────────────

    def _restore_symbols(self, s):
        for sd in s.symbols:
            si = SymbolItem(sd.sym_type, sd.port_side, sd.x, sd.y,
                            sd.kks, s.num_slots)
            if sd.sym_id:           # restaurar sym_id para que los conexiones casen
                si.sym_id = sd.sym_id
            self.addItem(si)
            self.symbol_items.append(si)

    def _restore_notes(self, s):
        for nd in s.notes:
            ni = NoteItem(text=nd.text, x=nd.x, y=nd.y,
                          font_size_px=getattr(nd, 'font_size_px', 0) or 0,
                          note_id=nd.note_id,
                          text_width=getattr(nd, 'text_width', 0) or 0)
            self.addItem(ni)
            self.note_items.append(ni)

    def _restore_textboxes(self, s):
        for td in getattr(s, 'textboxes', []):
            tb = TextBoxItem(text=td.text, x=td.x, y=td.y,
                             font_size_px=getattr(td, 'font_size_px', 0) or 0,
                             signal_type=getattr(td, 'signal_type', 'analog'),
                             textbox_id=td.textbox_id, scene=self)
            self.addItem(tb)
            self.textbox_items.append(tb)

    def add_symbol(self, sd) -> SymbolItem:
        from model import SymbolData
        ns = self.sheet.num_slots if self.sheet else 12
        si = SymbolItem(sd.sym_type, sd.port_side, sd.x, sd.y, sd.kks, ns)
        sd.sym_id = si.sym_id   # sincronizar el ID del modelo con el del item
        self.addItem(si)
        self.symbol_items.append(si)
        self.sheet.symbols.append(sd)
        # Refrescar las conexiones del slot asociado (offset del stub cambia)
        self._refresh_slot_conns_near(si)
        return si

    def branch_at_pos(self, pos: QPointF):
        """Devuelve el BranchNode más cercano a pos (o None)."""
        from const import mm
        hit = mm(4.0)
        best = None; best_d = hit
        for bn in self.branch_nodes:
            try:
                d = (bn.scenePos() - pos)
                dist = (d.x()**2 + d.y()**2) ** 0.5
                if dist < best_d:
                    best_d = dist; best = bn
            except Exception: pass
        return best

    def add_branch_node(self, parent_conn, scene_pos: QPointF,
                        branch_id: str = '') -> BranchNode:
        bn = BranchNode(parent_conn, scene_pos, self, branch_id=branch_id)
        self.branch_nodes.append(bn)
        return bn

    def remove_branch_node(self, bn: BranchNode):
        if bn in self.branch_nodes:
            self.branch_nodes.remove(bn)
        bn.remove()

    def prune_orphan_branches(self):
        """Elimina branch nodes sin conexiones consolidadas."""
        for bn in list(self.branch_nodes):
            if bn.is_orphan():
                self.branch_nodes.remove(bn)
                try:
                    if bn.scene(): self.removeItem(bn)
                except RuntimeError: pass

    def rebuild_junctions(self):
        """Recalcula y redibuja todos los puntos de derivacion.
        No se ejecuta durante el preview de conexión para no penalizar el rendimiento."""
        if self._preview_mode:
            return
        for ji in self._junction_items:
            try:
                if ji.scene(): self.removeItem(ji)
            except RuntimeError:
                pass
        self._junction_items.clear()
        for pos in compute_junctions(self.conn_items, self.branch_nodes):
            ji = JunctionOverlay(pos, self)
            self._junction_items.append(ji)

    def symbol_for_slot(self, slot_item) -> 'SymbolItem | None':
        """Devuelve el símbolo de campo posicionado en el mismo índice que el slot."""
        from const import WORK_Y, slot_h as _sh
        sh = _sh(self.sheet.num_slots if self.sheet else 23)
        target_idx = slot_item.index
        for si in self.symbol_items:
            try:
                sy = si.pos().y()
                idx = round((sy - WORK_Y) / sh)
                if idx == target_idx and si.port_side == (
                        'out' if slot_item.side == 'right' else 'in'):
                    return si
            except Exception:
                pass
        return None

    def remove_symbol(self, si: SymbolItem):
        port = si.port_item()
        for conn in list(port.connections):
            self.remove_conn(conn)
        if si in self.symbol_items:
            self.symbol_items.remove(si)
        sp = si.pos()
        self.sheet.symbols = [s for s in self.sheet.symbols
                               if not (abs(s.x - sp.x()) < 1 and abs(s.y - sp.y()) < 1)]
        if si.scene():
            self.removeItem(si)
        # Refrescar conexiones del slot ahora que el símbolo ya no está
        self._refresh_slot_conns_near(si)

    def _refresh_slot_conns_near(self, si: 'SymbolItem'):
        """Recalcula conexiones de slots cuya Y coincide con la fila del símbolo."""
        from const import WORK_Y, WORK_H
        try:
            sym_y   = si.pos().y()   # Y de escena del símbolo
            ns      = self.sheet.num_slots if self.sheet else 12
            sh      = WORK_H / max(ns, 1)
            row_tol = sh * 0.6       # tolerancia de fila
        except Exception:
            return
        for slot_item in self.slot_items_left + self.slot_items_right:
            try:
                slot_y = slot_item.mapToScene(slot_item.rect().center()).y()
                if abs(slot_y - (sym_y + si.boundingRect().height()/2)) > row_tol:
                    continue
                for conn in list(slot_item.connections):
                    conn._route_cache    = None
                    conn._user_waypoints = False
                    conn.waypoints.clear()
                    conn.update_path()
            except Exception:
                pass

    def add_note(self, text='Nota…', x=0, y=0) -> NoteItem:
        from model import NoteData
        nd = NoteData(text=text, x=x, y=y)
        self.sheet.notes.append(nd)
        ni = NoteItem(text, x, y, note_id=nd.note_id)
        self.addItem(ni)
        self.note_items.append(ni)
        return ni

    def add_textbox(self, text='Texto', x=0, y=0) -> TextBoxItem:
        from model import TextBoxData
        if not hasattr(self.sheet, 'textboxes'):
            self.sheet.textboxes = []
        td = TextBoxData(text=text, x=x, y=y)
        self.sheet.textboxes.append(td)
        tb = TextBoxItem(text, x, y, textbox_id=td.textbox_id, scene=self)
        self.addItem(tb)
        self.textbox_items.append(tb)
        return tb

    def remove_textbox(self, tb: TextBoxItem):
        if hasattr(self.sheet, 'textboxes'):
            self.sheet.textboxes = [t for t in self.sheet.textboxes
                                     if t.textbox_id != tb.textbox_id]
        if tb.port_item:
            for conn in list(tb.port_item.connections):
                try: self.remove_conn(conn)
                except Exception: pass
        if tb in self.textbox_items:
            self.textbox_items.remove(tb)
        if tb.scene():
            self.removeItem(tb)

    def remove_note(self, ni: NoteItem):
        self.sheet.notes = [n for n in self.sheet.notes if n.note_id != ni.note_id]
        if ni in self.note_items:
            self.note_items.remove(ni)
        if ni.scene():
            self.removeItem(ni)

    def sync_to_model(self):
        s = self.sheet
        if s is None: return
        for bi in self.block_items:
            try:
                bi.data.x = bi.pos().x()
                bi.data.y = bi.pos().y()
            except RuntimeError:
                pass
        s.connections.clear()
        for ci in self.conn_items:
            try:
                s.connections.append(self._conn_to_model(ci))
            except (RuntimeError, AttributeError):
                pass
        # Sync BranchNodes
        from model import BranchNodeData
        if not hasattr(s, 'branch_nodes'): s.branch_nodes = []
        s.branch_nodes.clear()
        for bn in self.branch_nodes:
            try:
                p = bn.scenePos()
                # El conn_id del parent_conn: buscarlo en s.connections via _conn_to_model
                parent_conn_id = ''
                pc = bn.parent_conn
                # Buscar el conn_id correspondiente en las conexiones ya serializadas
                for cd in s.connections:
                    ci_match = next((ci for ci in self.conn_items
                                     if hasattr(ci, 'conn_id') and ci.conn_id == cd.conn_id
                                     and ci is pc), None)
                    if ci_match:
                        parent_conn_id = cd.conn_id
                        break
                # Fallback: buscar por identidad del ConnItem
                if not parent_conn_id:
                    for cd, ci in zip(s.connections, self.conn_items):
                        if ci is pc:
                            parent_conn_id = cd.conn_id
                            break
                s.branch_nodes.append(BranchNodeData(
                    branch_id=bn.branch_id,
                    parent_conn_id=parent_conn_id,
                    x=p.x(), y=p.y(),
                ))
            except (RuntimeError, AttributeError):
                pass
        # Sync símbolos
        s.symbols.clear()
        for si in self.symbol_items:
            try:
                from model import SymbolData
                p = si.pos()
                sv = si.save()
                s.symbols.append(SymbolData(
                    sym_type=sv['sym_type'], port_side=sv['port_side'],
                    kks=sv['kks'], x=p.x(), y=p.y()))
            except RuntimeError:
                pass
        # Sync textboxes
        if not hasattr(s, 'textboxes'): s.textboxes = []
        s.textboxes.clear()
        for tb in self.textbox_items:
            try:
                from model import TextBoxData
                sv = tb.save()
                td = TextBoxData(textbox_id=sv['textbox_id'], text=sv['text'],
                                 x=sv['x'], y=sv['y'],
                                 font_size_px=sv.get('font_size_px', 0),
                                 signal_type=sv.get('signal_type', 'analog'))
                s.textboxes.append(td)
            except RuntimeError:
                pass
        # Sync notas
        s.notes.clear()
        for ni in self.note_items:
            try:
                from model import NoteData
                sv  = ni.save()
                nd  = NoteData(note_id=sv['note_id'], text=sv['text'],
                               x=sv['x'], y=sv['y'])
                nd.font_size_px = sv.get('font_size_px', 0)
                nd.text_width   = sv.get('text_width', 0.0)
                s.notes.append(nd)
            except RuntimeError:
                pass
        # Persistir la hoja en la BD en memoria
        try:
            from io_utils.db_io import sync_sheet
            sync_sheet(s)
        except Exception:
            pass

    def clear_all(self):
        self.clear()
        self.slot_items_left.clear()
        self.slot_items_right.clear()
        self.block_items.clear()
        self.conn_items.clear()
        self.branch_nodes.clear()
        self.symbol_items.clear()
        self.note_items.clear()
        self.textbox_items.clear()
        self._tb_item = None