"""
widgets/dialogs.py — Diálogos de edición (v5).
- SlotDialog: sin campo signal, KKS 18 chars
- SheetPropertiesDialog: número libre + título propio
- TitleBlockDialog: completo
- CoverPageDialog: portada PDF
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QSpinBox, QCheckBox,
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit,
    QHeaderView, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from model import (SlotData, BlockData, PortData, DocumentData,
                   BLOCK_LIBRARY, LIBRARY_CATEGORIES, LIBRARY_BY_ID,
                   TitleBlockData, CoverPageData)
from const import KKS_CHARS   # = 18


def _lbl(txt):
    l = QLabel(txt); l.setFont(QFont('Segoe UI', 9)); return l

def _sec(txt):
    l = QLabel(txt)
    f = QFont('Segoe UI', 8); f.setBold(True); l.setFont(f)
    l.setStyleSheet('color:#334466;border-bottom:1px solid #aab;padding-bottom:2px;')
    return l


def _mked(initial: str = '', height: int = 56) -> QTextEdit:
    """QTextEdit con selección, copia, pega y menú contextual garantizados."""
    from PyQt6.QtCore import Qt as _Qt
    ed = QTextEdit(initial)
    ed.setFixedHeight(height)
    # Menú contextual estándar (Cortar/Copiar/Pegar/Seleccionar todo)
    ed.setContextMenuPolicy(_Qt.ContextMenuPolicy.DefaultContextMenu)
    ed.setUndoRedoEnabled(True)
    return ed


# ── Nuevo documento ───────────────────────────────────────────────────────

class NewDocumentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Nuevo documento')
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(_sec('Datos del documento (cajetín)'))
        form = QFormLayout()
        self.ed_title    = QLineEdit()
        self.ed_doc      = QLineEdit()
        self.ed_project  = QLineEdit()
        self.ed_plant    = QLineEdit()
        self.ed_rev      = QLineEdit('A')
        self.ed_company  = QLineEdit()
        self.ed_drawn    = QLineEdit()
        self.ed_checked  = QLineEdit()
        self.ed_approved = QLineEdit()
        self.sp_slots    = QSpinBox()
        self.sp_slots.setRange(4, 40); self.sp_slots.setValue(23)
        form.addRow(_lbl('Título:'),       self.ed_title)
        form.addRow(_lbl('Nº Documento:'), self.ed_doc)
        form.addRow(_lbl('Proyecto:'),     self.ed_project)
        form.addRow(_lbl('Planta:'),       self.ed_plant)
        form.addRow(_lbl('Revisión:'),     self.ed_rev)
        form.addRow(_lbl('Empresa:'),      self.ed_company)
        form.addRow(_lbl('Elaborado:'),    self.ed_drawn)
        form.addRow(_lbl('Revisado:'),     self.ed_checked)
        form.addRow(_lbl('Aprobado:'),     self.ed_approved)
        form.addRow(_lbl('Cajones/hoja:'), self.sp_slots)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def make_document(self) -> DocumentData:
        from datetime import date
        from model import TitleBlockData, DocumentData
        tb = TitleBlockData(
            title       = self.ed_title.text().strip(),
            doc_number  = self.ed_doc.text().strip(),
            project     = self.ed_project.text().strip(),
            plant       = self.ed_plant.text().strip(),
            revision    = self.ed_rev.text().strip(),
            company     = self.ed_company.text().strip(),
            drawn_by    = self.ed_drawn.text().strip(),
            checked_by  = self.ed_checked.text().strip(),
            approved_by = self.ed_approved.text().strip(),
            date        = date.today().isoformat(),
        )
        doc = DocumentData(title_block=tb)
        doc.add_group('Grupo 1', system='Sistema 1', num_slots=self.sp_slots.value(),
                      sheet_number_base=10)
        return doc


# ── Editar cajetín ────────────────────────────────────────────────────────

class TitleBlockDialog(QDialog):
    def __init__(self, tb: TitleBlockData, parent=None):
        super().__init__(parent)
        self.tb = tb
        self.setWindowTitle('Editar cajetín')
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        fields = [
            ('Título:',       'ed_title',    tb.title),
            ('Nº Documento:', 'ed_doc',      tb.doc_number),
            ('Proyecto:',     'ed_project',  tb.project),
            ('Planta:',       'ed_plant',    tb.plant),
            ('Revisión:',     'ed_rev',      tb.revision),
            ('Fecha:',        'ed_date',     tb.date),
            ('Empresa:',      'ed_company',  tb.company),
            ('Elaborado:',    'ed_drawn',    tb.drawn_by),
            ('Revisado:',     'ed_checked',  tb.checked_by),
            ('Aprobado:',     'ed_approved', tb.approved_by),
        ]
        from datetime import date as _dt
        _today = _dt.today().isoformat()
        for lbl, attr, val in fields:
            # Sugerir fecha actual si el campo fecha está vacío
            if attr == 'ed_date' and not val:
                val = _today
            ed = QLineEdit(val); setattr(self, attr, ed)
            form.addRow(_lbl(lbl), ed)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self):
        self.tb.title       = self.ed_title.text().strip()
        self.tb.doc_number  = self.ed_doc.text().strip()
        self.tb.project     = self.ed_project.text().strip()
        self.tb.plant       = self.ed_plant.text().strip()
        self.tb.revision    = self.ed_rev.text().strip()
        self.tb.date        = self.ed_date.text().strip()
        self.tb.company     = self.ed_company.text().strip()
        self.tb.drawn_by    = self.ed_drawn.text().strip()
        self.tb.checked_by  = self.ed_checked.text().strip()
        self.tb.approved_by = self.ed_approved.text().strip()


# ── Propiedades de hoja (número libre + título propio) ────────────────────

class SheetPropertiesDialog(QDialog):
    def __init__(self, sheet, parent=None):
        super().__init__(parent)
        self.sheet = sheet
        self.setWindowTitle('Propiedades de hoja')
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_name   = QLineEdit(sheet.sheet_name)
        self.ed_number = QLineEdit(sheet.sheet_number)
        self.ed_number.setPlaceholderText('vacío = automático (1, 2, 3…)')
        self.ed_title  = QLineEdit(sheet.sheet_title)
        self.ed_title.setPlaceholderText('título específico de esta hoja')

        form.addRow(_lbl('Nombre de pestaña:'), self.ed_name)
        form.addRow(_lbl('Número de hoja:'),    self.ed_number)
        form.addRow(_lbl('Título de hoja:'),    self.ed_title)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self):
        self.sheet.sheet_name   = self.ed_name.text().strip()
        self.sheet.sheet_number = self.ed_number.text().strip()
        self.sheet.sheet_title  = self.ed_title.text().strip()


# ── Portada PDF ───────────────────────────────────────────────────────────

class CoverPageDialog(QDialog):
    def __init__(self, cover: CoverPageData, tb: TitleBlockData, parent=None):
        super().__init__(parent)
        self.cover = cover
        self.setWindowTitle('Configurar portada PDF')
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        lay.addWidget(_sec('Portada del PDF exportado'))

        self.chk_show = QCheckBox('Incluir portada en el PDF')
        self.chk_show.setChecked(cover.show)
        lay.addWidget(self.chk_show)

        form = QFormLayout()
        self.ed_subtitle = QLineEdit(cover.subtitle)
        self.ed_subtitle.setPlaceholderText('subtítulo opcional bajo el título principal')
        self.ed_desc = _mked(cover.description, 80)
        self.ed_desc.setPlaceholderText('descripción o alcance del documento')
        form.addRow(_lbl('Subtítulo:'),   self.ed_subtitle)
        form.addRow(_lbl('Descripción:'), self.ed_desc)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self):
        self.cover.show        = self.chk_show.isChecked()
        self.cover.subtitle    = self.ed_subtitle.text().strip()
        self.cover.description = self.ed_desc.toPlainText().strip()



# ── Editar conector ──────────────────────────────────────────────────────

class SlotDialog(QDialog):
    def __init__(self, data, side, document=None, sheet_idx=0, parent=None):
        super().__init__(parent)
        self.data = data
        col = 'ENTRADA' if side == 'left' else 'SALIDA'
        self.setWindowTitle(f'Conector {data.slot_id[:6]}... [{col}]')
        self.setMinimumWidth(460)
        lay  = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        f_mono = QFont('Courier New', 9)

        self.ed_desc = _mked(data.description, 56)
        self.ed_desc.setFont(f_mono)
        self.ed_desc.setPlaceholderText('2 lineas, 24 chars/linea')
        self.ed_desc.textChanged.connect(self._limit_desc)
        form.addRow(_lbl('Desc. equipo:'), self.ed_desc)

        self.ed_sig = _mked(data.signal_desc, 56)
        self.ed_sig.setFont(f_mono)
        self.ed_sig.setPlaceholderText('2 lineas, 9 chars/linea')
        self.ed_sig.textChanged.connect(self._limit_sig)
        form.addRow(_lbl('Desc. senal:'), self.ed_sig)

        self.ed_kks = QLineEdit(data.kks)
        self.ed_kks.setFont(f_mono)
        self.ed_kks.setMaxLength(14)
        self.ed_kks.setPlaceholderText('14 chars max')
        form.addRow(_lbl('KKS:'), self.ed_kks)

        self.ed_kks2 = QLineEdit(getattr(data, 'kks2', ''))
        self.ed_kks2.setFont(f_mono)
        self.ed_kks2.setMaxLength(14)
        self.ed_kks2.setPlaceholderText('14 chars max')
        form.addRow(_lbl('KKS (linea 2):'), self.ed_kks2)

        if data.sub_text:
            lbl_ref = QLabel(data.sub_text)
            lbl_ref.setStyleSheet('color:#003399;font-style:italic;background:#eef2ff;padding:3px;border-radius:3px;')
            form.addRow(_lbl('Ref. auto:'), lbl_ref)
        if data.is_linked():
            lbl_lk = QLabel(f'Enlazado: hoja {data.linked_sheet+1}, conector {data.linked_slot+1:02d}')
            lbl_lk.setStyleSheet('color:#006600;font-style:italic;')
            form.addRow(_lbl('Estado:'), lbl_lk)

        lay.addLayout(form)
        btn_clr = QPushButton('Limpiar conector')
        btn_clr.clicked.connect(self._clear)
        lay.addWidget(btn_clr)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _clip(ed, max_lines, max_chars):
        cursor = ed.textCursor()
        pos    = cursor.position()
        lines  = ed.toPlainText().split('\n')
        changed = False
        for i in range(len(lines)):
            if len(lines[i]) > max_chars:
                lines[i] = lines[i][:max_chars]; changed = True
        if len(lines) > max_lines:
            lines = lines[:max_lines]; changed = True
        if changed:
            joined = '\n'.join(lines)
            ed.blockSignals(True)
            ed.setPlainText(joined)
            cursor.setPosition(min(pos, len(joined)))
            ed.setTextCursor(cursor)
            ed.blockSignals(False)

    def _limit_desc(self): self._clip(self.ed_desc, 2, 24)
    def _limit_sig(self):  self._clip(self.ed_sig,  2, 9)
    def _limit_kks(self):  self._clip(self.ed_kks,  2, 15)

    def _clear(self):
        self.ed_desc.clear(); self.ed_sig.clear()
        self.ed_kks.clear(); self.ed_kks2.clear()

    def _limit_kks(self): pass   # QLineEdit ya limita con setMaxLength

    def apply(self):
        self.data.description = self.ed_desc.toPlainText().strip()
        self.data.signal_desc = self.ed_sig.toPlainText().strip()
        self.data.kks         = self.ed_kks.text().strip()
        self.data.kks2        = self.ed_kks2.text().strip()



# ── Editar bloque ─────────────────────────────────────────────────────────

class BlockDialog(QDialog):
    def __init__(self, data: BlockData, parent=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle('Bloque')
        self.setMinimumWidth(480); self.setMinimumHeight(460)

        main = QVBoxLayout(self)
        tabs = QTabWidget(); main.addWidget(tabs)

        # Tab General
        tab_gen = QWidget(); tabs.addTab(tab_gen, 'General')
        gl = QVBoxLayout(tab_gen)
        gl.addWidget(_sec('Tipo de bloque'))
        tl = QHBoxLayout()
        self.cb_cat  = QComboBox()
        self.cb_cat.addItems(['(todos)'] + LIBRARY_CATEGORIES)
        self.cb_type = QComboBox()
        tl.addWidget(_lbl('Cat:')); tl.addWidget(self.cb_cat)
        tl.addSpacing(8)
        tl.addWidget(_lbl('Tipo:')); tl.addWidget(self.cb_type)
        gl.addLayout(tl)
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet('color:#556;font-style:italic;')
        gl.addWidget(self.lbl_desc)
        gl.addSpacing(6); gl.addWidget(_sec('Datos'))
        form = QFormLayout()
        self.ed_kks   = QLineEdit(data.kks)
        self.ed_kks.setMaxLength(18)
        self.ed_kks.setFont(QFont('Courier New', 10))
        self.ed_label = QLineEdit(data.label)
        self.ed_label.setPlaceholderText('opcional')
        form.addRow(_lbl('KKS:'),      self.ed_kks)
        form.addRow(_lbl('Etiqueta:'), self.ed_label)
        # Anchura e inscripción — sobreescribibles por instancia
        bt0 = LIBRARY_BY_ID.get(data.type_id)
        def_w = getattr(bt0, 'width_mm', 20) if bt0 else 20
        cur_w = round(data.w / 10) if data.w > 0 else def_w   # unidades→mm
        self.sp_width = QSpinBox()
        self.sp_width.setRange(10, 120); self.sp_width.setSuffix(' mm')
        self.sp_width.setValue(int(cur_w))
        def_insc = getattr(bt0, 'inscription', '') if bt0 else ''
        self.ed_insc = QLineEdit(data.inscription or def_insc)
        self.ed_insc.setPlaceholderText('texto/emoji centrado (opcional)')
        form.addRow(_lbl('Anchura:'),     self.sp_width)
        form.addRow(_lbl('Inscripción:'), self.ed_insc)
        self.chk_type_lbl = QCheckBox('Mostrar nombre del tipo en la cabecera')
        self.chk_type_lbl.setChecked(getattr(data, 'show_type_label', False))
        form.addRow('', self.chk_type_lbl)
        gl.addLayout(form); gl.addStretch()

        # Tab Puertos
        tab_p = QWidget(); tabs.addTab(tab_p, 'Puertos')
        pl = QVBoxLayout(tab_p)
        pl.addWidget(_sec('Entradas (izquierda)'))
        self.tbl_in  = self._make_tbl(); pl.addWidget(self.tbl_in)
        h1 = QHBoxLayout()
        self._btn_add_in = self._pbtn('+ Entrada', lambda: self._add(self.tbl_in,'in'))
        h1.addWidget(self._btn_add_in)
        h1.addWidget(self._pbtn('− Elim.',   lambda: self._del(self.tbl_in)))
        h1.addStretch(); pl.addLayout(h1)
        pl.addWidget(_sec('Salidas (derecha)'))
        self.tbl_out = self._make_tbl(); pl.addWidget(self.tbl_out)
        h2 = QHBoxLayout()
        self._btn_add_out = self._pbtn('+ Salida', lambda: self._add(self.tbl_out,'out'))
        h2.addWidget(self._btn_add_out)
        h2.addWidget(self._pbtn('− Elim.',   lambda: self._del(self.tbl_out)))
        h2.addStretch(); pl.addLayout(h2)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        main.addWidget(bb)

        self.cb_cat.currentIndexChanged.connect(self._filter)
        # Conectar _on_type DESPUÉS de setCurrentIndex para evitar disparo prematuro
        self._filter()
        if data.type_id:
            idx = self.cb_type.findData(data.type_id)
            if idx >= 0:
                # Bloquear señal durante la selección inicial
                self.cb_type.blockSignals(True)
                self.cb_type.setCurrentIndex(idx)
                self.cb_type.blockSignals(False)
        # Poblar con datos existentes si los hay; si no, usar defaults del tipo
        if data.inputs or data.outputs:
            self._populate()
            self._update_ext_buttons()  # sincronizar botones add/del con extensible
        else:
            self._on_type()
        self.cb_type.currentIndexChanged.connect(self._on_type)

    def _update_ext_buttons(self):
        """Actualiza habilitación de botones añadir segun extensible del tipo actual."""
        from model import LIBRARY_BY_ID
        tid     = self.cb_type.currentData()
        bt      = LIBRARY_BY_ID.get(tid)
        ext_in  = getattr(bt, 'extensible_in',  True) if bt else True
        ext_out = getattr(bt, 'extensible_out', True) if bt else True
        custom  = (tid == 'CUSTOM')
        if hasattr(self, '_btn_add_in'):
            self._btn_add_in.setEnabled(ext_in  or custom)
            self._btn_add_out.setEnabled(ext_out or custom)

    def _make_tbl(self):
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(['Nº', 'Nombre', 'Tipo', 'Neg'])
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        t.setMaximumHeight(160); return t

    def _pbtn(self, txt, slot):
        b = QPushButton(txt); b.clicked.connect(slot); return b

    def _add(self, tbl, side, sig_type='analog', name='', negated=False):
        row = tbl.rowCount(); tbl.insertRow(row)
        tbl.setItem(row, 0, QTableWidgetItem(
            f"{'E' if side=='in' else 'S'}{row+1}"))
        tbl.setItem(row, 1, QTableWidgetItem(name))
        cb = QComboBox(); cb.addItems(['Analógica', 'Digital'])
        cb.setCurrentIndex(1 if sig_type == 'digital' else 0)
        tbl.setCellWidget(row, 2, cb)
        # Col 3: checkbox Neg — solo activo para digitales
        chk_w = QWidget(); chk_lay = QHBoxLayout(chk_w)
        chk_lay.setContentsMargins(4,0,4,0); chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk = QCheckBox(); chk.setChecked(negated and sig_type == 'digital')
        chk.setEnabled(sig_type == 'digital')
        chk_lay.addWidget(chk)
        tbl.setCellWidget(row, 3, chk_w)
        # Cuando cambia el tipo, actualizar el estado del checkbox
        def _on_type_change(idx, r=row, t=tbl):
            is_dig = (idx == 1)
            w = t.cellWidget(r, 3)
            if w:
                ch = w.findChild(QCheckBox)
                if ch:
                    ch.setEnabled(is_dig)
                    if not is_dig: ch.setChecked(False)
                    # Colorear fondo para indicar que no es seleccionable
                    w.setStyleSheet('' if is_dig else 'background:#e8e8e8;')
        cb.currentIndexChanged.connect(_on_type_change)
        # Aplicar estado inicial de fondo si es analógico
        if sig_type != 'digital':
            chk_w.setStyleSheet('background:#e8e8e8;')

    def _del(self, tbl):
        sel = tbl.selectedIndexes()
        row = sel[0].row() if sel else tbl.rowCount() - 1
        if row >= 0:
            tbl.removeRow(row)

    def _filter(self):
        cat = self.cb_cat.currentText()
        self.cb_type.clear()
        for bt in BLOCK_LIBRARY:
            if cat == '(todos)' or bt.category == cat:
                self.cb_type.addItem(f"{bt.name} — {bt.description}", bt.type_id)

    def _on_type(self):
        tid = self.cb_type.currentData()
        bt  = LIBRARY_BY_ID.get(tid)
        if bt:
            self.lbl_desc.setText(bt.description)
            self.ed_kks.setEnabled(bt.has_kks)
            pt = getattr(bt, 'port_type', 'analog')
            in_names  = getattr(bt, 'in_names',  ())
            out_names = getattr(bt, 'out_names', ())
            in_types  = getattr(bt, 'in_types',  ())
            out_types = getattr(bt, 'out_types', ())
            ext_in    = getattr(bt, 'extensible_in',  False)
            ext_out   = getattr(bt, 'extensible_out', False)
            # Limpiar y recargar con nombres por defecto del nuevo tipo
            self.tbl_in.setRowCount(0)
            self.tbl_out.setRowCount(0)
            for i in range(bt.default_ins):
                name = in_names[i] if i < len(in_names) else f'IN{i+1}'
                sig  = in_types[i] if i < len(in_types) else pt
                self._add(self.tbl_in, 'in', sig, name)
            for i in range(bt.default_outs):
                name = out_names[i] if i < len(out_names) else f'OUT{i+1}'
                sig  = out_types[i] if i < len(out_types) else pt
                self._add(self.tbl_out, 'out', sig, name)
            # Actualizar anchura e inscripción
            if hasattr(self, 'sp_width'):
                self.sp_width.setValue(int(getattr(bt, 'width_mm', 20)))
            if hasattr(self, 'ed_insc'):
                self.ed_insc.setText(getattr(bt, 'inscription', ''))
            # Controlar visibilidad de botones de añadir puertos
            if hasattr(self, '_btn_add_in'):
                self._btn_add_in.setEnabled(ext_in or tid == 'CUSTOM')
                self._btn_add_out.setEnabled(ext_out or tid == 'CUSTOM')

    def _populate(self):
        for pd in self.data.inputs:
            self._add(self.tbl_in, 'in',
                      getattr(pd, 'signal_type', 'analog'), pd.name,
                      getattr(pd, 'negated', False))
        for pd in self.data.outputs:
            self._add(self.tbl_out, 'out',
                      getattr(pd, 'signal_type', 'analog'), pd.name,
                      getattr(pd, 'negated', False))

    def _read_ports(self, tbl, side):
        ports = []
        for row in range(tbl.rowCount()):
            ni  = tbl.item(row, 1)
            cb  = tbl.cellWidget(row, 2)
            st  = 'digital' if (cb and cb.currentIndex() == 1) else 'analog'
            chk_w = tbl.cellWidget(row, 3)
            chk   = chk_w.findChild(QCheckBox) if chk_w else None
            neg   = bool(chk and chk.isChecked() and st == 'digital')
            ports.append(PortData(name=ni.text().strip() if ni else '',
                                  number=row+1, side=side,
                                  signal_type=st, negated=neg))
        return ports

    def apply(self):
        from const import mm as _mm
        tid = self.cb_type.currentData()
        if tid: self.data.type_id = tid
        self.data.kks         = self.ed_kks.text().strip()
        self.data.label       = self.ed_label.text().strip()
        self.data.inscription     = self.ed_insc.text().strip()
        self.data.show_type_label  = self.chk_type_lbl.isChecked()
        self.data.w           = _mm(self.sp_width.value())
        self.data.h           = 0   # se recalcula en _compute_size
        self.data.inputs      = self._read_ports(self.tbl_in,  'in')
        self.data.outputs     = self._read_ports(self.tbl_out, 'out')


# ── Copiar a hoja ─────────────────────────────────────────────────────────

class CopyToSheetDialog(QDialog):
    def __init__(self, document: DocumentData, current_idx: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Copiar bloque a otra hoja')
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self)
        lay.addWidget(_lbl('Selecciona la hoja de destino:'))
        self.lst = QListWidget()
        for i, (s, g) in enumerate(document.flat_sheets()):
            if i == current_idx: continue
            li = sum(1 for j, (_, g2) in enumerate(document.flat_sheets())
                     if j < i and g2.group_id == g.group_id)
            label = f"{g.sheet_number_base + li:02d}: {g.description or g.group_id[:8]}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.lst.addItem(item)
        lay.addWidget(self.lst)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected_sheet_idx(self):
        items = self.lst.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None



# ── Diálogo de grupo ───────────────────────────────────────────────────────

class GroupDialog(QDialog):
    """Crear o editar un grupo de hojas."""
    def __init__(self, document: DocumentData, group=None, parent=None):
        super().__init__(parent)
        self._document = document
        self._group    = group
        editing = group is not None
        self.setWindowTitle('Editar grupo' if editing else 'Nuevo grupo')
        self.setMinimumWidth(420)
        lay = QFormLayout(self)
        lay.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Sistema: combobox editable
        from PyQt6.QtWidgets import QComboBox as _CB
        self.cb_system = _CB()
        self.cb_system.setEditable(True)
        self.cb_system.setInsertPolicy(_CB.InsertPolicy.NoInsert)
        self.cb_system.lineEdit().setPlaceholderText('Seleccionar o escribir nuevo…')
        for s in document.all_systems():
            if s:
                self.cb_system.addItem(s)
        cur_system = getattr(group, 'system', '') if editing else ''
        if cur_system:
            idx = self.cb_system.findText(cur_system)
            if idx >= 0:
                self.cb_system.setCurrentIndex(idx)
            else:
                self.cb_system.setCurrentText(cur_system)
        else:
            self.cb_system.setCurrentIndex(-1)
            self.cb_system.setCurrentText('')

        self.ed_desc = QLineEdit(group.description if editing else '')
        self.ed_kks  = QLineEdit(group.kks         if editing else '')
        self.ed_rev  = QLineEdit(group.revision     if editing else 'A')
        from datetime import date as _date
        _today = _date.today().isoformat()
        self.ed_date = QLineEdit(group.date if (editing and group.date) else _today)

        suggested = document.next_suggested_base()
        self.sp_num = QSpinBox()
        self.sp_num.setRange(1, 9999)
        self.sp_num.setValue(group.sheet_number_base if editing else suggested)

        lay.addRow('Sistema:',     self.cb_system)
        lay.addRow('Descripción:', self.ed_desc)
        lay.addRow('KKS:',         self.ed_kks)
        lay.addRow('Revisión:',    self.ed_rev)
        lay.addRow('Fecha:',       self.ed_date)
        lay.addRow('Nº hoja base:',self.sp_num)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _on_accept(self):
        system = self.cb_system.currentText().strip()
        if not system:
            system = self._document._next_system_name()
            self.cb_system.setCurrentText(system)
        self.accept()

    def _system(self) -> str:
        s = self.cb_system.currentText().strip()
        return s if s else self._document._next_system_name()

    def create_group(self, document: DocumentData, num_slots: int = 23):
        from model import GroupData
        g = GroupData(
            system            = self._system(),
            description       = self.ed_desc.text().strip(),
            kks               = self.ed_kks.text().strip(),
            revision          = self.ed_rev.text().strip() or 'A',
            date              = self.ed_date.text().strip(),
            sheet_number_base = self.sp_num.value(),
        )
        g.add_sheet(num_slots)
        document.groups.append(g)
        return g

    def apply_to_group(self, group):
        group.system            = self._system()
        group.description       = self.ed_desc.text().strip()
        group.kks               = self.ed_kks.text().strip()
        group.revision          = self.ed_rev.text().strip() or 'A'
        group.date              = self.ed_date.text().strip()
        group.sheet_number_base = self.sp_num.value()


# ── Diálogo de índice interactivo ─────────────────────────────────────────

class IndexDialog(QDialog):
    """Lista todas las hojas del documento. Doble clic navega a la hoja."""

    sheet_selected = None  # índice plano seleccionado tras aceptar

    def __init__(self, document, current_flat_idx: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Índice del documento')
        self.setMinimumSize(580, 420)
        lay = QVBoxLayout(self)

        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        from PyQt6.QtCore import Qt as _Qt

        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(['Hoja', 'Sistema', 'KKS', 'Título'])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        self._tbl = tbl

        flat = document.flat_sheets()
        for flat_i, (sheet, group) in enumerate(flat):
            num = document.sheet_ref(flat_i)
            li  = sum(1 for j, (_, g2) in enumerate(flat)
                      if j < flat_i and g2.group_id == group.group_id)
            title = sheet.sheet_title or group.title_for_sheet(li)
            row = tbl.rowCount(); tbl.insertRow(row)
            for col, val in enumerate([f'H{int(num):02d}',
                                       group.system or '',
                                       group.kks or '',
                                       title]):
                item = QTableWidgetItem(val)
                item.setData(_Qt.ItemDataRole.UserRole, flat_i)
                tbl.setItem(row, col, item)
            if flat_i == current_flat_idx:
                tbl.selectRow(row)

        tbl.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(tbl)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText('Ir a hoja')
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_double_click(self, item):
        self.sheet_selected = item.data(__import__('PyQt6.QtCore', fromlist=['Qt']).Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_ok(self):
        rows = self._tbl.selectedItems()
        if rows:
            from PyQt6.QtCore import Qt as _Qt
            self.sheet_selected = rows[0].data(_Qt.ItemDataRole.UserRole)
        self.accept()
