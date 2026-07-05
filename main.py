"""
main.py — Ventana principal (v11).
"""
from __future__ import annotations
import sys, json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QToolBar,
    QStatusBar, QFileDialog, QMessageBox, QLabel,
    QWidget, QVBoxLayout, QHBoxLayout, QInputDialog, QComboBox
)
from PyQt6.QtGui import QAction, QFont, QKeySequence
from PyQt6.QtCore import Qt, QSize

from model import DocumentData
from scene import DiagramScene
from editor import DiagramEditor
from widgets.library_panel import LibraryPanel
from widgets.dialogs import (NewDocumentDialog, TitleBlockDialog,
                              SheetPropertiesDialog, CoverPageDialog,
                              GroupDialog, IndexDialog)
from io_utils.db_io import (load_document_from_path, save_document_to_path,
                             init_from_document, sync_sheet)
from io_utils.pdf_export import export_pdf, export_pdf_all, export_svg, print_dialog
from io_utils.excel_export import export_excel
from io_utils.dxf_export  import export_dxf_all


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Signal Diagram Editor v11")
        self.resize(1440, 920)
        self._current_file: Path | None = None
        self._modified = False
        self._document: DocumentData | None = None

        self._build_scene()
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._new_default()
        self.show()

    # ── Construcción ──────────────────────────────────────────────────────

    def _build_scene(self):
        self._scene  = DiagramScene()
        self._editor = DiagramEditor(self._scene, self)
        # Conectar señales del editor para enlace inter-hoja
        self._editor.xsheet_link_started.connect(self._on_xsheet_started)
        self._editor.xsheet_link_completed.connect(self._on_xsheet_done)
        self._editor.xsheet_link_cancelled.connect(self._on_xsheet_cancelled)
        self._editor.scene_modified.connect(self._on_scene_modified)

    def _build_ui(self):
        self._lib  = LibraryPanel()
        dock = QDockWidget('Biblioteca', self)
        dock.setWidget(self._lib)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        central = QWidget()
        vlay    = QVBoxLayout(central)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # ── Barra de navegación: Sistema → Grupo → Hoja ──────────────────
        nav = QWidget()
        nav.setFixedHeight(32)
        nav.setStyleSheet('background:#f0f4f8; border-bottom:1px solid #c8d0da;')
        hlay = QHBoxLayout(nav)
        hlay.setContentsMargins(6, 2, 6, 2)
        hlay.setSpacing(6)

        from PyQt6.QtWidgets import QLabel as _Lbl
        def _lbl(t):
            l = _Lbl(t); l.setStyleSheet('color:#556; font-size:11px;'); return l

        self._cb_system = QComboBox(); self._cb_system.setMinimumWidth(160)
        self._cb_group  = QComboBox(); self._cb_group.setMinimumWidth(200)
        self._cb_sheet  = QComboBox(); self._cb_sheet.setMinimumWidth(120)

        hlay.addWidget(_lbl('Sistema:')); hlay.addWidget(self._cb_system)
        hlay.addWidget(_lbl('Grupo:'));   hlay.addWidget(self._cb_group)
        hlay.addWidget(_lbl('Hoja:'));    hlay.addWidget(self._cb_sheet)
        hlay.addStretch()

        self._cb_system.currentIndexChanged.connect(self._on_system_changed)
        self._cb_group.currentIndexChanged.connect(self._on_group_changed)
        self._cb_sheet.currentIndexChanged.connect(self._on_sheet_combo_changed)

        self._nav_updating = False   # bandera para evitar señales en cascada

        vlay.addWidget(nav)
        vlay.addWidget(self._editor)
        self.setCentralWidget(central)

    def _build_menus(self):
        mb = self.menuBar()

        m_file = mb.addMenu('&Archivo')
        self._act(m_file, '&Nuevo documento',    QKeySequence.StandardKey.New,   self._new)
        self._act(m_file, '&Abrir…',             QKeySequence.StandardKey.Open,  self._open)
        m_file.addSeparator()
        self._act(m_file, '&Guardar',            QKeySequence.StandardKey.Save,  self._save)
        self._act(m_file, 'Guardar &como…',      QKeySequence.StandardKey.SaveAs,self._save_as)
        m_file.addSeparator()
        m_exp = m_file.addMenu('&Exportar')
        self._act(m_exp, 'PDF — hoja activa…',    None, self._export_pdf)
        self._act(m_exp, 'PDF — completo (todas las hojas + portada)…',
                                                   None, self._export_pdf_all)
        self._act(m_exp, 'SVG…',                   None, self._export_svg)
        self._act(m_exp, 'Excel / CSV…',            None, self._export_excel)
        self._act(m_exp, 'DXF — todas las hojas…',  None, self._export_dxf)
        self._act(m_exp, 'PDF — catálogo de símbolos…', None, self._export_symbol_catalog)
        m_exp.addSeparator()
        self._act(m_exp, 'Plantilla clonación masiva (Excel)…',
                  None, self._export_clone_template)
        m_file.addSeparator()
        self._act(m_file, '&Imprimir…', QKeySequence.StandardKey.Print, self._print)
        m_file.addSeparator()
        self._act(m_file, 'Salir', QKeySequence.StandardKey.Quit, self.close)

        m_lib = mb.addMenu('&Bi&blioteca')
        self._act(m_lib, 'Exportar biblioteca…', None, self._export_library)
        self._act(m_lib, 'Importar biblioteca…', None, self._import_library)

        m_edit = mb.addMenu('&Editar')
        self._act(m_edit, 'Copiar selección',  QKeySequence.StandardKey.Copy,  self._editor._copy_selection)
        self._act(m_edit, 'Pegar',             QKeySequence.StandardKey.Paste, self._editor._paste_blocks)
        m_edit.addSeparator()
        self._act(m_edit, 'Editar cajetín del documento…', None, self._edit_titleblock)
        self._act(m_edit, 'Configurar portada PDF…',       None, self._edit_cover)

        m_tools = mb.addMenu('&Herramientas')
        self._act(m_tools, '🔍  Análisis de coherencia…',
                  'Ctrl+Shift+H', self._run_coherence)

        m_sheet = mb.addMenu('&Hojas')
        self._act(m_sheet, 'Nuevo grupo…',             'Ctrl+Shift+G', self._new_group)
        self._act(m_sheet, 'Editar grupo actual…',     'Ctrl+Shift+E', self._edit_group)
        self._act(m_sheet, 'Clonar grupo…',            'Ctrl+Shift+C', self._clone_group)
        self._act(m_sheet, 'Importar clonación masiva…', 'Ctrl+Shift+B', self._bulk_clone)
        m_sheet.addSeparator()
        self._act(m_sheet, 'Mover grupo…',              'Ctrl+Shift+V', self._move_group)
        self._act(m_sheet, 'Añadir hoja al grupo',     'Ctrl+Shift+N', self._add_sheet)
        self._act(m_sheet, 'Insertar hoja antes de la actual', 'Ctrl+Shift+M', self._insert_sheet)
        self._act(m_sheet, 'Duplicar hoja actual',     'Ctrl+Shift+D', self._duplicate_sheet)
        self._act(m_sheet, 'Propiedades de hoja…',     'Ctrl+Shift+P', self._sheet_properties)
        m_sheet.addSeparator()
        self._act(m_sheet, 'Eliminar hoja actual',     'Ctrl+Shift+W', self._delete_sheet_menu)

        m_view = mb.addMenu('&Vista')
        self._act(m_view, 'Ajustar página', 'Ctrl+0', self._editor.fit_page)
        self._act(m_view, 'Zoom +',         'Ctrl++', lambda: self._editor.scale(1.25, 1.25))
        self._act(m_view, 'Zoom −',         'Ctrl+-', lambda: self._editor.scale(0.8, 0.8))

        m_help = mb.addMenu('A&yuda')
        self._act(m_help, 'Instrucciones', None, self._help)

    def _act(self, menu, label, shortcut, slot):
        a = QAction(label, self)
        if shortcut: a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_toolbar(self):
        tb = QToolBar('Principal')
        tb.setMovable(False); tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        def btn(lbl, tip, slot):
            a = QAction(lbl, self); a.setToolTip(tip)
            a.triggered.connect(slot); tb.addAction(a)

        btn('📄 Nuevo',   'Nuevo documento',              self._new)
        btn('📂 Abrir',   'Abrir',                        self._open)
        btn('💾 Guardar', 'Guardar',                      self._save)
        tb.addSeparator()
        btn('✅ Commit',   'Guardar estado actual en el fichero (commit)',  self._commit)
        btn('↩ Rollback', 'Descartar cambios y volver al último guardado', self._rollback)
        tb.addSeparator()
        btn('📤 PDF',     'Exportar PDF completo',        self._export_pdf_all)
        btn('📊 Excel',   'Exportar Excel',               self._export_excel)
        btn('📐 DXF',     'Exportar DXF (todas las hojas)',self._export_dxf)
        tb.addSeparator()
        btn('🗂 Grupo',   'Nuevo grupo',                  self._new_group)
        btn('✏ Grupo',   'Editar grupo actual',          self._edit_group)
        btn('↔ Grupo',   'Mover grupo a otra posición',  self._move_group)
        btn('➕ Hoja',    'Añadir hoja al grupo actual',  self._add_sheet)
        btn('⚙ Hoja',    'Propiedades de hoja',          self._sheet_properties)
        tb.addSeparator()
        btn('🔍 Ajustar', 'Ajustar página',               self._editor.fit_page)
        btn('✏ Cajetín', 'Editar cajetín del documento', self._edit_titleblock)
        tb.addSeparator()
        btn('⊕ Intercalar', 'Intercalar hojas desde el grupo activo',  self._intercalar_hojas)
        btn('⊖ Eliminar',   'Eliminar (renumerar) hojas desde activo', self._eliminar_hojas)

    def _build_statusbar(self):
        sb = QStatusBar(); self.setStatusBar(sb)
        self._lbl_status = QLabel('Listo'); sb.addWidget(self._lbl_status)
        # Barra de enlace inter-hoja (oculta por defecto)
        self._lbl_xsheet = QLabel()
        self._lbl_xsheet.setStyleSheet(
            'color:#884400;background:#FFF4CC;padding:3px 8px;'
            'border:1px solid #CC8800;border-radius:3px;')
        self._lbl_xsheet.hide()
        sb.addWidget(self._lbl_xsheet)
        hint = QLabel(
            '  Doble clic: editar  |  Puerto→clic→destino: conectar  |  '
            'Shift+clic conexión: bifurcar  |  Alt+clic conexión: re-enrutar  |  '
            'Clic derecho cajón salida: enlazar inter-hoja  |  '
            'Ctrl+C/V: copiar/pegar  |  Rueda: zoom')
        hint.setFont(QFont('Segoe UI', 7))
        hint.setStyleSheet('color:#667788;')
        sb.addPermanentWidget(hint)

    # ── Documento ─────────────────────────────────────────────────────────

    def _new_default(self):
        doc = DocumentData()
        doc.add_group('Grupo 1', system='Sistema 1', num_slots=23, sheet_number_base=10)
        for g in doc.groups:
            for s in g.sheets:
                s._loaded = True
        init_from_document(doc)
        self._load_document(doc)

    def _new(self):
        dlg = NewDocumentDialog(self)
        if dlg.exec():
            doc = dlg.make_document()
            for g in doc.groups:
                for s in g.sheets:
                    s._loaded = True
            init_from_document(doc)
            self._load_document(doc)
            self._current_file = None
            self._set_modified(False)

    def _load_document(self, doc: DocumentData):
        # NOTA: NO sincronizar aquí la hoja actual. Si el llamador necesita
        # guardar el estado previo (p.ej. _open) debe llamar
        # _sync_current_sheet() antes. En _rollback, sincronizar
        # sobrescribiría la BD recién recargada desde disco.
        # Reconstruir enlaces cruzados en memoria (slot_links → linked_sheets)
        if doc is not None:
            try:
                from io_utils.clone_group import rebuild_xsheet_links
                from io_utils.db_io import resolve_linked_sheets
                rebuild_xsheet_links(doc)
                resolve_linked_sheets(doc)
            except Exception:
                pass
        self._document = doc
        self._rebuild_tabs()
        self._editor.on_sheet_about_to_change()
        self._scene.load_sheet(doc, 0)
        self._update_window_title()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._editor.fit_page)
        QTimer.singleShot(10, self._rebuild_library_panel)

    def _rebuild_tabs(self):
        """Reconstruye los tres desplegables desde el documento actual."""
        if not self._document: return
        self._nav_updating = True
        # Sistemas únicos en orden
        systems = self._document.all_systems()
        self._cb_system.blockSignals(True)
        self._cb_group.blockSignals(True)
        self._cb_sheet.blockSignals(True)
        self._cb_system.clear()
        for s in systems:
            self._cb_system.addItem(s or '(sin sistema)')
        self._cb_system.blockSignals(False)
        self._cb_group.blockSignals(False)
        self._cb_sheet.blockSignals(False)
        self._nav_updating = False
        if systems:
            self._cb_system.setCurrentIndex(0)
            self._refresh_group_combo(systems[0])
            self._refresh_sheet_combo()

    # ── Gestión de navegación Sistema/Grupo/Hoja ─────────────────────────

    def _current_sheet_idx(self) -> int:
        """Índice plano de la hoja actualmente visible."""
        if not self._document: return 0
        sys_name = self._cb_system.currentText()
        grp_idx  = self._cb_group.currentIndex()
        sht_idx  = self._cb_sheet.currentIndex()
        if sys_name == '' or grp_idx < 0 or sht_idx < 0: return 0
        # Grupos del sistema actual
        groups = [g for g in self._document.groups
                  if (g.system or '') == sys_name.replace('(sin sistema)', '')]
        if grp_idx >= len(groups): return 0
        g = groups[grp_idx]
        if sht_idx >= len(g.sheets): return 0
        return self._document.flat_index_of(g.sheets[sht_idx])

    def _sync_current_sheet(self):
        """Sincroniza escena → modelo Python → BD en memoria.
        Llamar antes de cualquier commit/rollback y antes de cambiar de hoja.
        """
        if self._document:
            self._scene.sync_to_model()
            sheet = self._scene.sheet
            if sheet is not None:
                from io_utils.db_io import sync_sheet
                try:
                    sync_sheet(sheet)
                except Exception:
                    pass

    def _refresh_group_combo(self, system_name: str, keep_idx: int = 0):
        """Rellena el combo de grupos (silencioso, sin navegar)."""
        self._cb_group.blockSignals(True)
        self._cb_group.clear()
        if self._document:
            real_sys = system_name.replace('(sin sistema)', '')
            for g in self._document.groups:
                if (g.system or '') == real_sys:
                    label = f"{g.kks} — {g.description}" if g.kks else (g.description or g.group_id[:8])
                    self._cb_group.addItem(label)
        self._cb_group.blockSignals(False)
        # Seleccionar índice deseado sin disparar navegación
        if self._cb_group.count():
            self._cb_group.blockSignals(True)
            self._cb_group.setCurrentIndex(min(keep_idx, self._cb_group.count() - 1))
            self._cb_group.blockSignals(False)
        self._refresh_sheet_combo()

    def _refresh_sheet_combo(self, keep_idx: int = 0):
        """Rellena el combo de hojas (silencioso, sin navegar)."""
        self._cb_sheet.blockSignals(True)
        self._cb_sheet.clear()
        if self._document:
            sys_name = self._cb_system.currentText().replace('(sin sistema)', '')
            grp_idx  = self._cb_group.currentIndex()
            groups   = [g for g in self._document.groups
                        if (g.system or '') == sys_name]
            if 0 <= grp_idx < len(groups):
                g = groups[grp_idx]
                for li, s in enumerate(g.sheets):
                    num = g.sheet_number_base + li
                    label = f'H{num:02d}' + (f' — {s.sheet_name}' if s.sheet_name else '')
                    self._cb_sheet.addItem(label)
        if self._cb_sheet.count():
            self._cb_sheet.blockSignals(True)
            self._cb_sheet.setCurrentIndex(min(keep_idx, self._cb_sheet.count() - 1))
            self._cb_sheet.blockSignals(False)
        self._cb_sheet.blockSignals(False)

    def _navigate_now(self):
        """Carga la hoja apuntada por los tres combos en ese momento."""
        flat_idx = self._current_sheet_idx()
        self._sync_current_sheet()
        self._editor.on_sheet_about_to_change()
        self._scene.load_sheet(self._document, flat_idx)
        if self._editor.pending_link:
            self._lbl_xsheet.show()

    def _on_system_changed(self, idx: int):
        if self._nav_updating or idx < 0 or not self._document: return
        system = self._cb_system.itemText(idx)
        self._refresh_group_combo(system, keep_idx=0)
        self._navigate_now()

    def _on_group_changed(self, idx: int):
        if self._nav_updating or idx < 0 or not self._document: return
        self._refresh_sheet_combo(keep_idx=0)
        self._navigate_now()

    def _on_sheet_combo_changed(self, idx: int):
        if self._nav_updating or idx < 0 or not self._document: return
        self._navigate_now()

    def _on_tab_changed(self, idx: int):
        pass   # ya no se usa, mantenido por compatibilidad

    def _update_tab_label(self, idx: int):
        """Actualiza los combos de navegación para reflejar cambios."""
        self._rebuild_tabs()
        # Restaurar selección al índice plano correcto
        self._navigate_to(idx)

    def _navigate_to(self, flat_idx: int):
        """Navega los tres combos al índice plano dado."""
        if not self._document: return
        flat = self._document.flat_sheets()
        if not (0 <= flat_idx < len(flat)): return
        _, g  = flat[flat_idx]
        sys_name = g.system or ''
        # Seleccionar sistema
        cb_sys_text = sys_name or '(sin sistema)'
        sys_i = self._cb_system.findText(cb_sys_text)
        if sys_i < 0: return
        self._nav_updating = True
        self._cb_system.setCurrentIndex(sys_i)
        self._nav_updating = False
        self._refresh_group_combo(cb_sys_text)
        # Seleccionar grupo
        groups = [gr for gr in self._document.groups
                  if (gr.system or '') == sys_name]
        try:
            gi = groups.index(g)
        except ValueError:
            return
        self._nav_updating = True
        self._cb_group.setCurrentIndex(gi)
        self._nav_updating = False
        self._refresh_sheet_combo()
        # Seleccionar hoja
        li = sum(1 for i, (_, g2) in enumerate(flat)
                 if i < flat_idx and g2.group_id == g.group_id)
        self._nav_updating = True
        self._cb_sheet.setCurrentIndex(li)
        self._nav_updating = False

    def _new_group(self):
        if not self._document: return
        ns = 23
        if self._document.groups and self._document.groups[0].sheets:
            ns = self._document.groups[0].sheets[0].num_slots
        dlg = GroupDialog(self._document, parent=self)
        if dlg.exec():
            self._sync_current_sheet()
            g = dlg.create_group(self._document, ns)
            self._apply_group_autofill(g, overwrite=False)
            new_flat_idx = self._document.sheet_count() - len(g.sheets)
            self._rebuild_tabs()
            self._navigate_to(new_flat_idx)
            # Cargar la hoja en la escena (navigate_to bloquea señales)
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(self._document, new_flat_idx)
            self._set_modified(True)

    def _move_group(self):
        """Mueve un grupo a otra posición de numeración."""
        if not self._document: return
        if not self._document.groups:
            return

        # Grupo activo como preselección
        idx     = self._current_sheet_idx()
        g_cur   = self._document.group_at(idx)
        cur_gid = g_cur.group_id if g_cur else ''

        from widgets.move_group_dialog import MoveGroupDialog
        dlg = MoveGroupDialog(self._document, current_group_id=cur_gid, parent=self)
        if not dlg.exec():
            return

        g_to_move = dlg.selected_group()
        new_base  = dlg.dest_base()
        if g_to_move is None:
            return

        self._sync_current_sheet()

        # Ejecutar el movimiento estructural
        ok, result = self._document.move_group(g_to_move.group_id, new_base)
        if not ok:
            QMessageBox.warning(self, 'No se puede mover', result)
            return

        # Reconstruir todas las referencias cruzadas desde KKS y persistir
        from io_utils.clone_group import rebuild_xsheet_links
        from io_utils.db_io import sync_document
        rebuild_xsheet_links(self._document)
        sync_document(self._document)

        # Navegar al grupo movido (primera hoja)
        flat    = self._document.flat_sheets()
        dest_fi = next(
            (i for i, (s, g) in enumerate(flat) if g is g_to_move), 0
        )
        self._rebuild_tabs()
        self._navigate_to(dest_fi)
        self._scene.load_sheet(self._document, dest_fi)
        self._set_modified(True)

    def _clone_group(self):
        """Clona un grupo completo con sustituciones de texto y auto-link KKS."""
        if not self._document:
            return
        from widgets.clone_dialog import CloneGroupDialog
        from io_utils.clone_group  import clone_group_sql, apply_kks_autolink
        from io_utils.db_io        import load_document, sync_document

        dlg = CloneGroupDialog(self._document, parent=self)
        if not dlg.exec():
            return

        src_gi = dlg.src_group_idx()
        rules  = dlg.rules()

        # Sincronizar estado actual a la BD antes de operar
        self._sync_current_sheet()
        sync_document(self._document)

        doc       = self._document
        src_group = doc.groups[src_gi]

        try:
            real_doc_id   = getattr(doc, '_doc_id', None) or 'main'
            override_base = dlg.override_sheet_base()
            new_gid = clone_group_sql(
                src_group.group_id,
                real_doc_id, rules,
                override_base=override_base)
            from io_utils.db_io import get_mem
            get_mem().commit()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            try: get_mem().rollback()
            except Exception: pass
            QMessageBox.critical(self, "Error al clonar", str(e))
            return

        # Recargar documento desde la BD en memoria
        new_doc = load_document()
        if new_doc is None:
            return

        # Reconstruir todas las referencias cruzadas desde KKS
        apply_kks_autolink(new_doc)

        # Reconstruir linked_sheets/linked_slots en memoria desde slot_links
        from io_utils.db_io import resolve_linked_sheets
        resolve_linked_sheets(new_doc)

        # Persistir
        sync_document(new_doc)

        # Actualizar referencias en la app
        self._document = new_doc
        self._rebuild_tabs()
        # Navegar al primer sheet del nuevo grupo y cargarlo en la escena
        new_group = next((g for g in new_doc.groups
                          if g.group_id == new_gid), None)
        if new_group and new_group.sheets:
            flat = new_doc.flat_sheets()
            nav_idx = next((i for i, (s, g) in enumerate(flat)
                            if g.group_id == new_gid), 0)
            self._navigate_to(nav_idx)
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(new_doc, nav_idx)
        self._set_modified(True)
        self._status(f"Grupo clonado correctamente.")

    def _edit_group(self):
        if not self._document: return
        idx = self._current_sheet_idx()
        g   = self._document.group_at(idx)
        if g is None: return
        dlg = GroupDialog(self._document, group=g, parent=self)
        if dlg.exec():
            n_slots  = sum(1 for s in g.sheets for sd in s.slots_right
                           if sd.description or sd.kks)
            n_blocks = sum(len(s.blocks) for s in g.sheets)
            if n_slots + n_blocks > 0:
                ret = QMessageBox.question(
                    self, 'Confirmar edición de grupo',
                    f'Esta acción actualizará:\n'
                    f'  • {n_slots} conector(es) de salida con descripción o KKS\n'
                    f'  • {n_blocks} bloque(s) con KKS del grupo\n\n'
                    f'¿Continuar?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ret != QMessageBox.StandardButton.Yes:
                    return
            dlg.apply_to_group(g)
            self._apply_group_autofill(g, overwrite=True)
            # Refrescar SlotItems visibles en la escena actual
            for si in self._scene.slot_items_right:
                try: si.refresh()
                except Exception: pass
            self._rebuild_tabs()
            self._navigate_to(idx)
            self._sync_current_sheet()
            self._scene.load_sheet(self._document, idx)
            self._set_modified(True)

    def _apply_group_autofill(self, group, overwrite: bool):
        kks  = group.kks
        desc = group.description
        doc  = self._document
        for sheet in group.sheets:
            # Conectores de salida: relleno solo ocurre al conectar (en tiempo real).
            # Al editar grupo (overwrite=True) se actualizan los que ya tenian valor
            # Y se propagan a todos sus conectores de entrada enlazados.
            if overwrite:
                for slot in sheet.slots_right:
                    if slot.description:
                        slot.description = _wrap_description(desc)
                    if slot.kks:
                        slot.kks = kks[:14]
                    # Propagar a todos los conectores de entrada enlazados
                    if slot.is_linked():
                        self._propagate_slot_to_inputs(slot, doc)
            # KKS de bloques: siempre se sincroniza
            for block in sheet.blocks:
                if overwrite or not block.kks:
                    block.kks = kks

    def _propagate_slot_to_inputs(self, src_slot, doc):
        """Copia descripción, señal y KKS del conector de salida a todos sus
        conectores de entrada enlazados, y actualiza sus sub_text."""
        flat = doc.flat_sheets()
        for dst_sheet_idx, dst_slot_idx in zip(src_slot.linked_sheets, src_slot.linked_slots):
            if not (0 <= dst_sheet_idx < len(flat)):
                continue
            dst_sheet, _ = flat[dst_sheet_idx]
            if not (0 <= dst_slot_idx < len(dst_sheet.slots_left)):
                continue
            dst = dst_sheet.slots_left[dst_slot_idx]
            dst.description = src_slot.description
            dst.signal_desc = src_slot.signal_desc
            dst.kks         = src_slot.kks
            dst.kks2        = src_slot.kks2
            # Recalcular sub_text del destino (apunta al origen)
            src_sheet_idx = doc.flat_index_of(next(
                s for s, g in flat if any(sl is src_slot for sl in s.slots_right)
            ))
            dst.sub_text = f'H.{doc.sheet_ref(src_sheet_idx)}:{dst_slot_idx+1:02d}'
            # Refrescar SlotItem si está en la escena activa
            for si in self._scene.slot_items_left:
                try:
                    if si.data is dst:
                        si.refresh()
                except Exception:
                    pass

    def _add_sheet(self):
        if not self._document: return
        idx = self._current_sheet_idx()
        g   = self._document.group_at(idx)
        if g is None: return
        self._sync_current_sheet()
        ns = g.sheets[0].num_slots if g.sheets else 23
        new_sheet = g.add_sheet(ns)
        # Propagar desplazamiento si el nuevo número pisa el grupo siguiente
        gi = self._document.groups.index(g)
        self._document.cascade_shift_after_insert(gi)
        self._apply_group_autofill(g, overwrite=False)
        flat = self._document.flat_sheets()
        new_flat_idx = next(i for i, (s, g2) in enumerate(flat)
                            if s.sheet_id == new_sheet.sheet_id)
        self._rebuild_tabs()
        self._navigate_to(new_flat_idx)
        self._set_modified(True)

    def _insert_sheet(self):
        """Inserta una hoja nueva ANTES de la actual (toma su número de hoja)
        y desplaza en cascada los grupos siguientes si es necesario."""
        if not self._document: return
        idx = self._current_sheet_idx()
        g   = self._document.group_at(idx)
        if g is None: return
        self._sync_current_sheet()

        # Calcular índice local y flat_idx de inserción ANTES de modificar la lista
        flat_before = self._document.flat_sheets()
        cur_sheet   = flat_before[idx][0]
        local_idx   = next(li for li, s in enumerate(g.sheets) if s is cur_sheet)
        insert_flat_idx = idx   # la nueva hoja tomará exactamente este flat_idx

        ns = g.sheets[0].num_slots if g.sheets else 23
        new_sheet = g.insert_sheet_at(local_idx, ns)

        # 1. Remapear linked_sheets: índices >= insert_flat_idx suben 1
        self._document.remap_links_after_insert(insert_flat_idx)

        # 2. Cascada numérica: propagar si el nuevo número pisa el grupo siguiente
        gi = self._document.groups.index(g)
        self._document.cascade_shift_after_insert(gi)

        # 3. Recalcular sub_texts y persistir a BD
        self._apply_group_autofill(g, overwrite=False)
        self._rebuild_all_sub_texts()
        from io_utils.db_io import sync_document, sync_sheet
        new_sheet._loaded = True
        sync_document(self._document)
        sync_sheet(new_sheet)

        flat2 = self._document.flat_sheets()
        new_flat_idx = next(i for i, (s, g2) in enumerate(flat2)
                            if s.sheet_id == new_sheet.sheet_id)
        self._rebuild_tabs()
        self._navigate_to(new_flat_idx)
        # Cargar directamente la nueva hoja vacía en la escena.
        # No llamar on_sheet_about_to_change() aquí: los combos ya apuntan
        # a new_flat_idx, y esa llamada volvería a escribir el canvas actual
        # (contenido de la hoja original) en new_sheet, corrompiendo la nueva hoja.
        # _sync_current_sheet() al inicio ya guardó la hoja original correctamente.
        self._scene.load_sheet(self._document, new_flat_idx)
        self._set_modified(True)

    # ── Intercalar / Eliminar hojas (renumeración por tramos) ─────────────

    def _intercalar_hojas(self):
        """Desplaza hacia adelante los números de hoja desde el grupo activo."""
        if not self._document: return
        idx   = self._current_sheet_idx()
        g_act = self._document.group_at(idx)
        if g_act is None: return
        gi    = self._document.groups.index(g_act)

        from PyQt6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(
            self, 'Intercalar hojas',
            f'Número de hojas a intercalar antes del grupo "{g_act.description or g_act.kks or "actual"}".\n'
            f'Se sumará este valor al número base de todos los grupos\n'
            f'desde el grupo actual hasta el final del documento.',
            value=10, min=1, max=999)
        if not ok or n <= 0:
            return

        ok2, msg = self._document.can_shift(gi, n)
        if not ok2:
            QMessageBox.warning(self, 'No se puede intercalar', msg)
            return

        self._document.shift_from(gi, n)
        self._rebuild_all_sub_texts()
        from io_utils.db_io import sync_document
        sync_document(self._document)
        self._rebuild_tabs()
        self._navigate_to(idx)
        self._set_modified(True)

    def _eliminar_hojas(self):
        """Desplaza hacia atrás los números de hoja desde el grupo activo."""
        if not self._document: return
        idx   = self._current_sheet_idx()
        g_act = self._document.group_at(idx)
        if g_act is None: return
        gi    = self._document.groups.index(g_act)

        from PyQt6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(
            self, 'Eliminar / renumerar hojas',
            f'Número de hojas a eliminar del espacio de numeración.\n'
            f'Se restará este valor al número base de todos los grupos\n'
            f'desde el grupo actual hasta el final del documento.\n\n'
            f'La aplicación comprobará que no se producen duplicados.',
            value=10, min=1, max=999)
        if not ok or n <= 0:
            return

        ok2, msg = self._document.can_shift(gi, -n)
        if not ok2:
            QMessageBox.warning(self, 'No se puede renumerar', msg)
            return

        self._document.shift_from(gi, -n)
        self._rebuild_all_sub_texts()
        from io_utils.db_io import sync_document
        sync_document(self._document)
        self._rebuild_tabs()
        self._navigate_to(idx)
        self._set_modified(True)

    def _duplicate_sheet(self):
        if not self._document: return
        import copy, uuid
        self._sync_current_sheet()
        cur  = self._current_sheet_idx()
        g    = self._document.group_at(cur)
        if g is None: return
        sheet = self._document.sheet_at(cur)
        dup   = copy.deepcopy(sheet)
        dup.sheet_id = str(uuid.uuid4())
        for sl in dup.slots_left + dup.slots_right:
            sl.slot_id = str(uuid.uuid4())
        for bl in dup.blocks:
            bl.block_id = str(uuid.uuid4())
        g.sheets.append(dup)
        self._apply_group_autofill(g, overwrite=False)
        flat      = self._document.flat_sheets()
        new_idx   = next(i for i, (s, _) in enumerate(flat) if s.sheet_id == dup.sheet_id)
        local_idx = len(g.sheets) - 1
        self._rebuild_tabs()
        self._navigate_to(new_idx)
        self._set_modified(True)
    def _rebuild_all_sub_texts(self):
        """Recalcula sub_text en memoria para todos los slots enlazados
        y persiste a BD las hojas afectadas para que al navegar a ellas
        se cargue el texto actualizado (no el valor antiguo de la BD)."""
        doc = self._document
        if not doc: return
        from io_utils.db_io import sync_sheet as _sync_sheet
        for sheet_idx, (sheet, _) in enumerate(doc.flat_sheets()):
            dirty = False
            for slot_idx, sd in enumerate(sheet.slots_left):
                if sd.linked_sheets:
                    sd.rebuild_sub_text(doc, 'left', sheet_idx, slot_idx)
                    dirty = True
            for slot_idx, sd in enumerate(sheet.slots_right):
                if sd.linked_sheets:
                    sd.rebuild_sub_text(doc, 'right', sheet_idx, slot_idx)
                    dirty = True
            if dirty:
                if not getattr(sheet, '_loaded', False):
                    # Hoja nunca visitada: cargar desde BD para tener su contenido
                    # completo y poder reescribirla con el sub_text actualizado.
                    try:
                        from io_utils.db_io import load_sheet_content
                        load_sheet_content(sheet)
                    except Exception:
                        pass
                # Persistir el nuevo sub_text a BD.
                try:
                    _sync_sheet(sheet)
                except Exception:
                    pass


    def _sheet_properties(self):
        if not self._document: return
        idx   = self._current_sheet_idx()
        sheet = self._document.sheet_at(idx)
        if sheet is None: return
        dlg   = SheetPropertiesDialog(sheet, self)
        if dlg.exec():
            dlg.apply()
            self._update_tab_label(idx)
            # Recalcular sub_text de todos los slots enlazados (el número de hoja puede haber cambiado)
            self._rebuild_all_sub_texts()
            # Recargar para reflejar cambios en cajetín y sub_texts actualizados
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(self._document, idx)
            self._set_modified(True)

    def _close_sheet(self, idx: int):
        if not self._document: return
        if self._document.sheet_count() <= 1:
            QMessageBox.warning(self, 'Eliminar hoja',
                                'El documento debe tener al menos una hoja.')
            return
        g = self._document.group_at(idx)
        if g is None: return
        sheet = self._document.sheet_at(idx)
        ret = QMessageBox.question(
            self, 'Eliminar hoja',
            f'¿Eliminar esta hoja del grupo "{g.description or g.group_id[:8]}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes: return
        g.sheets = [s for s in g.sheets if s.sheet_id != sheet.sheet_id]
        if not g.sheets:
            # Si el grupo queda vacío, eliminar el grupo
            self._document.groups = [gr for gr in self._document.groups
                                     if gr.group_id != g.group_id]
        new_idx = min(idx, max(0, self._document.sheet_count() - 1))
        self._editor.on_sheet_about_to_change()
        self._rebuild_tabs()
        self._navigate_to(new_idx)
        self._scene.load_sheet(self._document, new_idx)
        self._set_modified(True)

    def _delete_sheet_menu(self):
        self._close_sheet(self._current_sheet_idx())


    def on_block_copied_to_sheet(self, target_idx: int):
        # Actualizar la pestaña destino
        self._update_tab_label(target_idx)
        self._set_modified(True)
    def _on_xsheet_started(self, msg: str):
        self._lbl_xsheet.setText(f'🔗  {msg}')
        self._lbl_xsheet.show()
        self._status('Modo enlace inter-hoja activo — navega a la hoja de destino')

    def _on_xsheet_done(self):
        self._lbl_xsheet.hide()
        self._status('Enlace inter-hoja establecido ✓')
        self._set_modified(True)

    def _on_xsheet_cancelled(self):
        self._lbl_xsheet.hide()
        self._status('Enlace inter-hoja cancelado')

    # ── Cajetín y portada ─────────────────────────────────────────────────

    def _edit_titleblock(self):
        if not self._document: return
        dlg = TitleBlockDialog(self._document.title_block, self)
        if dlg.exec():
            dlg.apply()
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(self._document, self._current_sheet_idx())
            self._set_modified(True)

    def _edit_cover(self):
        if not self._document: return
        dlg = CoverPageDialog(self._document.cover, self._document.title_block, self)
        if dlg.exec():
            dlg.apply()
            self._set_modified(True)

    # ── Archivo ───────────────────────────────────────────────────────────

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Abrir documento', '', 'Diagrama (*.sdg);;Todos (*)')
        if path:
            try:
                doc = load_document_from_path(path)
                self._load_document(doc)
                self._current_file = Path(path)
                self._set_modified(False)
                self._status(f'Abierto: {path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error al abrir', f'{type(e).__name__}: {e}')

    def _save(self):
        if self._current_file: self._do_save(self._current_file)
        else: self._save_as()

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Guardar', '', 'Diagrama (*.sdg);;Todos (*)')
        if path:
            if not path.endswith('.sdg'): path += '.sdg'
            self._do_save(Path(path))

    def _do_save(self, path: Path):
        self._sync_current_sheet()
        try:
            save_document_to_path(self._document, path)
            self._current_file = path
            self._set_modified(False)
            self._status(f'Guardado: {path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error al guardar', f'{type(e).__name__}: {e}')

    def _commit(self):
        """Guarda el estado actual de la BD en memoria al fichero (commit)."""
        if not self._current_file:
            self._save_as()
            return
        self._sync_current_sheet()
        try:
            from io_utils.db_io import sync_document, save_db
            sync_document(self._document)
            save_db(self._current_file)
            self._set_modified(False)
            self._status(f'Commit: {self._current_file.name}')
        except Exception as e:
            QMessageBox.critical(self, 'Error en commit', f'{type(e).__name__}: {e}')

    def _rollback(self):
        """Descarta todos los cambios en memoria y recarga desde el fichero."""
        if not self._current_file or not self._current_file.exists():
            QMessageBox.information(self, 'Rollback',
                'No hay fichero guardado al que volver.')
            return
        ret = QMessageBox.question(
            self, 'Confirmar rollback',
            'Se descartarán todos los cambios desde el último commit.\n¿Continuar?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            doc = load_document_from_path(self._current_file)
            self._load_document(doc)
            self._set_modified(False)
            self._status(f'Rollback: {self._current_file.name}')
        except Exception as e:
            QMessageBox.critical(self, 'Error en rollback', f'{type(e).__name__}: {e}')

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar PDF — hoja activa', '', 'PDF (*.pdf)')
        if path:
            if not path.endswith('.pdf'): path += '.pdf'
            self._sync_current_sheet()
            try:
                export_pdf(self._scene, path)
                self._status(f'PDF exportado: {path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error PDF', f'{type(e).__name__}: {e}')

    def _export_pdf_all(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar PDF completo', '', 'PDF (*.pdf)')
        if path:
            if not path.endswith('.pdf'): path += '.pdf'
            self._sync_current_sheet()
            try:
                export_pdf_all(self._document, self._scene, path)
                n = self._document.sheet_count()
                portada = ' (+ portada)' if self._document.cover.show else ''
                self._status(f'PDF completo{portada}: {n} hojas → {path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error PDF', f'{type(e).__name__}: {e}')

    def _export_svg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar SVG', '', 'SVG (*.svg)')
        if path:
            if not path.endswith('.svg'): path += '.svg'
            try:
                export_svg(self._scene, path)
                self._status(f'SVG: {path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error SVG', f'{type(e).__name__}: {e}')

    def _export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar señales', '',
            'Excel (*.xlsx);;CSV (*.csv)')
        if path:
            self._sync_current_sheet()
            try:
                export_excel(self._document, path)
                self._status(f'Excel: {path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error Excel', f'{type(e).__name__}: {e}')

    def _run_coherence(self):
        """Abre el diálogo de análisis de coherencia del documento."""
        if not self._document:
            return
        from io_utils.db_io import sync_document
        from widgets.coherence_dialog import CoherenceDialog
        self._sync_current_sheet()
        sync_document(self._document)
        dlg = CoherenceDialog(
            self._document,
            self._scene,
            navigate_fn=self._navigate_to,
            parent=self)
        dlg.exec()
        # Recargar escena por si hubo reparaciones en la hoja activa
        idx = self._current_sheet_idx()
        if idx >= 0:
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(self._document, idx)

    # ─── Plantilla clonacion masiva ───────────────────────────────────────────

    def _export_clone_template(self):
        if not self._document:
            return
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from widgets.export_template_dialog import ExportTemplateDialog
        from io_utils.bulk_clone import export_template_excel
        dlg = ExportTemplateDialog(self._document, parent=self)
        if not dlg.exec():
            return
        group_ids = dlg.selected_group_ids()
        if not group_ids:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar plantilla de clonacion", "plantilla_clonacion.xlsx",
            "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_template_excel(self._document, group_ids, path)
            self._status("Plantilla exportada: " + path)
            QMessageBox.information(
                self, "Plantilla exportada",
                "Plantilla guardada en:\n" + path + "\n\n" +
                str(len(group_ids)) + " grupo(s) incluido(s).")
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar plantilla", str(e))

    # ─── Clonacion masiva ─────────────────────────────────────────────────────

    def _bulk_clone(self):
        if not self._document:
            return
        from widgets.bulk_import_dialog import BulkImportDialog
        from io_utils.db_io import load_document, sync_document
        from io_utils.clone_group import apply_kks_autolink

        self._sync_current_sheet()
        dlg = BulkImportDialog(self._document, parent=self)
        if not dlg.exec():
            return
        if not dlg.new_group_ids():
            return
        new_doc = load_document()
        if new_doc is None:
            return
        apply_kks_autolink(new_doc)
        from io_utils.db_io import resolve_linked_sheets
        resolve_linked_sheets(new_doc)
        sync_document(new_doc)
        self._document = new_doc
        self._rebuild_tabs()
        first_gid = dlg.new_group_ids()[0]
        new_grp = next((g for g in new_doc.groups if g.group_id == first_gid), None)
        if new_grp and new_grp.sheets:
            flat = list(new_doc.flat_sheets())
            nav_idx = next((i for i, (s, g) in enumerate(flat)
                            if g.group_id == first_gid), 0)
            self._navigate_to(nav_idx)
            self._editor.on_sheet_about_to_change()
            self._scene.load_sheet(new_doc, nav_idx)
        self._set_modified(True)
        self._status("Clonacion masiva: " + str(len(dlg.new_group_ids())) + " grupo(s) creado(s).")


    def _export_symbol_catalog(self):
        """Exporta el catálogo de símbolos /NNN como PDF."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar catálogo de símbolos', 'simbolos.pdf',
            'PDF (*.pdf)')
        if not path:
            return
        try:
            from io_utils.symbol_catalog_pdf import export_symbol_catalog
            export_symbol_catalog(path)
            self._status(f'Catálogo exportado: {path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error al exportar catálogo', str(e))

    def _export_dxf(self):
        """Exporta a DXF con dialogo que permite crear carpeta nueva."""
        import os
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                      QLabel, QLineEdit, QPushButton,
                                      QDialogButtonBox)
        base = self._current_file or ""
        default_dir = (str(Path(base).parent / (Path(base).stem + "_dxf"))
                       if base else os.path.expanduser("~"))
        dlg = QDialog(self)
        dlg.setWindowTitle("Exportar DXF")
        dlg.setMinimumWidth(500)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Carpeta destino (se creara si no existe):"))
        row = QHBoxLayout()
        ed = QLineEdit(default_dir); row.addWidget(ed, 1)
        btn_b = QPushButton("Examinar..."); row.addWidget(btn_b)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        def _browse():
            chosen = QFileDialog.getExistingDirectory(
                dlg, "Seleccionar directorio base", ed.text() or default_dir)
            if chosen:
                ed.setText(chosen)
        btn_b.clicked.connect(_browse)
        if not dlg.exec():
            return
        out_dir = ed.text().strip()
        if not out_dir:
            return
        self._sync_current_sheet()
        try:
            # Limpiar archivos DXF de la revisión anterior en ese directorio
            out_path = Path(out_dir)
            if out_path.exists():
                for old in out_path.glob('*.dxf'):
                    try:
                        old.unlink()
                    except Exception:
                        pass
            exported = export_dxf_all(self._document, self._scene, out_dir)
            n = len(exported)
            self._status("DXF: " + str(n) + " ficheros en " + out_dir)
            msg = str(n) + " ficheros DXF en:" + chr(10) + out_dir
            QMessageBox.information(self, "Exportacion DXF", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error DXF",
                                 type(e).__name__ + ": " + str(e))
    def _print(self):
        self._sync_current_sheet()
        try: print_dialog(self._scene, self)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'{type(e).__name__}: {e}')

    # ── Ayuda ─────────────────────────────────────────────────────────────

    # ── Biblioteca ───────────────────────────────────────────────────────

    def _export_library(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from library_io import export_library
        from model import BLOCK_LIBRARY, BlockType
        from io_utils.db_io import load_sheet_content
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar biblioteca', 'biblioteca_bloques.txt',
            'Archivos de biblioteca (*.txt);;Todos (*.*)'
        )
        if not path:
            return
        try:
            # Recopilar bloques de usuario (CUSTOM) únicos del documento en curso,
            # deduplicados por inscripción. Cada configuración de puertos distinta
            # se exporta como un tipo propio en la categoría 'Usuario'.
            user_types: dict[str, BlockType] = {}   # inscripción → BlockType
            if self._document:
                for sheet, _ in self._document.flat_sheets():
                    if not getattr(sheet, '_loaded', False):
                        try: load_sheet_content(sheet)
                        except Exception: pass
                    for bd in sheet.blocks:
                        if bd.type_id != 'CUSTOM':
                            continue
                        key = (bd.inscription or bd.label or 'USER').strip()
                        if key in user_types:
                            continue   # ya registrado
                        # Construir un BlockType desde la instancia concreta
                        bt = BlockType(
                            type_id      = f'USER_{key}',
                            name         = key,
                            category     = 'Usuario',
                            has_kks      = True,
                            default_ins  = len(bd.inputs),
                            default_outs = len(bd.outputs),
                            color        = '#F5F0FF',
                            description  = key,
                            port_type    = 'analog',
                            in_names     = tuple(p.name for p in bd.inputs),
                            out_names    = tuple(p.name for p in bd.outputs),
                        )
                        bt.width_mm       = bd.w if bd.w else 20.0
                        bt.inscription    = key
                        bt.extensible_in  = False
                        bt.extensible_out = False
                        bt.in_types  = tuple(p.signal_type for p in bd.inputs)
                        bt.out_types = tuple(p.signal_type for p in bd.outputs)
                        user_types[key] = bt

            # Exportar: biblioteca estándar + tipos de usuario del documento
            export_list = [bt for bt in BLOCK_LIBRARY if bt.type_id != 'CUSTOM']
            export_list += list(user_types.values())

            n_user = len(user_types)
            export_library(export_list, path)
            msg = f'Biblioteca exportada:\n{path}'
            if n_user:
                msg += f'\n\n{n_user} bloque(s) de usuario incluido(s) desde el documento.'
            QMessageBox.information(self, 'Exportar biblioteca', msg)
        except Exception as e:
            QMessageBox.critical(self, 'Error al exportar', str(e))

    def _import_library(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from library_io import import_library
        import model

        path, _ = QFileDialog.getOpenFileName(
            self, 'Importar biblioteca', '',
            'Archivos de biblioteca (*.txt);;Todos (*.*)'
        )
        if not path:
            return

        new_types, warnings, errors = import_library(path)

        if errors:
            err_txt = '\n'.join(errors[:10])
            more = f'\n…y {len(errors)-10} más' if len(errors) > 10 else ''
            ret = QMessageBox.warning(
                self, 'Errores en el archivo',
                f'Se encontraron errores:\n{err_txt}{more}\n\n¿Continuar con los bloques válidos?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        if not new_types:
            QMessageBox.warning(self, 'Importar biblioteca',
                'No se encontraron bloques válidos en el archivo.')
            return

        # Detectar type_ids que desaparecen
        new_ids = {bt.type_id for bt in new_types}
        old_ids = {bt.type_id for bt in model.BLOCK_LIBRARY}
        removed = old_ids - new_ids - {'CUSTOM'}

        # Buscar bloques huérfanos en el documento
        orphans = []
        for sheet, _ in self._document.flat_sheets():
            for bd in sheet.blocks:
                if bd.type_id in removed:
                    orphans.append(bd)

        if orphans:
            ids_list = ', '.join(sorted(removed))
            ret = QMessageBox.warning(
                self, 'Tipos eliminados',
                f'Los siguientes tipos ya no existen en la nueva biblioteca:\n{ids_list}\n\n'
                f'Hay {len(orphans)} bloque(s) con esos tipos.\n'
                f'Se convertirán a tipo CUSTOM conservando sus puertos.\n\n¿Continuar?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            for bd in orphans:
                bd.type_id = 'CUSTOM'

        # Sustituir biblioteca en memoria
        model.BLOCK_LIBRARY.clear()
        model.BLOCK_LIBRARY.extend(new_types)
        # CUSTOM siempre presente
        if 'CUSTOM' not in new_ids:
            from model import BlockType
            model.BLOCK_LIBRARY.append(BlockType(
                type_id='CUSTOM', name='USER', category='Usuario',
                has_kks=True, default_ins=2, default_outs=2,
                color='#F5F5F5', description='Bloque personalizado',
                port_type='analog',
                in_names=('IN1','IN2'), out_names=('OUT1','OUT2'),
                width_mm=20, inscription='',
                extensible_in=True, extensible_out=True,
                in_types=('analog','analog'), out_types=('analog','analog'),
            ))
        model.LIBRARY_BY_ID.clear()
        model.LIBRARY_BY_ID.update({bt.type_id: bt for bt in model.BLOCK_LIBRARY})
        model.LIBRARY_CATEGORIES.clear()
        model.LIBRARY_CATEGORIES.extend(sorted({bt.category for bt in model.BLOCK_LIBRARY}))

        # Refrescar BlockItems en escena
        for bi in list(self._editor._scene.block_items):
            try: bi.refresh()
            except Exception: pass

        self._rebuild_library_panel()

        msg = f'Biblioteca importada: {len(new_types)} tipos.'
        if warnings:
            msg += f'\n{len(warnings)} aviso(s):\n' + '\n'.join(warnings[:5])
        QMessageBox.information(self, 'Importar biblioteca', msg)

    def _rebuild_library_panel(self):
        """Reconstruye el dock de biblioteca tras cambiar la librería."""
        # Delegar completamente al panel: reconstruye símbolos + bloques
        self._lib._build_tree()

    def _help(self):
        QMessageBox.information(self, 'Instrucciones', """
<b>Signal Diagram Editor</b><br><br>
<b>Bloques:</b> Arrastra desde la biblioteca al área central.<br>
<b>Cajones:</b> Doble clic para editar KKS y referencia.<br>
<b>Conexiones:</b> Clic en puerto de salida → clic en destino.<br>
&nbsp;&nbsp;Con la conexión seleccionada, clic sobre ella → nuevo punto de quiebre.<br>
&nbsp;&nbsp;Arrastra los handles naranjas. Doble clic en handle → eliminarlo.<br><br>
<b>Enlace inter-hoja:</b><br>
&nbsp;&nbsp;1. Clic derecho en cajón de SALIDAS → "Enlazar con cajón de otra hoja"<br>
&nbsp;&nbsp;2. Navega a la hoja destino (pestaña inferior)<br>
&nbsp;&nbsp;3. Clic izquierdo en el cajón de ENTRADAS de destino<br>
&nbsp;&nbsp;→ Se sincroniza el KKS y se establece la referencia HH:CC en ambos cajones<br><br>
<b>Propiedades de hoja:</b> Menú Hojas → Propiedades (número libre + título propio)<br>
<b>Portada PDF:</b> Menú Editar → Configurar portada PDF<br>
<b>PDF completo:</b> exporta portada + todas las hojas con márgenes<br>
<b>Copiar:</b> Ctrl+C / Ctrl+V, o clic derecho → Copiar a hoja<br>
""")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _status(self, msg): self._lbl_status.setText(msg)

    def _update_window_title(self):
        tb = self._document.title_block if self._document else None
        t  = tb.title if tb and tb.title else 'Sin título'
        self.setWindowTitle(f'Signal Diagram Editor v11 — {t}')

    def _on_scene_modified(self):
        """Sincroniza escena → BD en memoria y marca el documento como modificado."""
        self._sync_current_sheet()
        self._set_modified(True)

    def _set_modified(self, val: bool):
        self._modified = val
        base = self.windowTitle().lstrip('* ')
        self.setWindowTitle(('* ' if val else '') + base)

    def closeEvent(self, event):
        if self._modified:
            ret = QMessageBox.question(
                self, 'Salir', '¿Descartar cambios no guardados?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore(); return
        event.accept()


# ── Arranque ──────────────────────────────────────────────────────────────



def _wrap_description(desc: str, max_len: int = 35) -> str:
    """Adapta la descripcion al campo de conector: maximo 2x35 chars."""
    if not desc: return ''
    if len(desc) <= max_len: return desc
    cut = desc[:max_len].rfind(' ')
    if cut < 1: cut = max_len
    line1 = desc[:cut].strip()
    line2 = desc[cut:cut + max_len].strip()
    return (line1 + '\n' + line2) if line2 else line1

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 9))
    app.setStyleSheet("""
        QMainWindow { background:#E8EEF5; }
        QMenuBar { background:#1A2A4A; color:#EEF; }
        QMenuBar::item:selected { background:#2A4A7A; }
        QMenu { background:#F5F8FF; border:1px solid #AAB; }
        QMenu::item:selected { background:#3355AA; color:white; }
        QToolBar { background:#2A3A5A; border:none; padding:2px; }
        QToolButton { color:white; padding:4px 8px; }
        QToolButton:hover { background:#3A5A8A; border-radius:3px; }
        QDockWidget::title { background:#2A3A5A; color:white; padding:4px; }
        QStatusBar { background:#E0E8F0; color:#334; }
        QTabBar::tab { padding:5px 14px; background:#C8D8F0;
                       border:1px solid #AAB; border-bottom:none; min-width:80px; }
        QTabBar::tab:selected { background:#F5F8FF; font-weight:bold; }
        QTabBar::tab:hover { background:#D8E8FF; }
        QPushButton { background:#3355AA; color:white; border:none;
                      padding:5px 14px; border-radius:3px; }
        QPushButton:hover { background:#2244AA; }
        QLineEdit, QComboBox, QSpinBox { border:1px solid #AABBCC;
                                         border-radius:3px; padding:3px 6px; }
        QTabWidget::pane { border:1px solid #AABBCC; }
        QTreeWidget, QTableWidget { border:1px solid #AABBCC; background:#FAFCFF; }
        QHeaderView::section { background:#D0DAF0; padding:3px; border:none; }
    """)
    win = MainWindow()
    sys.exit(app.exec())
