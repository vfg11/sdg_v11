"""
editor.py — Vista + máquina de estados.
Modos: IDLE, DRAWING_CONN, XSHEET_LINK.

SEGURIDAD: el modo XSHEET_LINK guarda SOLO datos Python puros (PendingXSheetLink).
Nunca almacena referencias a items Qt entre cambios de hoja.
Cuando necesita acceder al item visual lo busca en tiempo real en self._scene.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from PyQt6.QtWidgets import QGraphicsView, QMenu, QApplication
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QKeySequence

from const import (CANVAS_X, CANVAS_Y, CANVAS_W, CANVAS_H, mm, PAGE_W, PAGE_H,
                    COL_W, COL_R_X, SYM_SIZE)
from items.slot_item import SlotItem
from items.block_item import BlockItem
from items.port_item import PortItem
from items.conn_item import ConnItem
from items.branch_node import BranchNode
from items.symbol_item import SymbolItem
from items.note_item import NoteItem
from items.textbox_item import TextBoxItem
from model import BlockData, PortData
from scene import DiagramScene

IDLE         = 0
DRAWING_CONN = 1
XSHEET_LINK  = 2
DRAG_SLOT    = 3   # arrastrando un conector a otro vacío
DRAG_ENDPT   = 4   # reubicando extremo de conexión existente
SEL_RECT     = 5   # selección por rectángulo pendiente de acción
SEL_MOVE     = 6   # mover grupo: esperando click+drag del usuario


@dataclass
class PendingXSheetLink:
    """Datos Python puros del origen del enlace — sin referencias Qt."""
    sheet_idx:  int
    slot_index: int   # índice en slots_right
    kks:        str


class DiagramEditor(QGraphicsView):

    xsheet_link_started   = pyqtSignal(str)
    xsheet_link_completed = pyqtSignal()
    xsheet_link_cancelled = pyqtSignal()
    scene_modified        = pyqtSignal()   # emitir tras cualquier cambio persistible

    def __init__(self, scene: DiagramScene, parent=None):
        super().__init__(scene, parent)
        self._scene: DiagramScene = scene
        self._state = IDLE

        # Conexión en curso (intra-hoja)
        self._conn_src      = None
        self._conn_src_slot = False
        self._temp_line     = None
        self._temp_end      = None
        # Drag conector
        self._drag_slot_src  = None   # SlotItem origen del drag
        self._drag_slot_sym  = None   # SymbolItem asociado al slot (sigue en vivo)
        # Drag extremo de conexion
        self._drag_ep_conn   = None   # ConnItem que se reubica
        self._drag_ep_end    = 'dst'  # 'src' | 'dst'
        self._drag_ep_orig   = None   # item original del extremo

        # Enlace inter-hoja — SOLO datos Python, nunca referencias Qt
        self.pending_link: PendingXSheetLink | None = None

        self._last_release_ms: int = 0    # timestamp del último mouseRelease
        self._sel_drag_start = None       # QPointF inicio arrastre selección
        self._sel_drag_positions = {}     # {item: QPointF} posiciones originales
        self._pending_drag = None         # ('slot'|'endpoint', item, extra, sp)
        self._sel_rect_band = None        # QRubberBand permanente durante SEL_RECT
        self._rb_scene_rect  = None        # QRectF del último rubber band (coords escena)
        self._sel_move_items     = []      # ítems pendientes de mover tras _execute_sel_move
        self._pending_sel_items  = []      # sel guardada antes de mostrar menú
        self._affected_conns     = []      # (ConnItem, orig_waypoints) para recalcular al soltar
        self.rubberBandChanged.connect(self._on_rubber_band_changed)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._fit_page()

    def _fit_page(self):
        from PyQt6.QtCore import QRectF
        self.fitInView(QRectF(0, 0, PAGE_W, PAGE_H),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def fit_page(self):
        self._fit_page()

    # ── Zoom ─────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        f = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    # ── Drag & Drop desde biblioteca ──────────────────────────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasText(): e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText(): return
        try:
            payload = json.loads(event.mimeData().text())
        except Exception:
            return
        sp   = self.mapToScene(event.position().toPoint())
        kind = payload.get('kind', 'block')

        if kind == 'note':
            if self._in_canvas(sp):
                self._scene.add_note('Nota…', sp.x(), sp.y())
            event.acceptProposedAction()
            return

        if kind == 'textbox':
            if self._in_canvas(sp):
                self._scene.add_textbox('Texto', sp.x(), sp.y())
            event.acceptProposedAction()
            return

        if kind == 'symbol':
            if self._in_canvas(sp):
                from model import SymbolData
                # x irrelevante (se fija por tipo en SymbolItem.__init__)
                sd = SymbolData(
                    sym_type  = payload['sym_type'],
                    port_side = payload['port_side'],
                    x=sp.x(), y=sp.y(),   # y → snap al cajón más cercano
                )
                self._scene.add_symbol(sd)
            event.acceptProposedAction()
            return

        # kind == 'block'
        if not self._in_canvas(sp): return
        from model import LIBRARY_BY_ID, PortData as _PD
        tid = payload['type_id']
        bt  = LIBRARY_BY_ID.get(tid)
        # Construir datos del bloque directamente desde el tipo de biblioteca
        if bt:
            in_types  = getattr(bt, 'in_types',  ())
            out_types = getattr(bt, 'out_types', ())
            in_names  = getattr(bt, 'in_names',  ())
            out_names = getattr(bt, 'out_names', ())
            inputs  = [_PD(name=in_names[i] if i < len(in_names) else f'IN{i+1}',
                           number=i+1, side='in',
                           signal_type=in_types[i] if i < len(in_types) else 'analog')
                       for i in range(bt.default_ins)]
            outputs = [_PD(name=out_names[i] if i < len(out_names) else f'OUT{i+1}',
                           number=i+1, side='out',
                           signal_type=out_types[i] if i < len(out_types) else 'analog')
                       for i in range(bt.default_outs)]
            from const import mm as _mm
            w = _mm(getattr(bt, 'width_mm', 20))  # mm → px
        else:
            inputs, outputs, w = [], [], 0
        data = BlockData(
            type_id    = tid,
            inscription= getattr(bt, 'inscription', '') if bt else '',
            inputs=inputs, outputs=outputs,
            x=sp.x(), y=sp.y(), w=w,
        )
        # Auto-relleno KKS desde el grupo
        g = self._scene.group()
        if g and g.kks:
            data.kks = g.kks
        self._scene.add_block(data)
        event.acceptProposedAction()

    # ── Menú contextual ───────────────────────────────────────────────────

    def _items_inside_rect(self, rb_rect):
        """
        Devuelve los ítems de usuario (BlockItem, ConnItem, NoteItem,
        TextBoxItem, SymbolItem) cuyos bounds estén completamente dentro de rb_rect.
        Opera sobre top-level items para ignorar hijos (PortItem, WaypointHandle).
        """
        from items.conn_item import WaypointHandle
        from items.block_item import PortItem
        from items.symbol_item import SymbolItem, SymbolPortItem
        from items.note_item import NoteItem

        result = []
        # Top-level items de la escena (sin padre)
        for it in self._scene.items():
            if it.parentItem() is not None:
                continue   # ignorar hijos
            if isinstance(it, (WaypointHandle, PortItem, SymbolPortItem)):
                continue
            # BlockItem / NoteItem / TextBoxItem / SymbolItem: usar bounding rect
            if isinstance(it, ConnItem):
                pts = it._full_pts()
                if pts and all(rb_rect.contains(p) for p in pts):
                    result.append(it)
            else:
                br = it.mapToScene(it.boundingRect()).boundingRect()
                if rb_rect.contains(br):
                    result.append(it)
        return result

    def _on_rubber_band_changed(self, rb_rect, from_scene, to_scene):
        """Captura el rect del rubber band en coordenadas de escena."""
        if rb_rect.isNull():
            return
        self._rb_scene_rect = self.mapToScene(rb_rect).boundingRect()

    def contextMenuEvent(self, event):
        # Clic derecho durante SEL_RECT → cancelar selección (sin menú)
        if self._state == SEL_RECT:
            self._cancel_sel_rect()
            return
        sp   = self.mapToScene(event.pos())
        # Intentar detectar SymbolItem primero (su área puede solapar con slots)
        sym_direct = self._sym_at_pos(sp)
        it   = sym_direct if sym_direct else self._scene.item_at_pos(sp)
        menu = QMenu(self)

        if isinstance(it, SlotItem):
            menu.addAction('✏  Editar conector',  lambda: self._edit_slot(it))
            menu.addAction('🗑  Limpiar conector', lambda: self._clear_slot(it))
            menu.addSeparator()
            # Añadir / quitar símbolo de campo
            existing_sym = self._sym_for_slot(it)
            if existing_sym:
                menu.addAction('✂  Quitar símbolo de campo',
                               lambda s=existing_sym: self._remove_sym_from_slot(s))
            else:
                from items.symbol_item import SYM_NAMES
                sym_menu = menu.addMenu('➕  Añadir símbolo de campo')
                for sym_type, sym_label in SYM_NAMES.items():
                    sym_menu.addAction(sym_label,
                        lambda _=None, sl=it, st=sym_type: self._add_sym_to_slot(sl, st))
            menu.addSeparator()
            if self._state == IDLE and it.side == 'right':
                menu.addAction('🔗  Enlazar con cajón de entrada de otra hoja…',
                               lambda: self._start_xsheet_link(it))
            elif self._state == XSHEET_LINK:
                if it.side == 'left':
                    menu.addAction('✅  Completar enlace aquí',
                                   lambda: self._finish_xsheet_link(it))
                menu.addAction('❌  Cancelar enlace', self._cancel_xsheet_link)

        elif isinstance(it, BlockItem):
            menu.addAction('✏  Editar bloque',   lambda: self._edit_block(it))
            menu.addAction('📋 Copiar bloque',    lambda: self._copy_block(it))
            menu.addAction('📋 Copiar a hoja…',   lambda: self._copy_to_sheet(it))
            menu.addSeparator()
            menu.addAction('🗑  Eliminar bloque', lambda: self._scene.remove_block(it))

        elif isinstance(it, ConnItem):
            menu.addAction('🗑  Eliminar conexión',     lambda: self._scene.remove_conn(it))
            # Si es una de varias ramas del mismo puerto, indicarlo
            try:
                siblings = [c for c in self._scene.conn_items
                            if c.src_item is it.src_item and c is not it]
                if siblings:
                    menu.addAction(
                        f'✂  Eliminar esta rama  ({len(siblings)+1} ramas en total)',
                        lambda: self._scene.remove_conn(it))
            except Exception:
                pass
            menu.addAction('↩  Resetear a ruta simple', lambda: self._reset_routing(it))

        elif isinstance(it, SymbolItem):
            menu.addAction('✏  Editar KKS',       lambda: self._edit_symbol(it))
            menu.addAction('🗑  Eliminar símbolo', lambda: self._scene.remove_symbol(it))

        elif isinstance(it, NoteItem):
            menu.addAction('🗑  Eliminar nota',    lambda: self._scene.remove_note(it))

        elif isinstance(it, TextBoxItem):
            from PyQt6.QtWidgets import QInputDialog
            # Cambiar tamaño de fuente
            a_sz  = menu.addAction('📝  Cambiar tamaño de fuente…')
            # Tipo de señal
            a_dig = menu.addAction('⚡  Puerto: Digital')
            a_ana = menu.addAction('〰  Puerto: Analógico')
            a_dig.setCheckable(True)
            a_ana.setCheckable(True)
            a_dig.setChecked(getattr(it, '_sig_type', 'analog') == 'digital')
            a_ana.setChecked(getattr(it, '_sig_type', 'analog') == 'analog')
            menu.addSeparator()
            a_del = menu.addAction('🗑  Eliminar')
            act = menu.exec(event.globalPos())
            if act == a_sz:
                cur_pt = max(4, round(it.font_size_px * 0.75))
                new_pt, ok = QInputDialog.getInt(
                    None, 'Tamaño', 'Puntos (4–24):', cur_pt, 4, 24, 1)
                if ok:
                    from const import mm as _mm
                    _F_MIN, _F_MAX = int(_mm(2.0)), int(_mm(9.0))
                    it.font_size_px = max(_F_MIN, min(_F_MAX,
                                          int(round(new_pt / 0.75))))
                    it._apply_font(); it._fit(); it.update()
            elif act == a_dig:
                it._set_signal_type('digital')
            elif act == a_ana:
                it._set_signal_type('analog')
            elif act == a_del:
                self._scene.remove_textbox(it)
            return

        else:
            if self._state == XSHEET_LINK:
                menu.addAction('❌  Cancelar enlace inter-hoja',
                               self._cancel_xsheet_link)
            else:
                # Mostrar Pegar solo si el portapapeles tiene bloques
                try:
                    _cb_data = json.loads(QApplication.clipboard().text())
                    _has_blocks = 'blocks' in _cb_data
                except Exception:
                    _has_blocks = False
                if _has_blocks:
                    paste_sp = self.mapToScene(event.pos())
                    menu.addAction('📋 Pegar',
                                   lambda _=None, p=paste_sp: self._paste_blocks(insert_pos=p))

        if not menu.isEmpty():
            menu.exec(event.globalPos())

    # ── Doble clic ────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        sp = self.mapToScene(event.position().toPoint())
        it = self._scene.item_at_pos(sp)
        if isinstance(it, SlotItem):
            self._edit_slot(it)
        elif isinstance(it, BlockItem):
            self._edit_block(it)
        elif isinstance(it, SymbolItem):
            self._edit_symbol(it)
        else:
            super().mouseDoubleClickEvent(event)

    # ── Clic izquierdo ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Guardia anti-click-fantasma: ignorar si llega < 80ms tras un release
            # (artefacto de Qt/OS al soltar arrastres de bloque)
            import time
            now_ms = int(time.monotonic() * 1000)
            if now_ms - self._last_release_ms < 80:
                event.accept()
                return
            sp   = self.mapToScene(event.position().toPoint())
            port = self._scene.port_at_pos(sp)
            slot = self._scene.slot_at_pos(sp) if not port else None

            if self._state == XSHEET_LINK:
                if slot and slot.side == 'left':
                    self._finish_xsheet_link(slot)
                    return
                elif slot and slot.side == 'right':
                    # Cambiar origen del enlace
                    self._start_xsheet_link(slot)
                    return
                elif slot is None and port is None:
                    self._cancel_xsheet_link()
                    return

            elif self._state == SEL_MOVE:
                # Click izquierdo en SEL_MOVE: iniciar arrastre
                self._sel_drag_start = sp
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

            elif self._state == IDLE:
                mods  = event.modifiers()
                shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

                # Clic sin modificador sobre BranchNode → drag a lo largo del padre
                if not shift:
                    bn_hit = self._scene.branch_at_pos(sp)
                    if bn_hit and not bn_hit._dragging:
                        # Dejar que el evento llegue al BranchNode
                        super().mousePressEvent(event)
                        return

                # Shift+clic sobre una conexión → nodo de bifurcación
                if shift:
                    conn = self._conn_at_pos(sp)
                    if conn:
                        bn = self._scene.add_branch_node(conn, sp)
                        self._start_conn(bn, False, sp)
                        return

                # SymbolItem tiene prioridad sobre slot (están adyacentes y el slot
                # tiene margen de hit que solaparía con el símbolo)
                sym_hit = self._sym_at_pos(sp)
                if sym_hit and not port:
                    # Dejar que Qt gestione la selección del SymbolItem
                    super().mousePressEvent(event)
                    return

                if port:
                    if port.connections:
                        # Puerto ocupado: guardar intent para drag o selección
                        conn, end = self._conn_endpoint_at(sp, port)
                        if conn:
                            self._pending_drag = ('endpoint', conn, end, sp)
                            event.accept(); return
                        return
                    self._start_conn(port, False, sp); return
                elif slot and not sym_hit:
                    if slot.connections:
                        # Slot ocupado: guardar intent para drag
                        self._pending_drag = ('slot', slot, None, sp)
                        event.accept(); return
                    self._start_conn(slot, True, sp); return
                else:
                    it = self._scene.item_at_pos(sp)
                    if it is None:
                        # Canvas vacío: si hay selección activa y NO se pulsa Ctrl,
                        # NO la limpiamos — el usuario puede estar iniciando un move
                        # o simplemente ha soltado el botón fuera. Solo limpiamos
                        # si no había nada seleccionado.
                        has_sel = bool(self._scene.selectedItems())
                        if not has_sel:
                            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                        else:
                            # Iniciar arrastre del grupo seleccionado
                            self._sel_drag_start = sp
                            self._sel_drag_positions = {
                                it: it.pos()
                                for it in self._scene.selectedItems()
                                if hasattr(it, 'setPos') and not isinstance(it, ConnItem)
                            }
                            self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    else:
                        # Clic sobre un ítem → moverlo individualmente
                        self.setDragMode(QGraphicsView.DragMode.NoDrag)
                        self._sel_drag_start = None
                        if isinstance(it, ConnItem):
                            if it.isSelected():
                                # Ya seleccionada: dejar que ConnItem gestione
                                # el drag de segmento vía super()
                                pass   # no return → super().mousePressEvent abajo
                            else:
                                # Primer click: seleccionar
                                self._scene.clearSelection()
                                it.setSelected(True)
                                it._set_handles_visible(True)
                                return

            elif self._state == DRAWING_CONN:
                # Comprobar también BranchNode en destino
                branch = self._scene.branch_at_pos(sp) if self._scene else None
                if branch and branch is not self._conn_src:
                    self._finish_conn(branch, False); return
                if port or slot:
                    self._finish_conn(port or slot,
                                      isinstance(port or slot, SlotItem))
                    return
                else:
                    self._cancel_conn()

        elif event.button() == Qt.MouseButton.RightButton:
            if self._state == DRAWING_CONN:
                self._cancel_conn(); return
            if self._state in (SEL_RECT, SEL_MOVE):
                self._cancel_sel_move(); return
            # Clic derecho en canvas vacío → limpiar selección
            if self._state == IDLE:
                sp2 = self.mapToScene(event.position().toPoint())
                if self._scene.item_at_pos(sp2) is None:
                    self._scene.clearSelection()
                    return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            import time
            self._last_release_ms = int(time.monotonic() * 1000)
            self._pending_drag = None
            # Finalizar arrastre en SEL_MOVE
            if self._state == SEL_MOVE and self._sel_drag_start is not None:
                self._sel_drag_start = None
                self._sel_move_items = []
                self._retrace_connections_for_selection()
                self._sel_drag_positions = {}
                self._state = IDLE
                self._scene.clearSelection()
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                self.scene_modified.emit()
                return
            # Finalizar arrastre de selección múltiple normal
            if self._sel_drag_start is not None:
                self._sel_drag_start = None
                self._sel_drag_positions = {}
                self._retrace_connections_for_selection()
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self.scene_modified.emit()
                return
            sp = self.mapToScene(event.position().toPoint())
            if self._state == DRAG_SLOT:
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self._finish_drag_slot(sp); return
            elif self._state == DRAG_ENDPT:
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self._finish_drag_endpoint(sp); return
            # Tras rubber band: filtrar ítems completamente dentro del rect
            rb_rect = self._rb_scene_rect
            self._rb_scene_rect = None
            # Solo activar si el rect tiene área mínima (no es un simple click)
            if (rb_rect and rb_rect.width() > mm(3) and rb_rect.height() > mm(3)
                    and self._state == IDLE):
                self._scene.clearSelection()
                truly_inside = self._items_inside_rect(rb_rect)
                if len(truly_inside) > 1 or (
                        len(truly_inside) == 1
                        and not isinstance(truly_inside[0], ConnItem)):
                    for it in truly_inside:
                        it.setSelected(True)
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    self._show_sel_rect_menu(truly_inside,
                                             event.globalPosition().toPoint())
                    return
                self._scene.clearSelection()
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        elif event.button() == Qt.MouseButton.RightButton:
            if self._state in (SEL_RECT, SEL_MOVE):
                self._cancel_sel_move()
                return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._state == IDLE:
            # Qt ha gestionado el drag nativo de un bloque → emitir modificación
            # IMPORTANTE: emitir DESPUÉS de super() para que BlockItem.mouseReleaseEvent
            # ya haya ejecutado update_path() y guardado los waypoints finales.
            self.scene_modified.emit()

    def mouseMoveEvent(self, event):
        sp = self.mapToScene(event.position().toPoint())

        # Resolver pending drag (port/slot ocupado) cuando el ratón se mueve
        if (self._pending_drag is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            kind, item, extra, origin = self._pending_drag
            dx = sp.x() - origin.x(); dy = sp.y() - origin.y()
            if dx*dx + dy*dy > 25:   # umbral ~5px
                self._pending_drag = None
                if kind == 'endpoint':
                    self._start_drag_endpoint(item, extra, origin)
                elif kind == 'slot':
                    self._start_drag_slot(item, origin)
            super().mouseMoveEvent(event)
            return

        # Arrastre de selección múltiple (normal o SEL_MOVE)
        if (self._sel_drag_start is not None
                and self._sel_drag_positions
                and event.buttons() & Qt.MouseButton.LeftButton):
            dx = sp.x() - self._sel_drag_start.x()
            dy = sp.y() - self._sel_drag_start.y()
            for it, orig in self._sel_drag_positions.items():
                try:
                    it.setPos(orig.x() + dx, orig.y() + dy)
                except RuntimeError:
                    pass
            super().mouseMoveEvent(event)
            return
        if self._state == DRAWING_CONN and self._temp_end is not None:
            try:
                # Throttle: solo recalcular si el ratón se movió más de 3 unidades
                last = getattr(self, '_last_preview_pos', None)
                if last is not None:
                    dx = sp.x() - last.x(); dy = sp.y() - last.y()
                    if dx*dx + dy*dy < 9:   # 3u² = 0.3mm — ignorar micromovimientos
                        super().mouseMoveEvent(event)
                        return
                self._last_preview_pos = sp
                self._temp_end.setPos(sp)
                if self._temp_line is not None:
                    # invalidate_cache=False: reutiliza A* anterior si src/dst no cambió
                    self._temp_line.update_path(invalidate_cache=False)
            except RuntimeError:
                self._state = IDLE
                self._temp_line = None
                self._temp_end  = None
                self._conn_src  = None
        elif self._state == DRAG_SLOT:
            self._update_drag_slot(sp)
        elif self._state == DRAG_ENDPT:
            self._update_drag_endpoint(sp)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        # Si el foco está en un campo de texto, dejar que el widget lo gestione
        from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit, QAbstractItemView
        from PyQt6.QtWidgets import QGraphicsTextItem
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QAbstractItemView)):
            super().keyPressEvent(event)
            return
        # QGraphicsTextItem en modo edición: el foco está en la escena, no en un QWidget
        if self._scene:
            fi = self._scene.focusItem()
            if isinstance(fi, QGraphicsTextItem) and (
                    fi.textInteractionFlags() &
                    Qt.TextInteractionFlag.TextEditorInteraction):
                super().keyPressEvent(event)
                return

        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._state == DRAWING_CONN:   self._cancel_conn()
            elif self._state == XSHEET_LINK:  self._cancel_xsheet_link()
            else: self._scene.clearSelection()
        elif event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self._paste_blocks()   # sin posición → centro de vista
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selection()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                     Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Mover selección con cursor (paso fino con Shift, normal sin él)
            sel = self._scene.selectedItems()
            if sel:
                step = 2 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 10
                dx = (-step if key == Qt.Key.Key_Left else
                       step if key == Qt.Key.Key_Right else 0)
                dy = (-step if key == Qt.Key.Key_Up else
                       step if key == Qt.Key.Key_Down else 0)
                for it in sel:
                    try:
                        it.setPos(it.pos().x() + dx, it.pos().y() + dy)
                    except RuntimeError:
                        pass
                self._retrace_connections_for_selection()
            else:
                super().keyPressEvent(event)

    # ── Conexión intra-hoja ───────────────────────────────────────────────

    def _start_conn(self, src, src_is_slot, sp):
        self._conn_src      = src
        self._conn_src_slot = src_is_slot
        self._state         = DRAWING_CONN
        self._last_preview_pos = None          # resetear throttle
        if self._scene:
            self._scene._preview_mode = True   # suprimir rebuild_junctions

        from PyQt6.QtWidgets import QGraphicsEllipseItem
        self._temp_end = self._scene.addEllipse(-1, -1, 2, 2)
        self._temp_end.setPos(sp)
        self._temp_end.connections = []
        self._temp_end.side = 'right'           # para _port_dir cuando dst_is_slot=True
        self._temp_end.port_scene_pos = lambda: self._temp_end.scenePos()

        self._temp_line = ConnItem(src, src_is_slot, self._temp_end, True, self._scene)
        p = self._temp_line.pen()
        p.setColor(__import__('PyQt6.QtGui', fromlist=['QColor']).QColor('#889BB0'))
        p.setStyle(Qt.PenStyle.DashLine)
        self._temp_line.setPen(p)

    def _finish_conn(self, dst, dst_is_slot):
        src, src_is_slot = self._conn_src, self._conn_src_slot
        self._cancel_temp()
        self._state = IDLE
        if src is None or src is dst: return
        ok = False
        src_is_branch    = isinstance(src, BranchNode)
        dst_is_branch    = isinstance(dst, BranchNode)
        src_is_port      = isinstance(src, PortItem) and not src_is_branch
        dst_is_port      = isinstance(dst, PortItem) and not dst_is_branch
        src_is_slot_item = isinstance(src, SlotItem)
        dst_is_slot_item = isinstance(dst, SlotItem)

        # BranchNode como origen: admite cualquier destino válido
        if src_is_branch:
            ok = ((dst_is_port      and dst.side == 'in') or
                  (dst_is_slot_item and dst.side == 'right') or
                  dst_is_branch)

        # Puerto 'out' → puerto 'in' o cajón SALIDAS
        elif src_is_port and src.side == 'out':
            ok = ((dst_is_port      and dst.side == 'in') or
                  (dst_is_slot_item and dst.side == 'right') or
                  dst_is_branch)

        elif src_is_port and src.side == 'in':
            ok = False

        # Cajón ENTRADAS → puerto 'in' o cajón SALIDAS
        elif src_is_slot_item and src.side == 'left':
            ok = ((dst_is_port      and dst.side == 'in') or
                  (dst_is_slot_item and dst.side == 'right') or
                  dst_is_branch)

        # Cajón SALIDAS → puerto 'out' de símbolo
        elif src_is_slot_item and src.side == 'right':
            ok = dst_is_port and dst.side == 'out'

        if ok:
            # Verificar que el destino no esté ya ocupado (excepto BranchNode)
            if not dst_is_branch and dst_is_port and dst.connections:
                return   # destino ocupado
            if dst_is_slot_item and dst.connections:
                return
            self._scene.add_conn(src, src_is_slot, dst, dst_is_slot)
            # Auto-relleno: si se conecta algo a conector de SALIDA, rellenar vacíos
            if dst_is_slot_item and dst.side == 'right':
                self._autofill_slot_from_group(dst)
            elif src_is_slot_item and src.side == 'right':
                self._autofill_slot_from_group(src)

    def _cancel_conn(self):
        src = self._conn_src
        self._cancel_temp()
        self._state = IDLE
        # Si el origen era un BranchNode recién creado y quedó huérfano, eliminarlo
        if isinstance(src, BranchNode) and src.is_orphan():
            try: self._scene.remove_branch_node(src)
            except Exception: pass

    def _cancel_temp(self):
        if self._scene:
            self._scene._preview_mode = False   # reanudar rebuild_junctions
            self._scene.rebuild_junctions()     # actualizar ahora
        self._last_preview_pos = None
        """Limpia la línea temporal de conexión.
        Seguro aunque los C++ objects ya hayan sido destruidos por clear_all().
        """
        if self._temp_line is not None:
            try:
                self._temp_line.remove()
            except RuntimeError:
                pass   # C++ object already deleted — ignorar
            self._temp_line = None
        if self._temp_end is not None:
            try:
                if self._temp_end.scene():
                    self._scene.removeItem(self._temp_end)
            except RuntimeError:
                pass
            self._temp_end = None
        self._conn_src = None

    # ── Drag conector (Ctrl+clic en conector con conexion) ───────────────

    def _start_drag_slot(self, slot: SlotItem, sp):
        """Inicia el arrastre de un conector a otra posicion vacía."""
        self._drag_slot_src = slot
        self._state = DRAG_SLOT
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        # Guardar símbolo asociado al slot origen para arrastrarlo en vivo
        self._drag_slot_sym = self._sym_for_slot(slot)

    def _sym_for_slot(self, slot: SlotItem):
        """Devuelve el SymbolItem cuyo índice de fila coincide con el slot, o None."""
        if not self._scene or not self._scene.sheet:
            return None
        from const import WORK_Y, slot_h as _sh
        sh       = _sh(self._scene.sheet.num_slots)
        sym_side = 'out' if slot.side == 'right' else 'in'
        for si in self._scene.symbol_items:
            try:
                idx = round((si.pos().y() - WORK_Y) / sh)
                if idx == slot.index and si.port_side == sym_side:
                    return si
            except Exception:
                pass
        return None

    def _update_drag_slot(self, sp):
        """Resalta el conector destino más cercano y arrastra el símbolo en vivo."""
        dst = self._scene.slot_at_pos(sp)
        valid = (dst and dst is not self._drag_slot_src
                 and dst.data.is_empty()
                 and dst.side == self._drag_slot_src.side)
        self.setCursor(Qt.CursorShape.PointingHandCursor if valid
                       else Qt.CursorShape.ForbiddenCursor)

        # Mover símbolo en vivo a la fila del slot destino (o al cursor si no hay destino)
        sym = getattr(self, '_drag_slot_sym', None)
        if sym is None:
            return
        try:
            from const import WORK_Y, slot_h as _sh
            sh = _sh(self._scene.sheet.num_slots)
            if valid:
                target_y = WORK_Y + dst.index * sh + sh / 2
            else:
                target_y = sp.y()
            sym.snap_to_slot(target_y, self._scene.sheet.num_slots)
            for c in sym.port_item().connections:
                try: c.update_path(invalidate_cache=False)
                except Exception: pass
        except Exception:
            pass

    def _finish_drag_slot(self, sp):
        """Mueve un conector (datos + conexiones) a otro vacio de la misma columna."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._state = IDLE
        src = self._drag_slot_src
        sym = getattr(self, '_drag_slot_sym', None)
        self._drag_slot_src = None
        self._drag_slot_sym = None
        if src is None: return

        dst = self._scene.slot_at_pos(sp)
        if dst is None or dst is src or not dst.data.is_empty() or dst.side != src.side:
            # Drag cancelado: restaurar símbolo a su fila original
            if sym is not None:
                try:
                    from const import WORK_Y, slot_h as _sh
                    sh = _sh(self._scene.sheet.num_slots)
                    sym.snap_to_slot(WORK_Y + src.index * sh + sh / 2,
                                     self._scene.sheet.num_slots)
                    for c in sym.port_item().connections:
                        try: c.update_path()
                        except Exception: pass
                except Exception:
                    pass
            return

        sd, dd = src.data, dst.data

        dd.description   = sd.description
        dd.signal_desc   = sd.signal_desc
        dd.kks           = sd.kks
        dd.kks2          = sd.kks2
        dd.sub_text      = sd.sub_text
        dd.linked_sheets = list(sd.linked_sheets)
        dd.linked_slots  = list(sd.linked_slots)

        sd.description   = ''
        sd.signal_desc   = ''
        sd.kks           = ''
        sd.kks2          = ''
        sd.sub_text      = ''
        sd.linked_sheets = []
        sd.linked_slots  = []

        # Actualizar referencias remotas: indice src.index -> dst.index
        doc      = self._scene.document
        my_sheet = self._scene.sheet_idx
        for r_si, r_sl in zip(dd.linked_sheets, dd.linked_slots):
            if not (0 <= r_si < doc.sheet_count()): continue
            sheet = doc.sheet_at(r_si)
            sl_list = (sheet.slots_left if src.side == 'right' else sheet.slots_right)
            if not (0 <= r_sl < len(sl_list)): continue
            rd = sl_list[r_sl]
            for i, (rs, rsl) in enumerate(zip(rd.linked_sheets, rd.linked_slots)):
                if rs == my_sheet and rsl == src.index:
                    rd.linked_slots[i] = dst.index
            rd.rebuild_sub_text(doc, 'right' if src.side == 'left' else 'left',
                                 r_si, r_sl)

        # Redirigir conexiones src -> dst
        for conn in list(src.connections):
            if conn.src_item is src:
                conn.src_item = dst
            elif conn.dst_item is src:
                conn.dst_item = dst
            if conn not in dst.connections:
                dst.connections.append(conn)
        src.connections.clear()

        src.refresh(); dst.refresh()
        # Resetear rutas automáticas (Hanan recalculará desde nueva posición)
        for conn in dst.connections:
            try:
                if not conn._user_waypoints:
                    conn.waypoints.clear()
                conn.update_path()
            except Exception: pass
        # Limpiar BranchNodes huérfanos que pudieran haber quedado desconectados
        try: self._scene.prune_orphan_branches()
        except Exception: pass

        # Mover el símbolo de campo del índice origen al índice destino
        from const import WORK_Y, slot_h as _sh
        sh = _sh(self._scene.sheet.num_slots if self._scene.sheet else 23)
        sym_side = 'out' if src.side == 'right' else 'in'
        for si in list(self._scene.symbol_items):
            try:
                idx = round((si.pos().y() - WORK_Y) / sh)
                if idx == src.index and si.port_side == sym_side:
                    si.snap_to_slot(WORK_Y + dst.index * sh + sh / 2,
                                    self._scene.sheet.num_slots)
                    for c in si.port_item().connections:
                        try: c.update_path()
                        except Exception: pass
                    p = si.pos()
                    for sd in self._scene.sheet.symbols:
                        if sd.sym_id == si.sym_id:
                            sd.x = p.x(); sd.y = p.y()
                    break
            except Exception:
                pass

    # ── Drag extremo de conexion (Ctrl+clic sobre puerto/extremo) ────────

    def _sym_at_pos(self, sp):
        """Devuelve el SymbolItem bajo sp, o None."""
        from items.symbol_item import SymbolItem as _SI
        from PyQt6.QtCore import QRectF
        hit = mm(3)
        for it in self._scene.items(QRectF(sp.x()-hit, sp.y()-hit, 2*hit, 2*hit)):
            if isinstance(it, _SI):
                return it
            p = it.parentItem()
            while p:
                if isinstance(p, _SI):
                    return p
                p = p.parentItem()
        return None

    def _conn_at_pos(self, sp) -> 'ConnItem | None':
        """Devuelve el ConnItem bajo sp (tolerancia 3 mm).
        Usa scene.items(rect) para la detección, que es correcto con Qt.
        """
        from const import mm
        from PyQt6.QtCore import QRectF
        hit = mm(3.0)
        rect = QRectF(sp.x() - hit, sp.y() - hit, 2 * hit, 2 * hit)
        for item in self._scene.items(rect):
            if isinstance(item, ConnItem):
                return item
        return None

    def _conn_endpoint_at(self, sp, port):
        """Devuelve (ConnItem, src|dst) buscando por identidad del port."""
        for conn in self._scene.conn_items:
            if conn.src_item is port:
                return conn, 'src'
            if conn.dst_item is port:
                return conn, 'dst'
        hit = mm(8)
        for conn in self._scene.conn_items:
            try:
                s = (conn.src_item.port_scene_pos() if conn.src_is_slot
                     else conn.src_item.scenePos())
                d = (conn.dst_item.port_scene_pos() if conn.dst_is_slot
                     else conn.dst_item.scenePos())
            except Exception:
                continue
            if abs(s.x()-sp.x()) < hit and abs(s.y()-sp.y()) < hit:
                return conn, 'src'
            if abs(d.x()-sp.x()) < hit and abs(d.y()-sp.y()) < hit:
                return conn, 'dst'
        return None, 'dst'


    def _start_drag_endpoint(self, conn: ConnItem, end: str, sp):
        """Inicia el drag del extremo de la conexion."""
        self._drag_ep_conn  = conn
        self._drag_ep_end   = end
        self._drag_ep_orig  = conn.src_item if end == 'src' else conn.dst_item
        self._state = DRAG_ENDPT
        # Crear marcador temporal en el extremo
        self._temp_end = self._scene.addEllipse(-2, -2, 4, 4)
        self._temp_end.setPos(sp)
        self._temp_end.connections = []
        self._temp_end.side = 'right'
        self._temp_end.port_scene_pos = lambda: self._temp_end.scenePos()
        # Redirigir temporalmente el extremo al marcador
        if end == 'src':
            conn.src_item = self._temp_end
        else:
            conn.dst_item = self._temp_end
        conn.update_path()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _update_drag_endpoint(self, sp):
        if self._temp_end is None: return
        try:
            self._temp_end.setPos(sp)
            if self._drag_ep_conn:
                self._drag_ep_conn.update_path()
        except RuntimeError:
            self._state = IDLE

    def _finish_drag_endpoint(self, sp):
        """Conecta el extremo suelto al nuevo puerto/conector."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._state = IDLE
        conn   = self._drag_ep_conn
        end    = self._drag_ep_end
        orig   = self._drag_ep_orig
        self._drag_ep_conn = None
        self._drag_ep_orig = None

        if self._temp_end is not None:
            try:
                if self._temp_end.scene():
                    self._scene.removeItem(self._temp_end)
            except RuntimeError: pass
            self._temp_end = None

        if conn is None: return

        # Buscar nuevo destino
        new_port = self._scene.port_at_pos(sp)
        new_slot = self._scene.slot_at_pos(sp) if not new_port else None
        new_item = new_port or new_slot

        # Restaurar extremo original si no hay destino válido
        if new_item is None or new_item is orig:
            if end == 'src': conn.src_item = orig
            else:            conn.dst_item = orig
            conn.update_path()
            return

        # Validar compatibilidad
        is_slot_new = isinstance(new_item, SlotItem)
        ok = self._validate_ep_move(conn, end, new_item, is_slot_new)
        if not ok:
            if end == 'src': conn.src_item = orig
            else:            conn.dst_item = orig
            conn.update_path()
            return

        # Desconectar del extremo antiguo
        try: orig.connections.remove(conn)
        except (ValueError, AttributeError): pass

        # Conectar al nuevo extremo
        if end == 'src':
            conn.src_item    = new_item
            conn.src_is_slot = is_slot_new
        else:
            conn.dst_item    = new_item
            conn.dst_is_slot = is_slot_new

        if not hasattr(new_item, 'connections'):
            new_item.connections = []
        if conn not in new_item.connections:
            new_item.connections.append(conn)

        conn.waypoints.clear()
        conn.update_path()
        self._scene.sync_to_model()

    def _validate_ep_move(self, conn, end, new_item, is_slot_new):
        """Valida que el nuevo extremo sea compatible con el opuesto."""
        from items.symbol_item import SymbolPortItem
        opp = conn.dst_item if end == 'src' else conn.src_item
        opp_is_slot = conn.dst_is_slot if end == 'src' else conn.src_is_slot

        def side_of(item, is_slot):
            if is_slot: return item.side
            return getattr(item, 'side', 'out')

        opp_side = side_of(opp, opp_is_slot)
        new_side = side_of(new_item, is_slot_new)

        # El extremo opuesto determina cuál lado acepta el nuevo
        if end == 'dst':
            # Movemos el destino: el src manda
            if opp_side in ('out', 'left'):
                return new_side in ('in', 'right')
            return new_side in ('out', 'left')
        else:
            # Movemos el src: el dst manda
            if opp_side in ('in', 'right'):
                return new_side in ('out', 'left')
            return new_side in ('in', 'right')

    # ── Enlace inter-hoja ─────────────────────────────────────────────────
    #
    # INVARIANTE DE SEGURIDAD:
    #   pending_link  contiene solo datos Python (ints y str).
    #   Nunca almacenamos un item Qt entre cambios de hoja.
    #   Para marcar/desmarcar visualmente el cajón origen, lo buscamos
    #   en self._scene.slot_items_right[] SIN guardarlo en un atributo.

    def _src_slot_item_if_visible(self):
        """Devuelve el SlotItem del cajón origen si está en la escena actual."""
        pl = self.pending_link
        if pl is None:
            return None
        if self._scene.sheet_idx != pl.sheet_idx:
            return None          # la hoja origen no está cargada → no tocar nada
        items = self._scene.slot_items_right
        if pl.slot_index < len(items):
            return items[pl.slot_index]
        return None


    def _autofill_slot_from_group(self, slot_item):
        """Rellena descripcion y KKS del conector de salida con los del grupo,
        solo si los campos estan vacios."""
        scene = self._scene
        if scene is None: return
        group = scene.group()
        if group is None: return
        sd = slot_item.data
        if not sd.description:
            from main import _wrap_description
            sd.description = _wrap_description(group.description)
        if not sd.kks:
            sd.kks = group.kks[:14]
        slot_item.refresh()

    def _start_xsheet_link(self, slot: SlotItem):
        """Inicia el enlace. Solo guarda datos Python."""
        if slot.side != 'right':
            return

        # Si había un enlace anterior, desmarcar su cajón si aún es visible
        self._unmark_src_slot()

        self.pending_link = PendingXSheetLink(
            sheet_idx  = self._scene.sheet_idx,
            slot_index = slot.index,
            kks        = slot.data.kks,
        )
        self._state = XSHEET_LINK

        # Marcar visualmente — acceso directo, sin guardar la referencia
        slot.set_pending(True)

        self.xsheet_link_started.emit(
            f'Cajón {slot.index+1:02d} (hoja {self._scene.sheet_idx+1})  '
            f'KKS: {slot.data.kks or "(vacío)"}  — '
            f'navega a otra hoja y haz clic en un cajón de ENTRADAS'
        )

    def _unmark_src_slot(self):
        """Quita el marcado visual del cajón origen si está en la escena actual.
        No lanza excepción si el item ya fue destruido por Qt."""
        si = self._src_slot_item_if_visible()
        if si is not None:
            try:
                si.set_pending(False)
            except RuntimeError:
                pass   # C++ object already deleted — ignorar

    def _finish_xsheet_link(self, dst_slot: SlotItem):
        """Completa el enlace. dst_slot pertenece a la hoja activa.
        Un conector SALIDA puede enlazarse a varios ENTRADA (multi-link)."""
        if self.pending_link is None: return
        if dst_slot.side != 'left':  return

        doc = self._scene.document
        pl  = self.pending_link

        src_sheet     = doc.sheet_at(pl.sheet_idx)
        src_data      = src_sheet.slots_right[pl.slot_index]
        dst_data      = dst_slot.data
        dst_sheet_idx = self._scene.sheet_idx

        src_num = doc.sheet_ref(pl.sheet_idx)
        dst_num = doc.sheet_ref(dst_sheet_idx)

        # SALIDA: añadir esta ENTRADA a su lista (multi-link)
        src_data.add_link(dst_sheet_idx, dst_slot.index)
        src_data.rebuild_sub_text(doc, 'right', pl.sheet_idx, pl.slot_index)

        # ENTRADA: copiar todos los campos del SALIDA y registrar su origen
        dst_data.description   = src_data.description
        dst_data.signal_desc   = src_data.signal_desc
        dst_data.kks           = src_data.kks
        dst_data.kks2          = src_data.kks2
        dst_data.linked_sheets = [pl.sheet_idx]
        dst_data.linked_slots  = [pl.slot_index]
        dst_data.sub_text      = f'H.{src_num}:{pl.slot_index+1:02d}'

        # Refrescar destino
        dst_slot.refresh()

        # Refrescar origen si está en la escena activa
        si = self._src_slot_item_if_visible()
        if si is not None:
            try:
                si.set_pending(False)
                si.refresh()
            except RuntimeError:
                pass

        self.pending_link = None
        self._state = IDLE
        # Auto-link KKS: propagar a otras entradas con la misma clave kks+kks2
        try:
            from io_utils.clone_group import apply_kks_autolink
            apply_kks_autolink(self._scene.document)
        except Exception:
            pass
        self.xsheet_link_completed.emit()

    def _cancel_xsheet_link(self):
        """Cancela el enlace de forma segura."""
        self._unmark_src_slot()   # busca el item en tiempo real, no usa referencia guardada
        self.pending_link = None
        self._state = IDLE
        self.xsheet_link_cancelled.emit()

    def on_sheet_about_to_change(self):
        """
        Llamado por MainWindow ANTES de que scene.load_sheet() destruya los items Qt.
        DEBE llamarse ANTES de clear_all(); después los items ya no son accesibles.
        """
        if self._state == DRAWING_CONN:
            # Limpiar referencias Python sin llamar .remove() —
            # clear_all() ya se encargará de destruir los items Qt.
            # Si llamamos remove() aquí podría funcionar (los items aún existen),
            # pero es más seguro soltar primero las refs y dejar que clear() haga su trabajo.
            try:
                self._cancel_temp()
            except Exception:
                pass
            self._state = IDLE

        elif self._state == XSHEET_LINK:
            self._unmark_src_slot()   # desmarcar mientras el item aún existe
            # NO limpiar pending_link: el enlace inter-hoja continúa activo en la nueva hoja

    # ── Edición de elementos ──────────────────────────────────────────────

    def _add_sym_to_slot(self, slot: SlotItem, sym_type: str):
        """Añade un símbolo de campo al slot y refresca el stub de las conexiones."""
        from model import SymbolData
        from const import WORK_Y, slot_h as _sh
        sh       = _sh(self._scene.sheet.num_slots)
        sym_side = 'out' if slot.side == 'right' else 'in'
        sy       = WORK_Y + slot.index * sh
        sd = SymbolData(sym_type=sym_type, port_side=sym_side, x=0, y=sy)
        self._scene.add_symbol(sd)
        self.scene_modified.emit()

    def _remove_sym_from_slot(self, si):
        """Elimina el símbolo de campo y refresca el stub de las conexiones."""
        self._scene.remove_symbol(si)
        self.scene_modified.emit()

    def _edit_slot(self, slot: SlotItem):
        from widgets.dialogs import SlotDialog
        dlg = SlotDialog(slot.data, slot.side,
                         self._scene.document, self._scene.sheet_idx, self)
        if dlg.exec():
            dlg.apply()
            if slot.side == 'right':
                # Propagar a entradas ya enlazadas
                if slot.data.is_linked():
                    self._propagate_all(slot)
                # Buscar nuevas entradas con KKS coincidente y enlazarlas
                self._try_kks_autolink_output(slot)
            else:
                # Buscar salida con KKS coincidente y enlazar
                self._try_kks_autolink_slot(slot)
            slot.refresh()

    def _propagate_all(self, slot: SlotItem):
        """Propaga desc/senal/kks/kks2 del conector SALIDA a TODOS los remotos enlazados."""
        doc = self._scene.document
        sd  = slot.data
        for r_si, r_sl in zip(sd.linked_sheets, sd.linked_slots):
            if not (0 <= r_si < doc.sheet_count()): continue
            sheet = doc.sheet_at(r_si)
            sl_list = sheet.slots_left if slot.side == 'right' else sheet.slots_right
            if not (0 <= r_sl < len(sl_list)): continue
            rd = sl_list[r_sl]
            rd.description = sd.description
            rd.signal_desc = sd.signal_desc
            rd.kks         = sd.kks
            rd.kks2        = sd.kks2
            # Refrescar visual si está en escena activa
            if r_si == self._scene.sheet_idx:
                items = (self._scene.slot_items_left if slot.side == 'right'
                         else self._scene.slot_items_right)
                if 0 <= r_sl < len(items):
                    try: items[r_sl].refresh()
                    except RuntimeError: pass

    def _propagate_kks(self, slot):
        """Alias de compatibilidad."""
        self._propagate_all(slot)

    def _try_kks_autolink_output(self, slot: 'SlotItem'):
        """Para un slot SALIDA: busca todas las ENTRADAS del documento con KKS
        coincidente (incluso en hojas no cargadas) y establece el enlace.
        Persiste slot_links en BD para que sobreviva navegaciones.
        """
        from io_utils.db_io import get_mem, load_sheet_content, sync_sheet
        doc  = self._scene.document
        sd   = slot.data
        if not sd.kks:
            return
        key     = (sd.kks.strip() + sd.kks2.strip()).upper()
        my_fi   = self._scene.sheet_idx
        my_si   = slot.index
        con     = get_mem()
        flat    = list(doc.flat_sheets())

        # Mapa sheet_id → flat_idx para resolver referencias
        sid_to_fi = {s.sheet_id: i for i, (s, _) in enumerate(flat)}

        # Buscar entradas en BD con KKS coincidente (sin cargar hojas)
        rows = con.execute(
            "SELECT s.slot_id, s.sheet_id, s.slot_index "
            "FROM slots s "
            "WHERE s.side='left' AND upper(s.kks || s.kks2)=?",
            (key,)).fetchall()

        changed_sheets = set()
        for row in rows:
            dst_sheet_id = row['sheet_id']
            dst_fi = sid_to_fi.get(dst_sheet_id)
            if dst_fi is None:
                continue
            dst_si = row['slot_index']
            # Cargar la hoja destino si no está en memoria
            dst_sheet = flat[dst_fi][0]
            if not getattr(dst_sheet, '_loaded', False):
                load_sheet_content(dst_sheet)
            if dst_si >= len(dst_sheet.slots_left):
                continue
            dst_sd = dst_sheet.slots_left[dst_si]
            # Saltar si ya están enlazados
            if any(s == my_fi and sl == my_si
                   for s, sl in zip(dst_sd.linked_sheets, dst_sd.linked_slots)):
                continue
            # Enlace bidireccional
            sd.add_link(dst_fi, dst_si)
            dst_sd.linked_sheets = [my_fi]
            dst_sd.linked_slots  = [my_si]
            # Propagar campos de salida → entrada
            dst_sd.description = sd.description
            dst_sd.signal_desc = sd.signal_desc
            dst_sd.kks         = sd.kks
            dst_sd.kks2        = sd.kks2
            # sub_text
            sd.rebuild_sub_text(doc, 'right', my_fi, my_si)
            dst_sd.sub_text = f'H.{doc.sheet_ref(my_fi)}:{my_si+1:02d}'
            # Persistir slot_link en BD
            import uuid as _uuid
            with con:
                con.execute(
                    'INSERT OR IGNORE INTO slot_links (link_id, src_slot_id, dst_slot_id) '
                    'VALUES (?,?,?)',
                    (str(_uuid.uuid4()), sd.slot_id, row['slot_id']))
            changed_sheets.add(dst_fi)
            # Refrescar visual si la entrada está en la hoja activa
            if dst_fi == self._scene.sheet_idx:
                items = self._scene.slot_items_left
                if 0 <= dst_si < len(items):
                    try: items[dst_si].refresh()
                    except RuntimeError: pass

        # Persistir hojas afectadas
        my_sheet = flat[my_fi][0]
        sync_sheet(my_sheet)
        for fi in changed_sheets:
            sync_sheet(flat[fi][0])

    def _try_kks_autolink_slot(self, slot: 'SlotItem'):
        """Para un slot ENTRADA: busca la SALIDA con KKS coincidente en el
        documento (incluidas hojas no cargadas) y establece el enlace.
        """
        from io_utils.db_io import get_mem, load_sheet_content, sync_sheet
        doc   = self._scene.document
        sd    = slot.data
        if not sd.kks:
            return
        key   = (sd.kks.strip() + sd.kks2.strip()).upper()
        my_fi = self._scene.sheet_idx
        my_si = slot.index
        con   = get_mem()
        flat  = list(doc.flat_sheets())
        sid_to_fi = {s.sheet_id: i for i, (s, _) in enumerate(flat)}

        # Buscar salida en BD con KKS coincidente
        rows = con.execute(
            "SELECT s.slot_id, s.sheet_id, s.slot_index "
            "FROM slots s "
            "WHERE s.side='right' AND upper(s.kks || s.kks2)=?",
            (key,)).fetchall()

        for row in rows:
            src_fi = sid_to_fi.get(row['sheet_id'])
            if src_fi is None:
                continue
            src_si = row['slot_index']
            src_sheet = flat[src_fi][0]
            if not getattr(src_sheet, '_loaded', False):
                load_sheet_content(src_sheet)
            if src_si >= len(src_sheet.slots_right):
                continue
            src_sd = src_sheet.slots_right[src_si]
            # Ya enlazado?
            if any(s == my_fi and sl == my_si
                   for s, sl in zip(src_sd.linked_sheets, src_sd.linked_slots)):
                return
            # Copiar campos salida → entrada
            sd.description = src_sd.description
            sd.signal_desc = src_sd.signal_desc
            sd.kks         = src_sd.kks
            sd.kks2        = src_sd.kks2
            # Enlace bidireccional
            src_sd.add_link(my_fi, my_si)
            sd.linked_sheets = [src_fi]
            sd.linked_slots  = [src_si]
            # sub_text
            src_sd.rebuild_sub_text(doc, 'right', src_fi, src_si)
            sd.sub_text = f'H.{doc.sheet_ref(src_fi)}:{src_si+1:02d}'
            # Persistir slot_link
            import uuid as _uuid
            with con:
                con.execute(
                    'INSERT OR IGNORE INTO slot_links (link_id, src_slot_id, dst_slot_id) '
                    'VALUES (?,?,?)',
                    (str(_uuid.uuid4()), row['slot_id'], sd.slot_id))
            # Persistir hojas
            sync_sheet(src_sheet)
            sync_sheet(flat[my_fi][0])
            # Refrescar visual de la salida si está en escena activa
            if src_fi == self._scene.sheet_idx:
                items = self._scene.slot_items_right
                if 0 <= src_si < len(items):
                    try: items[src_si].refresh()
                    except RuntimeError: pass
            return   # primer match es suficiente

    def _clear_slot(self, slot: SlotItem):
        """Limpia el conector y rompe el enlace remoto bidireccionalmente."""
        if slot.data.is_linked():
            self._break_remote_link(slot)
        slot.data.description   = ''
        slot.data.signal_desc   = ''
        slot.data.kks           = ''
        slot.data.kks2          = ''
        slot.data.sub_text      = ''
        slot.data.linked_sheets = []
        slot.data.linked_slots  = []
        slot.refresh()

    def _break_remote_link(self, slot: SlotItem):
        """Elimina el enlace de este conector en todos sus remotos.
        Si el remoto es un SALIDA con más enlaces activos, recalcula su sub_text
        para que sólo muestre las referencias que quedan."""
        doc      = self._scene.document
        sd       = slot.data
        my_sheet = self._scene.sheet_idx
        my_idx   = slot.index

        for r_si, r_sl in zip(list(sd.linked_sheets), list(sd.linked_slots)):
            if not (0 <= r_si < doc.sheet_count()): continue
            sheet = doc.sheet_at(r_si)
            # Si slot es ENTRADA (left), el remoto es SALIDA (right) → slots_right
            # Si slot es SALIDA (right), el remoto es ENTRADA (left) → slots_left
            sl_list = (sheet.slots_left if slot.side == 'right' else sheet.slots_right)
            if not (0 <= r_sl < len(sl_list)): continue
            rd = sl_list[r_sl]
            rd.remove_link(my_sheet, my_idx)
            # Reconstruir sub_text del remoto con los enlaces que le quedan
            if rd.is_linked():
                rd.rebuild_sub_text(doc,
                                    'left' if slot.side == 'right' else 'right',
                                    r_si, r_sl)
            else:
                rd.sub_text = ''
            # Refrescar visual del remoto si está en la escena actual
            if r_si == self._scene.sheet_idx:
                items = (self._scene.slot_items_left if slot.side == 'right'
                         else self._scene.slot_items_right)
                if 0 <= r_sl < len(items):
                    try: items[r_sl].refresh()
                    except RuntimeError: pass

    def _remove_single_link(self, src_slot: SlotItem,
                             dst_sheet_idx: int, dst_slot_idx: int):
        """Elimina un enlace específico del SALIDA, manteniendo los demás activos."""
        doc = self._scene.document
        sd  = src_slot.data

        # Quitar del modelo del SALIDA
        sd.remove_link(dst_sheet_idx, dst_slot_idx)
        sd.rebuild_sub_text(doc, 'right', self._scene.sheet_idx, src_slot.index)

        # Limpiar referencia en el ENTRADA remoto
        if 0 <= dst_sheet_idx < doc.sheet_count():
            sheet = doc.sheet_at(dst_sheet_idx)
            sl_list = sheet.slots_left
            if 0 <= dst_slot_idx < len(sl_list):
                rd = sl_list[dst_slot_idx]
                rd.linked_sheets = []
                rd.linked_slots  = []
                rd.sub_text      = ''
                if dst_sheet_idx == self._scene.sheet_idx:
                    items = self._scene.slot_items_left
                    if 0 <= dst_slot_idx < len(items):
                        try: items[dst_slot_idx].refresh()
                        except RuntimeError: pass

        # Refrescar el SALIDA (sub_text actualizado)
        src_slot.refresh()


    def _edit_block(self, bi: BlockItem):
        from widgets.dialogs import BlockDialog
        dlg = BlockDialog(bi.data, self)
        if dlg.exec():
            dlg.apply()
            bi.refresh()

    def _reset_routing(self, ci: ConnItem):
        """Elimina todos los waypoints y deja la ruta por defecto (un codo)."""
        ci.waypoints.clear()
        ci.update_path()

    # ── Copiar / pegar ────────────────────────────────────────────────────

    def _selected_blocks(self):
        return [it for it in self._scene.selectedItems()
                if isinstance(it, BlockItem)]

    # ── selección por rectángulo con overlay ─────────────────────────────

    def _show_sel_rect_menu(self, sel_items, global_pos):
        """Muestra el rectángulo sombreado sobre la selección y el menú contextual."""
        from PyQt6.QtWidgets import QRubberBand, QMenu

        # Calcular bounding rect en coords de vista
        br = None
        for it in sel_items:
            r = it.mapToScene(it.boundingRect()).boundingRect()
            br = r if br is None else br.united(r)
        if br is None:
            return

        # Guardar sel_items antes de cualquier clearSelection
        self._pending_sel_items = list(sel_items)

        # Limpiar overlay anterior (solo el band, sin tocar la selección)
        if self._sel_rect_band is not None:
            self._sel_rect_band.hide()
            self._sel_rect_band.deleteLater()
            self._sel_rect_band = None

        vr = self.mapFromScene(br).boundingRect()
        self._sel_rect_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self._sel_rect_band.setGeometry(vr)
        self._sel_rect_band.show()
        self._state = SEL_RECT

        menu = QMenu(self)
        a_copy   = menu.addAction('📋  Copiar selección')
        a_move   = menu.addAction('✂   Mover selección')
        menu.addSeparator()
        a_cancel = menu.addAction('❌  Cancelar')
        act = menu.exec(global_pos)

        if act == a_copy:
            self._execute_sel_copy()
        elif act == a_move:
            self._execute_sel_move()
        else:
            self._cancel_sel_rect()

    def _cancel_sel_rect(self):
        if self._sel_rect_band is not None:
            self._sel_rect_band.hide()
            self._sel_rect_band.deleteLater()
            self._sel_rect_band = None
        self._scene.clearSelection()
        self._sel_move_items    = []
        self._sel_drag_start    = None
        self._sel_drag_positions = {}
        self._state = IDLE
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def _cancel_sel_move(self):
        """Cancela SEL_MOVE: restaura posiciones y waypoints originales."""
        for it, orig in self._sel_drag_positions.items():
            try:
                it.setPos(orig)
            except RuntimeError:
                pass
        # Restaurar waypoints originales de todas las conexiones afectadas
        for entry in self._affected_conns:
            ci, orig_wps, orig_uw = entry[0], entry[1], entry[2]
            try:
                ci._routing_live   = False
                ci.waypoints       = orig_wps
                ci._user_waypoints = orig_uw
                ci._route_cache    = None
                ci.update_path(invalidate_cache=False)
            except Exception:
                pass
        self._affected_conns = []
        self._cancel_sel_rect()

    def _execute_sel_copy(self):
        """Serializa la selección al portapapeles. El usuario pega con Ctrl+V o menú."""
        sel_items = getattr(self, '_pending_sel_items', None) or list(self._scene.selectedItems())
        blocks    = [it for it in sel_items if isinstance(it, BlockItem)]
        self._copy_block_list_with_conns(blocks, sel_items)
        self._cancel_sel_rect()

    def _execute_sel_move(self):
        """Activa estado SEL_MOVE: el siguiente click+drag mueve el grupo."""
        sel = getattr(self, '_pending_sel_items', None) or list(self._scene.selectedItems())
        # Cerrar overlay sin borrar la selección
        if self._sel_rect_band is not None:
            self._sel_rect_band.hide()
            self._sel_rect_band.deleteLater()
            self._sel_rect_band = None
        # Re-seleccionar los ítems
        self._scene.clearSelection()
        for it in sel:
            try: it.setSelected(True)
            except RuntimeError: pass

        # Clasificar conexiones afectadas
        internal, partial = self._sel_conn_sets(sel)

        # Activar _routing_live en TODAS las conexiones afectadas (internas + parciales).
        # Así durante el drag:
        #   - Los handles no aparecen en posición antigua (update_path no persiste)
        #   - Los stubs de parciales siguen dinámicamente al puerto movido
        #   - Los branches se redibujan en tiempo real
        self._affected_conns = []
        for ci in list(internal) + list(partial):
            try:
                orig_wps = list(ci.waypoints)
                orig_uw  = ci._user_waypoints
                self._affected_conns.append((ci, orig_wps, orig_uw, ci in internal))
                ci.save_branch_t()
                ci._user_waypoints = False
                ci._routing_live   = True
                ci.waypoints.clear()
                ci._route_cache = None
            except Exception:
                pass

        self._sel_move_items     = sel
        # Solo mover ítems posicionables — excluir ConnItem (su posición
        # la definen sus endpoints, no setPos; si se incluyen quedan flotantes)
        self._sel_drag_positions = {
            it: it.pos() for it in sel
            if hasattr(it, 'setPos') and not isinstance(it, ConnItem)
        }
        self._sel_drag_start     = None
        self._state = SEL_MOVE
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)

    def _copy_selection(self):
        sel_items = list(self._scene.selectedItems())
        blocks = [it for it in sel_items if isinstance(it, BlockItem)]
        self._copy_block_list_with_conns(blocks, sel_items)

    def _copy_block(self, bi):
        self._copy_block_list([bi])

    def _sel_conn_sets(self, sel_items):
        """
        Clasifica las conexiones de la hoja respecto a la selección.
        Devuelve (internal, partial) donde:
          internal : ConnItem con ambos extremos en sel_items
          partial  : ConnItem con exactamente un extremo en sel_items
        Reglas para BranchNode:
          - Un BranchNode está "en selección" solo si él mismo Y su parent_conn
            están ambos en la selección interna.
        """
        from items.branch_node import BranchNode as _BN
        sel_set = set(sel_items)

        def _endpoint_in_sel(item, is_slot):
            if is_slot:
                return item in sel_set
            if isinstance(item, _BN):
                return item in sel_set   # se valida después con parent_conn
            return item.parentItem() in sel_set if item.parentItem() else item in sel_set

        # Primera pasada: conexiones sin BranchNode
        internal = set()
        partial  = set()
        for ci in self._scene.conn_items:
            try:
                src_in = _endpoint_in_sel(ci.src_item, ci.src_is_slot)
                dst_in = _endpoint_in_sel(ci.dst_item, ci.dst_is_slot)
                if src_in and dst_in:
                    internal.add(ci)
                elif src_in or dst_in:
                    partial.add(ci)
            except Exception:
                pass

        # Segunda pasada: depurar branches — un branch está en sel solo si
        # su parent_conn también está en internal
        for ci in list(internal):
            try:
                if isinstance(ci.src_item, _BN):
                    if ci.src_item.parent_conn not in internal:
                        internal.discard(ci)
                        partial.add(ci)
                if isinstance(ci.dst_item, _BN):
                    if ci.dst_item.parent_conn not in internal:
                        internal.discard(ci)
                        partial.add(ci)
            except Exception:
                pass

        return internal, partial

    def _copy_block_list_with_conns(self, blocks, sel_items=None):
        """Serializa bloques + conexiones internas a la selección."""
        block_ids  = {id(bi) for bi in blocks}
        all_sel    = sel_items or blocks
        internal, _partial = self._sel_conn_sets(all_sel)

        from items.branch_node import BranchNode as _BN
        conns_data  = []
        branch_data = []   # BranchNodes internos, indexados por conn padre

        # Mapas para serializar branches
        ci_to_key = {}   # ConnItem → key string para referencias de branch

        def _ci_key(ci):
            if ci not in ci_to_key:
                ci_to_key[ci] = ci.conn_id
            return ci_to_key[ci]

        for ci in internal:
            try:
                src_item = ci.src_item
                dst_item = ci.dst_item

                def _ser_ep(item, is_slot):
                    if is_slot:
                        return {'kind': 'slot', 'side': item.side,
                                'index': item.index}
                    if isinstance(item, _BN):
                        return {'kind': 'branch',
                                'branch_id': item.branch_id,
                                'x': item.scenePos().x(),
                                'y': item.scenePos().y()}
                    pi = item
                    bi = pi.parentItem()
                    return {'kind': 'port',
                            'block_id': bi.data.block_id,
                            'port_idx': pi.index,
                            'port_side': pi.side}

                conns_data.append({
                    'conn_id':  _ci_key(ci),
                    'src':      _ser_ep(src_item, ci.src_is_slot),
                    'dst':      _ser_ep(dst_item, ci.dst_is_slot),
                    'waypoints': ci.waypoints_as_tuples(),
                })
            except Exception:
                pass

        QApplication.clipboard().setText(
            json.dumps({'blocks':      [bi.save() for bi in blocks],
                        'connections': conns_data}))

    def _copy_block_list(self, blocks):
        self._copy_block_list_with_conns(blocks)

    def _paste_blocks(self, insert_pos=None):
        """Pega el contenido del portapapeles.
        insert_pos (QPointF escena): si se da, el bloque con coordenadas mínimas
        se coloca en ese punto y el resto mantiene posición relativa.
        Si no, se pega en el centro de la vista.
        """
        try:
            data = json.loads(QApplication.clipboard().text())
        except Exception:
            return
        if 'blocks' in data:
            self._paste_block_data(data['blocks'], data.get('connections', []),
                                   insert_pos=insert_pos)
            self.scene_modified.emit()

    def _paste_block_data(self, block_list, conn_list=None, dx=None, dy=None,
                          insert_pos=None):
        """Pega bloques manteniendo posiciones relativas. Recrea conexiones internas.
        insert_pos: QPointF escena donde se coloca el bloque de coordenada mínima.
        """
        from model import PortData as _PD
        import uuid
        if block_list:
            min_x = min(bd['x'] for bd in block_list)
            min_y = min(bd['y'] for bd in block_list)
            if insert_pos is not None:
                dx = insert_pos.x() - min_x
                dy = insert_pos.y() - min_y
            elif dx is None:
                vr = self.mapToScene(self.viewport().rect()).boundingRect()
                cx = vr.center().x() - (max(bd['x'] for bd in block_list) - min_x) / 2
                cy = vr.center().y() - (max(bd['y'] for bd in block_list) - min_y) / 2
                dx = cx - min_x
                dy = cy - min_y
        else:
            dx = dx if dx is not None else mm(10)
            dy = dy if dy is not None else mm(10)

        id_map = {}   # old block_id → new BlockItem
        for bd in block_list:
            old_id = bd['block_id']
            new_id = str(uuid.uuid4())
            new_block = BlockData(
                block_id       = new_id,
                type_id        = bd['type_id'],
                kks            = bd.get('kks', ''),
                label          = bd.get('label', ''),
                inscription    = bd.get('inscription', ''),
                show_type_label= bd.get('show_type_label', False),
                x              = bd['x'] + dx,
                y              = bd['y'] + dy,
                w              = bd.get('w', 0),
                h              = bd.get('h', 0),
                inputs  = [_PD(name=p['name'], number=p['number'], side='in',
                               signal_type=p.get('signal_type', 'analog'),
                               negated=p.get('negated', False))
                           for p in bd.get('inputs', [])],
                outputs = [_PD(name=p['name'], number=p['number'], side='out',
                               signal_type=p.get('signal_type', 'analog'),
                               negated=p.get('negated', False))
                           for p in bd.get('outputs', [])],
            )
            bi = self._scene.add_block(new_block)
            id_map[old_id] = bi

        # Recrear conexiones internas con el nuevo formato extendido
        # También compatible con el formato antiguo {src_block, dst_block, ...}
        conn_id_map = {}   # old conn_id → new ConnItem (para branches)
        branch_todo = []   # conexiones con src/dst branch, a resolver al final

        def _resolve_ep(ep_data):
            """Resuelve un endpoint serializado → (item, is_slot)."""
            kind = ep_data.get('kind', 'port')
            if kind == 'slot':
                side  = ep_data['side']
                idx   = ep_data['index']
                slots = self._scene.slot_items
                slot  = next((s for s in slots
                              if s.side == side and s.index == idx), None)
                return (slot, True) if slot else (None, True)
            elif kind == 'port':
                bi = id_map.get(ep_data.get('block_id'))
                if bi is None: return (None, False)
                idx  = ep_data.get('port_idx', 0)
                side = ep_data.get('port_side', 'out')
                pool = bi.port_items_out if side == 'out' else bi.port_items_in
                port = next((p for p in pool if p.index == idx), None)
                return (port, False) if port else (None, False)
            elif kind == 'branch':
                return (ep_data, False)   # diferido
            return (None, False)

        for cd in (conn_list or []):
            # Formato antiguo: src_block/dst_block directamente
            if 'src_block' in cd and 'src' not in cd:
                src_bi = id_map.get(cd.get('src_block'))
                dst_bi = id_map.get(cd.get('dst_block'))
                if src_bi is None or dst_bi is None: continue
                try:
                    src_port = next((p for p in src_bi.port_items_out
                                     if p.index == cd.get('src_port_idx', 0)), None)
                    dst_port = next((p for p in dst_bi.port_items_in
                                     if p.index == cd.get('dst_port_idx', 0)), None)
                    if src_port and dst_port:
                        ci = self._scene.add_conn(src_port, False, dst_port, False)
                        if cd.get('conn_id'): conn_id_map[cd['conn_id']] = ci
                except Exception: pass
                continue

            # Formato nuevo
            src_ep = _resolve_ep(cd.get('src', {}))
            dst_ep = _resolve_ep(cd.get('dst', {}))
            old_id = cd.get('conn_id', '')
            wps    = [QPointF(x, y + dy) if False else QPointF(x + dx, y + dy)
                      for x, y in cd.get('waypoints', [])]

            # Si algún extremo es branch → diferir
            if (isinstance(src_ep[0], dict) and src_ep[0].get('kind') == 'branch') or                (isinstance(dst_ep[0], dict) and dst_ep[0].get('kind') == 'branch'):
                branch_todo.append((cd, old_id, wps))
                continue

            src_item, src_is_slot = src_ep
            dst_item, dst_is_slot = dst_ep
            if src_item is None or dst_item is None: continue
            try:
                wps_qp = [QPointF(p.x(), p.y()) for p in wps] or None
                ci = self._scene.add_conn(src_item, src_is_slot,
                                          dst_item, dst_is_slot,
                                          waypoints=wps_qp)
                if old_id: conn_id_map[old_id] = ci
            except Exception: pass

        # Resolver branches (parent_conn debe estar ya creada)
        for cd, old_id, wps in branch_todo:
            try:
                src_d = cd.get('src', {})
                dst_d = cd.get('dst', {})
                # Determinar qué extremo es branch
                if src_d.get('kind') == 'branch':
                    branch_d = src_d
                    other_ep = _resolve_ep(dst_d)
                    branch_is_src = True
                else:
                    branch_d = dst_d
                    other_ep = _resolve_ep(src_d)
                    branch_is_src = False

                parent_ci = conn_id_map.get(cd.get('parent_conn_id', ''))
                if parent_ci is None: continue
                bpos = QPointF(branch_d['x'] + dx, branch_d['y'] + dy)
                bn   = self._scene.add_branch_node(parent_ci, bpos)

                other_item, other_is_slot = other_ep
                if other_item is None: continue
                wps_qp = [QPointF(p.x(), p.y()) for p in wps] or None
                if branch_is_src:
                    ci = self._scene.add_conn(bn, False, other_item, other_is_slot,
                                              waypoints=wps_qp)
                else:
                    ci = self._scene.add_conn(other_item, other_is_slot, bn, False,
                                              waypoints=wps_qp)
                if old_id: conn_id_map[old_id] = ci
            except Exception: pass
    def _copy_to_sheet(self, bi: BlockItem):
        from widgets.dialogs import CopyToSheetDialog
        dlg = CopyToSheetDialog(self._scene.document, self._scene.sheet_idx, self)
        if dlg.exec():
            idx = dlg.selected_sheet_idx()
            if idx is not None and idx != self._scene.sheet_idx:
                cloned = bi.data.clone(dx=mm(5), dy=mm(5))
                self._scene.document.sheet_at(idx).blocks.append(cloned)
                if hasattr(self.parent(), 'on_block_copied_to_sheet'):
                    self.parent().on_block_copied_to_sheet(idx)

    def _retrace_connections_for_selection(self):
        """Recalcula conexiones afectadas tras mover una selección.

        Para cada conexión en _affected_conns (parciales, preparadas en
        _execute_sel_move): recalcula la ruta completa desde cero.
        Los stubs ya apuntan a la nueva posición del puerto porque
        _stub_src/_stub_dst leen scenePos() dinámicamente.

        También recalcula conexiones internas (waypoints desplazados)
        y BranchNodes arrastrados junto con sus conexiones hijo.
        """
        if not self._scene:
            return
        from items.branch_node import BranchNode as _BN

        sel_items = set(self._scene.selectedItems())

        # ── Delta de movimiento ──────────────────────────────────────────
        dx, dy = 0.0, 0.0
        if self._sel_drag_positions:
            deltas = []
            for it, orig in self._sel_drag_positions.items():
                try:
                    cur = it.pos()
                    deltas.append((cur.x() - orig.x(), cur.y() - orig.y()))
                except RuntimeError:
                    pass
            if deltas:
                dx = sum(d[0] for d in deltas) / len(deltas)
                dy = sum(d[1] for d in deltas) / len(deltas)

        internal_set = {ci for ci, _w, _u, is_int in self._affected_conns if is_int}

        # ── BranchNodes de conexiones internas: desplazar ────────────────
        moved_bns: set = set()
        for ci in internal_set:
            for bn in list(self._scene.branch_nodes):
                if bn.parent_conn is ci:
                    try:
                        bn.setPos(bn.pos().x() + dx, bn.pos().y() + dy)
                        moved_bns.add(bn)
                    except RuntimeError:
                        pass

        # ── Conexiones internas: desactivar live, desplazar waypoints, persistir
        for ci, orig_wps, _orig_uw, is_int in self._affected_conns:
            if not is_int:
                continue
            try:
                ci._routing_live   = False
                ci.waypoints       = [QPointF(wp.x() + dx, wp.y() + dy)
                                      for wp in orig_wps]
                ci._user_waypoints = True
                ci._route_cache    = None
                ci.update_path(invalidate_cache=False)
            except Exception:
                pass

        # ── Conexiones hijo de BranchNodes movidos ───────────────────────
        already = {ci for ci, *_ in self._affected_conns}
        for bn in moved_bns:
            for ci in list(bn.connections):
                if ci not in already:
                    try:
                        ci._routing_live   = False
                        ci._user_waypoints = False
                        ci.waypoints.clear()
                        ci._route_cache = None
                        ci.update_path()
                        already.add(ci)
                    except Exception:
                        pass

        # ── Conexiones parciales: desactivar live, recalcular y persistir ──
        for ci, _orig_wps, _orig_uw, is_int in self._affected_conns:
            if is_int:
                continue
            try:
                ci._routing_live   = False
                ci._user_waypoints = False
                ci.waypoints.clear()
                ci._route_cache = None
                ci.update_path()
            except Exception:
                pass

        self._affected_conns = []
        self._scene.rebuild_junctions()

    def _delete_selection(self):
        for it in list(self._scene.selectedItems()):
            if isinstance(it, BlockItem):
                self._scene.remove_block(it)
            elif isinstance(it, ConnItem):
                self._scene.remove_conn(it)
            elif isinstance(it, SymbolItem):
                self._scene.remove_symbol(it)
            elif isinstance(it, NoteItem):
                self._scene.remove_note(it)
            elif isinstance(it, TextBoxItem):
                self._scene.remove_textbox(it)

    # ── helper ────────────────────────────────────────────────────────────

    def _edit_symbol(self, si: SymbolItem):
        from PyQt6.QtWidgets import QInputDialog
        kks, ok = QInputDialog.getText(
            self, 'Editar símbolo', 'KKS / Etiqueta:', text=si.kks)
        if ok:
            si.kks = kks.strip()
            si._build()   # limpia hijos y reconstruye internamente

    def insert_note_center(self):
        """Inserta una nota en el centro visible del viewport."""
        vr = self.mapToScene(self.viewport().rect()).boundingRect()
        cx = vr.center().x()
        cy = vr.center().y()
        self._scene.add_note('Nota…', cx, cy)
    def insert_textbox_center(self):
        r    = self.mapToScene(self.viewport().rect())
        cx   = (r.x() + r.width())  / 2
        cy   = (r.y() + r.height()) / 2
        self._scene.add_textbox('Texto', cx, cy)


    def _in_canvas(self, pos: QPointF) -> bool:
        """Área válida para drop: canvas + franjas de símbolos."""
        in_canvas = (CANVAS_X <= pos.x() <= CANVAS_X + CANVAS_W and
                     CANVAS_Y <= pos.y() <= CANVAS_Y + CANVAS_H)
        # También válido en las franjas interiores junto a los cajones
        in_sym_r  = (COL_R_X - SYM_SIZE <= pos.x() <= COL_R_X and
                     CANVAS_Y <= pos.y() <= CANVAS_Y + CANVAS_H)
        in_sym_l  = (COL_W <= pos.x() <= COL_W + SYM_SIZE and
                     CANVAS_Y <= pos.y() <= CANVAS_Y + CANVAS_H)
        return in_canvas or in_sym_r or in_sym_l
