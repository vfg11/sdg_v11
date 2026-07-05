"""
io_utils/json_io.py — Serialización JSON del documento (v10).
Jerarquía: DocumentData → GroupData → SheetData
"""
from __future__ import annotations
import json
from pathlib import Path
from model import (DocumentData, GroupData, SheetData, TitleBlockData,
                   CoverPageData, SlotData, BlockData, PortData,
                   ConnectionData, EndpointRef, SymbolData, NoteData, TextBoxData)

VERSION = 10


def save_json(document: DocumentData, path: str | Path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(_doc_to_dict(document), f, ensure_ascii=False, indent=2)


def load_json(path: str | Path) -> DocumentData:
    with open(path, 'r', encoding='utf-8') as f:
        return _dict_to_doc(json.load(f))


# ── serialización ──────────────────────────────────────────────────────────

def _doc_to_dict(doc: DocumentData) -> dict:
    tb = doc.title_block
    cv = doc.cover
    return {
        'version': VERSION,
        'title_block': {
            'title': tb.title, 'doc_number': tb.doc_number,
            'project': tb.project, 'plant': tb.plant,
            'revision': tb.revision, 'date': tb.date,
            'company': tb.company, 'drawn_by': tb.drawn_by,
            'checked_by': tb.checked_by, 'approved_by': tb.approved_by,
            'logo_path': tb.logo_path,
        },
        'cover': {
            'show': cv.show, 'subtitle': cv.subtitle,
            'description': cv.description, 'logo_path': cv.logo_path,
        },
        'groups':  [_group_to_dict(g) for g in doc.groups],
        'library': _library_to_list(),
    }


def _group_to_dict(g: GroupData) -> dict:
    return {
        'group_id':          g.group_id,
        'system':            getattr(g, 'system', ''),
        'description':       g.description,
        'kks':               g.kks,
        'revision':          g.revision,
        'date':              g.date,
        'sheet_number_base': g.sheet_number_base,
        'sheets':            [_sheet_to_dict(s) for s in g.sheets],
    }


def _sheet_to_dict(s: SheetData) -> dict:
    return {
        'sheet_id':     s.sheet_id,
        'sheet_name':   s.sheet_name,
        'sheet_title':  s.sheet_title,
        'sheet_number': s.sheet_number,
        'num_slots':    s.num_slots,
        'slots_left':   [_slot(sl) for sl in s.slots_left],
        'slots_right':  [_slot(sl) for sl in s.slots_right],
        'blocks':       [_block(b) for b in s.blocks],
        'connections':  [_conn(c)  for c in s.connections],
        'branch_nodes': [{'branch_id': bn.branch_id,
                          'parent_conn_id': bn.parent_conn_id,
                          'x': bn.x, 'y': bn.y}
                         for bn in getattr(s, 'branch_nodes', [])],
        'symbols':      [_symbol(sy) for sy in s.symbols],
        'notes':        [_note(n)   for n in s.notes],
        'textboxes':    [_textbox(tb) for tb in getattr(s, 'textboxes', [])],
    }


def _slot(s: SlotData) -> dict:
    return {
        'slot_id':       s.slot_id,
        'description':   s.description,
        'signal_desc':   s.signal_desc,
        'kks':           s.kks,
        'kks2':          s.kks2,
        'sub_text':      s.sub_text,
        'linked_sheets': s.linked_sheets,
        'linked_slots':  s.linked_slots,
    }


def _block(b: BlockData) -> dict:
    return {
        'block_id':        b.block_id,
        'type_id':         b.type_id,
        'kks':             b.kks,
        'label':           b.label,
        'inscription':     b.inscription,
        'show_type_label': getattr(b, 'show_type_label', False),
        'x': b.x, 'y': b.y, 'w': b.w, 'h': b.h,
        'inputs':  [{'name': p.name, 'number': p.number,
                     'signal_type': getattr(p, 'signal_type', 'analog'),
                     'negated':     getattr(p, 'negated', False)}
                    for p in b.inputs],
        'outputs': [{'name': p.name, 'number': p.number,
                     'signal_type': getattr(p, 'signal_type', 'analog'),
                     'negated':     getattr(p, 'negated', False)}
                    for p in b.outputs],
    }


def _symbol(s: SymbolData) -> dict:
    return {
        'sym_id': s.sym_id, 'sym_type': s.sym_type,
        'port_side': s.port_side, 'kks': s.kks,
        'x': s.x, 'y': s.y,
    }


def _note(n: NoteData) -> dict:
    return {
        'note_id':      n.note_id, 'text': n.text,
        'font_size_px': getattr(n, 'font_size_px', 0),
        'x': n.x, 'y': n.y,
    }


def _textbox(tb) -> dict:
    return {
        'textbox_id':   tb.textbox_id, 'text': tb.text,
        'font_size_px': getattr(tb, 'font_size_px', 0),
        'signal_type':  getattr(tb, 'signal_type', 'analog'),
        'x': tb.x, 'y': tb.y,
    }


def _conn(c: ConnectionData) -> dict:
    def ep(e): return {'kind': e.kind, 'item_id': e.item_id, 'port_idx': e.port_idx}
    return {'conn_id': c.conn_id or '', 'src': ep(c.src), 'dst': ep(c.dst),
            'waypoints': list(c.waypoints)}


def _library_to_list() -> list:
    from model import BLOCK_LIBRARY
    result = []
    for bt in BLOCK_LIBRARY:
        result.append({
            'type_id':       bt.type_id,
            'name':          bt.name,
            'category':      bt.category,
            'has_kks':       bt.has_kks,
            'default_ins':   bt.default_ins,
            'default_outs':  bt.default_outs,
            'color':         bt.color,
            'description':   bt.description,
            'port_type':     bt.port_type,
            'in_names':      list(bt.in_names),
            'out_names':     list(bt.out_names),
            'width_mm':      getattr(bt, 'width_mm', 20),
            'inscription':   getattr(bt, 'inscription', ''),
            'extensible_in': getattr(bt, 'extensible_in', True),
            'extensible_out':getattr(bt, 'extensible_out', True),
            'in_types':      list(getattr(bt, 'in_types', ())),
            'out_types':     list(getattr(bt, 'out_types', ())),
        })
    return result


# ── deserialización ────────────────────────────────────────────────────────

def _dict_to_doc(d: dict) -> DocumentData:
    tb_d = d.get('title_block', {})
    tb   = TitleBlockData(
        title=tb_d.get('title',''), doc_number=tb_d.get('doc_number',''),
        project=tb_d.get('project',''), plant=tb_d.get('plant',''),
        revision=tb_d.get('revision','A'), date=tb_d.get('date',''),
        company=tb_d.get('company',''), drawn_by=tb_d.get('drawn_by',''),
        checked_by=tb_d.get('checked_by',''), approved_by=tb_d.get('approved_by',''),
        logo_path=tb_d.get('logo_path',''),
    )
    cv_d = d.get('cover', {})
    cv   = CoverPageData(
        show=cv_d.get('show', True), subtitle=cv_d.get('subtitle',''),
        description=cv_d.get('description',''), logo_path=cv_d.get('logo_path',''),
    )
    doc = DocumentData(title_block=tb, cover=cv)

    # Versión 10: grupos
    if 'groups' in d:
        for gd in d['groups']:
            doc.groups.append(_dict_to_group(gd))
    # Migración desde v9 (sin grupos): envolver hojas en un grupo por defecto
    elif 'sheets' in d:
        g = GroupData(description='Grupo 1', sheet_number_base=1)
        for sd in d.get('sheets', []):
            g.sheets.append(_dict_to_sheet(sd))
        if not g.sheets:
            g.add_sheet(23)
        doc.groups.append(g)

    if not doc.groups or doc.sheet_count() == 0:
        doc.add_group('Nuevo grupo', num_slots=23)

    lib_data = d.get('library', [])
    if lib_data:
        _restore_library(lib_data)

    return doc


def _dict_to_group(d: dict) -> GroupData:
    g = GroupData(
        group_id          = d.get('group_id', ''),
        system            = d.get('system', ''),
        description       = d.get('description', ''),
        kks               = d.get('kks', ''),
        revision          = d.get('revision', 'A'),
        date              = d.get('date', ''),
        sheet_number_base = d.get('sheet_number_base', 1),
    )
    for sd in d.get('sheets', []):
        g.sheets.append(_dict_to_sheet(sd))
    if not g.sheets:
        g.add_sheet(23)
    return g


def _dict_to_sheet(d: dict) -> SheetData:
    s = SheetData(
        sheet_id     = d.get('sheet_id', ''),
        sheet_name   = d.get('sheet_name', ''),
        sheet_title  = d.get('sheet_title', ''),
        sheet_number = d.get('sheet_number', ''),
        num_slots    = d.get('num_slots', 23),
    )
    s.slots_left  = [_dict_to_slot(x) for x in d.get('slots_left', [])]
    s.slots_right = [_dict_to_slot(x) for x in d.get('slots_right', [])]
    while len(s.slots_left)  < s.num_slots: s.slots_left.append(SlotData())
    while len(s.slots_right) < s.num_slots: s.slots_right.append(SlotData())
    s.blocks      = [_dict_to_block(b) for b in d.get('blocks', [])]
    s.connections = [_dict_to_conn(c)  for c in d.get('connections', [])]
    s.symbols     = [_dict_to_symbol(sy) for sy in d.get('symbols', [])]
    # Branch nodes (multi-conexiones)
    from model import BranchNodeData
    s.branch_nodes = [BranchNodeData(
        branch_id=bn.get('branch_id', ''),
        parent_conn_id=bn.get('parent_conn_id', ''),
        x=bn.get('x', 0), y=bn.get('y', 0),
    ) for bn in d.get('branch_nodes', [])]
    s.notes       = [_dict_to_note(n)    for n in d.get('notes', [])]
    s.textboxes   = [TextBoxData(
                        textbox_id   = tb.get('textbox_id', ''),
                        text         = tb.get('text', 'Texto'),
                        x=tb.get('x', 0), y=tb.get('y', 0),
                        font_size_px = tb.get('font_size_px', 0),
                        signal_type  = tb.get('signal_type', 'analog'),
                    ) for tb in d.get('textboxes', [])]
    return s


def _dict_to_slot(d: dict) -> SlotData:
    sd = SlotData(
        slot_id=d.get('slot_id',''), description=d.get('description',''),
        signal_desc=d.get('signal_desc',''), kks=d.get('kks',''),
        kks2=d.get('kks2',''), sub_text=d.get('sub_text',''),
        linked_sheet=d.get('linked_sheet',-1), linked_slot=d.get('linked_slot',-1),
    )
    if 'linked_sheets' in d:
        sd.linked_sheets = list(d['linked_sheets'])
        sd.linked_slots  = list(d['linked_slots'])
    return sd


def _dict_to_block(d: dict) -> BlockData:
    bd = BlockData(
        block_id    = d.get('block_id',''),
        type_id     = d.get('type_id','CUSTOM'),
        kks         = d.get('kks',''), label=d.get('label',''),
        inscription = d.get('inscription', ''),
        x=d['x'], y=d['y'], w=d.get('w',0), h=d.get('h',0),
        inputs  = [PortData(name=p['name'],number=p['number'],side='in',
                             signal_type=p.get('signal_type','analog'),
                             negated=p.get('negated',False))
                   for p in d.get('inputs',[])],
        outputs = [PortData(name=p['name'],number=p['number'],side='out',
                            signal_type=p.get('signal_type','analog'),
                            negated=p.get('negated',False))
                   for p in d.get('outputs',[])],
    )
    bd.show_type_label = d.get('show_type_label', False)
    return bd


def _dict_to_symbol(d: dict) -> SymbolData:
    return SymbolData(
        sym_id=d.get('sym_id',''), sym_type=d.get('sym_type','CIRCLE'),
        port_side=d.get('port_side','out'), kks=d.get('kks',''),
        x=d.get('x',0), y=d.get('y',0),
    )


def _dict_to_note(d: dict) -> NoteData:
    nd = NoteData(note_id=d.get('note_id',''), text=d.get('text',''),
                  x=d.get('x',0), y=d.get('y',0))
    nd.font_size_px = d.get('font_size_px', 0)
    return nd


def _dict_to_conn(d: dict) -> ConnectionData:
    def ep(e): return EndpointRef(kind=e['kind'],item_id=e['item_id'],
                                  port_idx=e.get('port_idx',0))
    return ConnectionData(
        conn_id=d.get('conn_id',''), src=ep(d['src']), dst=ep(d['dst']),
        waypoints=[tuple(wp) for wp in d.get('waypoints',[])],
    )


def _restore_library(lib_data: list):
    import model
    from model import BlockType
    new_types = []
    for d in lib_data:
        bt = BlockType(
            type_id=d['type_id'], name=d.get('name', d['type_id']),
            category=d.get('category','Usuario'), has_kks=d.get('has_kks',True),
            default_ins=d.get('default_ins',0), default_outs=d.get('default_outs',0),
            color=d.get('color','#E8F0FE'), description=d.get('description',''),
            port_type=d.get('port_type','analog'),
            in_names=tuple(d.get('in_names',[])), out_names=tuple(d.get('out_names',[])),
            width_mm=d.get('width_mm',20), inscription=d.get('inscription',''),
            extensible_in=d.get('extensible_in',True), extensible_out=d.get('extensible_out',True),
            in_types=tuple(d.get('in_types',[])), out_types=tuple(d.get('out_types',[])),
        )
        new_types.append(bt)
    model.BLOCK_LIBRARY.clear(); model.BLOCK_LIBRARY.extend(new_types)
    model.LIBRARY_BY_ID.clear(); model.LIBRARY_BY_ID.update({bt.type_id: bt for bt in new_types})
    model.LIBRARY_CATEGORIES.clear()
    model.LIBRARY_CATEGORIES.extend(sorted({bt.category for bt in new_types}))
