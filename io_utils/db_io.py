"""
io_utils/db_io.py  -  Persistencia SQLite v11.

Arquitectura:
  Abrir   : fichero .sdg -> SQLite :memory:
  En uso  : lectura/escritura sobre la BD en memoria
  Guardar : BD en memoria -> fichero .sdg

Compatibilidad: detecta JSON v10 y migra automaticamente.
"""
from __future__ import annotations
import sqlite3, json, uuid
from pathlib import Path

from model import (
    DocumentData, GroupData, SheetData, TitleBlockData, CoverPageData,
    SlotData, BlockData, PortData, ConnectionData, EndpointRef,
    BranchNodeData, SymbolData, NoteData, TextBoxData,
)

VERSION = 11
_mem = None


# ── BD en memoria ─────────────────────────────────────────────────────────

def get_mem():
    global _mem
    if _mem is None:
        _mem = sqlite3.connect(':memory:', check_same_thread=False)
        _mem.row_factory = sqlite3.Row
        _mem.execute('PRAGMA foreign_keys = ON')
        _create_schema(_mem)
    return _mem


def reset_mem():
    global _mem
    if _mem is not None:
        try: _mem.close()
        except Exception: pass
    _mem = None
    return get_mem()


# ── esquema ───────────────────────────────────────────────────────────────

def _create_schema(con):
    con.executescript("""
CREATE TABLE IF NOT EXISTS document (
    doc_id TEXT PRIMARY KEY, title TEXT DEFAULT '', doc_number TEXT DEFAULT '',
    project TEXT DEFAULT '', plant TEXT DEFAULT '', revision TEXT DEFAULT 'A',
    date TEXT DEFAULT '', company TEXT DEFAULT '', drawn_by TEXT DEFAULT '',
    checked_by TEXT DEFAULT '', approved_by TEXT DEFAULT '',
    logo_path TEXT DEFAULT '', version INTEGER DEFAULT 11);
CREATE TABLE IF NOT EXISTS cover_page (
    doc_id TEXT PRIMARY KEY, show INTEGER DEFAULT 1,
    subtitle TEXT DEFAULT '', description TEXT DEFAULT '',
    logo_path TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL,
    order_idx INTEGER NOT NULL, system TEXT DEFAULT '',
    description TEXT DEFAULT '', kks TEXT DEFAULT '',
    revision TEXT DEFAULT 'A', date TEXT DEFAULT '',
    sheet_number_base INTEGER DEFAULT 10);
CREATE TABLE IF NOT EXISTS sheets (
    sheet_id TEXT PRIMARY KEY, group_id TEXT NOT NULL,
    order_idx INTEGER NOT NULL, num_slots INTEGER DEFAULT 23,
    sheet_name TEXT DEFAULT '', sheet_title TEXT DEFAULT '',
    sheet_number TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    side TEXT NOT NULL, slot_index INTEGER NOT NULL,
    description TEXT DEFAULT '', signal_desc TEXT DEFAULT '',
    kks TEXT DEFAULT '', kks2 TEXT DEFAULT '',
    sub_text TEXT DEFAULT '', signal_type TEXT DEFAULT 'analog');
CREATE TABLE IF NOT EXISTS slot_links (
    link_id TEXT PRIMARY KEY,
    src_slot_id TEXT NOT NULL, dst_slot_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS xsheet_links (
    link_id     TEXT PRIMARY KEY,
    src_slot_id TEXT NOT NULL,
    dst_sheet_id TEXT NOT NULL,
    dst_slot_idx INTEGER NOT NULL,
    dst_side    TEXT NOT NULL DEFAULT 'left');
CREATE TABLE IF NOT EXISTS blocks (
    block_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    type_id TEXT DEFAULT 'CUSTOM',
    x REAL DEFAULT 0, y REAL DEFAULT 0,
    w REAL DEFAULT 0, h REAL DEFAULT 0,
    kks TEXT DEFAULT '', inscription TEXT DEFAULT '',
    label TEXT DEFAULT '', show_type_label INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS block_ports (
    port_id TEXT PRIMARY KEY, block_id TEXT NOT NULL,
    side TEXT NOT NULL, port_index INTEGER NOT NULL,
    name TEXT DEFAULT '', number INTEGER DEFAULT 0,
    signal_type TEXT DEFAULT 'analog', negated INTEGER DEFAULT 0,
    transfer_fn TEXT DEFAULT NULL);
CREATE TABLE IF NOT EXISTS connections (
    conn_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    src_id TEXT NOT NULL, src_kind TEXT NOT NULL,
    src_port_idx INTEGER DEFAULT 0,
    dst_id TEXT NOT NULL, dst_kind TEXT NOT NULL,
    dst_port_idx INTEGER DEFAULT 0,
    signal_type TEXT DEFAULT NULL, sim_value REAL DEFAULT NULL);
CREATE TABLE IF NOT EXISTS branch_nodes (
    branch_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    parent_conn_id TEXT, x REAL DEFAULT 0, y REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS waypoints (
    wp_id TEXT PRIMARY KEY, conn_id TEXT NOT NULL,
    order_idx INTEGER NOT NULL, x REAL DEFAULT 0, y REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS symbols (
    sym_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    sym_type TEXT NOT NULL, port_side TEXT NOT NULL,
    x REAL DEFAULT 0, y REAL DEFAULT 0,
    kks TEXT DEFAULT '', num_slots INTEGER DEFAULT 12);
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    text TEXT DEFAULT '', x REAL DEFAULT 0, y REAL DEFAULT 0,
    font_size_px INTEGER DEFAULT 0, text_width REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS textboxes (
    box_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL,
    text TEXT DEFAULT '', x REAL DEFAULT 0, y REAL DEFAULT 0,
    w REAL DEFAULT 0, h REAL DEFAULT 0,
    font_size_px INTEGER DEFAULT 0, signal_type TEXT DEFAULT 'analog');
CREATE INDEX IF NOT EXISTS idx_groups_doc     ON groups(doc_id);
CREATE INDEX IF NOT EXISTS idx_sheets_group   ON sheets(group_id);
CREATE INDEX IF NOT EXISTS idx_slots_sheet    ON slots(sheet_id);
CREATE INDEX IF NOT EXISTS idx_blocks_sheet   ON blocks(sheet_id);
CREATE INDEX IF NOT EXISTS idx_ports_block    ON block_ports(block_id);
CREATE INDEX IF NOT EXISTS idx_conns_sheet    ON connections(sheet_id);
CREATE INDEX IF NOT EXISTS idx_conns_src      ON connections(src_id);
CREATE INDEX IF NOT EXISTS idx_conns_dst      ON connections(dst_id);
CREATE INDEX IF NOT EXISTS idx_branches_sheet ON branch_nodes(sheet_id);
CREATE INDEX IF NOT EXISTS idx_waypoints_conn ON waypoints(conn_id);
CREATE INDEX IF NOT EXISTS idx_links_src      ON slot_links(src_slot_id);
CREATE INDEX IF NOT EXISTS idx_links_dst      ON slot_links(dst_slot_id);
CREATE INDEX IF NOT EXISTS idx_xlinks_src     ON xsheet_links(src_slot_id);
CREATE INDEX IF NOT EXISTS idx_xlinks_dst     ON xsheet_links(dst_sheet_id);
""")
    try:
        con.execute("""
CREATE VIEW IF NOT EXISTS signal_graph AS
    SELECT conn_id AS edge_id, sheet_id,
           src_id, src_kind, dst_id, dst_kind,
           signal_type, sim_value, 'intra' AS link_type
    FROM connections
    UNION ALL
    SELECT sl.link_id, s.sheet_id,
           sl.src_slot_id, 'slot', sl.dst_slot_id, 'slot',
           s.signal_type, NULL, 'inter'
    FROM slot_links sl JOIN slots s ON sl.src_slot_id = s.slot_id""")
    except Exception:
        pass
    con.commit()


# ── fichero <-> memoria ───────────────────────────────────────────────────

def save_db(path):
    mem  = get_mem()
    path = Path(path)
    if path.exists():
        path.unlink()
    dest = sqlite3.connect(str(path))
    with dest:
        for line in mem.iterdump():
            if line.startswith('CREATE VIEW'):
                continue
            try:
                dest.execute(line)
            except Exception:
                pass
    dest.close()


def _migrate_schema(con):
    """Añade columnas que pueden faltar en documentos guardados con versiones antiguas."""
    migrations = [
        ("notes",     "text_width",      "REAL",    "0"),
        ("groups",    "sheet_number_base","INTEGER", "1"),
    ]
    for table, col, typ, default in migrations:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if col not in cols:
            try:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ} DEFAULT {default}")
            except Exception:
                pass


def load_db(path):
    path = Path(path)
    mem  = reset_mem()
    src  = sqlite3.connect(str(path))
    with mem:
        for line in src.iterdump():
            if line.startswith('CREATE VIEW') or line.startswith('CREATE INDEX'):
                continue
            try:
                mem.execute(line)
            except Exception:
                pass
    src.close()
    _migrate_schema(mem)
    mem.commit()


# ── BD -> modelo Python ───────────────────────────────────────────────────

def load_document():
    """Carga estructura del documento (grupos/hojas). Contenido de hojas: lazy."""
    con = get_mem()
    row = con.execute('SELECT * FROM document LIMIT 1').fetchone()
    if row is None:
        return DocumentData()
    doc_id = row['doc_id']
    tb = TitleBlockData(
        title=row['title'],           doc_number=row['doc_number'],
        project=row['project'],       plant=row['plant'],
        revision=row['revision'],     date=row['date'],
        company=row['company'],       drawn_by=row['drawn_by'],
        checked_by=row['checked_by'], approved_by=row['approved_by'],
        logo_path=row['logo_path'],
    )
    cv_r = con.execute('SELECT * FROM cover_page WHERE doc_id=?', (doc_id,)).fetchone()
    cv = CoverPageData(
        show=bool(cv_r['show']), subtitle=cv_r['subtitle'],
        description=cv_r['description'], logo_path=cv_r['logo_path'],
    ) if cv_r else CoverPageData()
    doc = DocumentData(title_block=tb, cover=cv)
    doc._doc_id = doc_id
    for g_row in con.execute(
            'SELECT * FROM groups WHERE doc_id=? ORDER BY order_idx', (doc_id,)):
        g = GroupData(
            group_id=g_row['group_id'],       system=g_row['system'],
            description=g_row['description'], kks=g_row['kks'],
            revision=g_row['revision'],       date=g_row['date'],
            sheet_number_base=g_row['sheet_number_base'],
        )
        for s_row in con.execute(
                'SELECT * FROM sheets WHERE group_id=? ORDER BY order_idx',
                (g_row['group_id'],)):
            s = SheetData(
                sheet_id=s_row['sheet_id'],     sheet_name=s_row['sheet_name'],
                sheet_title=s_row['sheet_title'], sheet_number=s_row['sheet_number'],
                num_slots=s_row['num_slots'],
            )
            s._loaded = False
            g.sheets.append(s)
        if not g.sheets:
            g.add_sheet(23)
        doc.groups.append(g)
    if not doc.groups or doc.sheet_count() == 0:
        doc.add_group('Nuevo grupo', num_slots=23)
    return doc


def load_sheet_content(sheet):
    """Carga el contenido completo de una hoja (lazy). Llama antes de renderizar."""
    if getattr(sheet, '_loaded', False):
        return
    con = get_mem()
    sid = sheet.sheet_id
    # Slots
    sheet.slots_left = []
    sheet.slots_right = []
    for r in con.execute(
            'SELECT * FROM slots WHERE sheet_id=? ORDER BY slot_index', (sid,)):
        sd = SlotData(
            slot_id=r['slot_id'],       description=r['description'],
            signal_desc=r['signal_desc'], kks=r['kks'],
            kks2=r['kks2'],             sub_text=r['sub_text'],
        )
        for lnk in con.execute(
                'SELECT dst_slot_id FROM slot_links WHERE src_slot_id=?',
                (r['slot_id'],)):
            sd.linked_slots.append(lnk[0])
        if r['side'] == 'left':
            sheet.slots_left.append(sd)
        else:
            sheet.slots_right.append(sd)
    while len(sheet.slots_left)  < sheet.num_slots: sheet.slots_left.append(SlotData())
    while len(sheet.slots_right) < sheet.num_slots: sheet.slots_right.append(SlotData())
    # Bloques
    sheet.blocks = []
    for br in con.execute('SELECT * FROM blocks WHERE sheet_id=?', (sid,)):
        bd = BlockData(
            block_id=br['block_id'], type_id=br['type_id'],
            kks=br['kks'], inscription=br['inscription'], label=br['label'],
            show_type_label=bool(br['show_type_label']),
            x=br['x'], y=br['y'], w=br['w'], h=br['h'],
        )
        for pr in con.execute(
                'SELECT * FROM block_ports WHERE block_id=? ORDER BY port_index',
                (br['block_id'],)):
            pd = PortData(
                port_id=pr['port_id'], name=pr['name'], number=pr['number'],
                side=pr['side'], signal_type=pr['signal_type'],
                negated=bool(pr['negated']),
            )
            (bd.inputs if pr['side'] == 'in' else bd.outputs).append(pd)
        sheet.blocks.append(bd)
    # Conexiones
    sheet.connections = []
    for cr in con.execute('SELECT * FROM connections WHERE sheet_id=?', (sid,)):
        wps = [(r['x'], r['y']) for r in con.execute(
            'SELECT x,y FROM waypoints WHERE conn_id=? ORDER BY order_idx',
            (cr['conn_id'],))]
        sheet.connections.append(ConnectionData(
            conn_id=cr['conn_id'],
            src=EndpointRef(kind=cr['src_kind'], item_id=cr['src_id'],
                            port_idx=cr['src_port_idx']),
            dst=EndpointRef(kind=cr['dst_kind'], item_id=cr['dst_id'],
                            port_idx=cr['dst_port_idx']),
            waypoints=wps,
        ))
    # Branch nodes
    sheet.branch_nodes = [
        BranchNodeData(branch_id=r['branch_id'],
                       parent_conn_id=r['parent_conn_id'] or '',
                       x=r['x'], y=r['y'])
        for r in con.execute('SELECT * FROM branch_nodes WHERE sheet_id=?', (sid,))
    ]
    # Simbolos
    sheet.symbols = [
        SymbolData(sym_id=r['sym_id'], sym_type=r['sym_type'],
                   port_side=r['port_side'], kks=r['kks'], x=r['x'], y=r['y'])
        for r in con.execute('SELECT * FROM symbols WHERE sheet_id=?', (sid,))
    ]
    # Notas
    sheet.notes = [
        NoteData(note_id=r['note_id'], text=r['text'],
                 x=r['x'], y=r['y'], font_size_px=r['font_size_px'],
                 text_width=r['text_width'] if 'text_width' in r.keys() else 0.0)
        for r in con.execute('SELECT * FROM notes WHERE sheet_id=?', (sid,))
    ]
    # Cajas de texto
    sheet.textboxes = [
        TextBoxData(textbox_id=r['box_id'], text=r['text'],
                    x=r['x'], y=r['y'], font_size_px=r['font_size_px'],
                    signal_type=r['signal_type'])
        for r in con.execute('SELECT * FROM textboxes WHERE sheet_id=?', (sid,))
    ]
    sheet._loaded = True


# ── modelo Python -> BD ───────────────────────────────────────────────────

def sync_document(doc):
    """Escribe estructura del documento (sin contenido de hojas)."""
    con    = get_mem()
    doc_id = getattr(doc, '_doc_id', None) or str(uuid.uuid4())
    doc._doc_id = doc_id
    tb = doc.title_block
    cv = doc.cover
    with con:
        con.execute("""
            INSERT OR REPLACE INTO document
              (doc_id,title,doc_number,project,plant,revision,date,
               company,drawn_by,checked_by,approved_by,logo_path,version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, tb.title, tb.doc_number, tb.project, tb.plant,
             tb.revision, tb.date, tb.company, tb.drawn_by,
             tb.checked_by, tb.approved_by, tb.logo_path, VERSION))
        con.execute("""
            INSERT OR REPLACE INTO cover_page
              (doc_id,show,subtitle,description,logo_path)
            VALUES (?,?,?,?,?)""",
            (doc_id, int(cv.show), cv.subtitle, cv.description, cv.logo_path))
        for gi, g in enumerate(doc.groups):
            con.execute("""
                INSERT OR REPLACE INTO groups
                  (group_id,doc_id,order_idx,system,description,kks,
                   revision,date,sheet_number_base)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (g.group_id, doc_id, gi, g.system, g.description,
                 g.kks, g.revision, g.date, g.sheet_number_base))
            for si, s in enumerate(g.sheets):
                con.execute("""
                    INSERT OR REPLACE INTO sheets
                      (sheet_id,group_id,order_idx,num_slots,
                       sheet_name,sheet_title,sheet_number)
                    VALUES (?,?,?,?,?,?,?)""",
                    (s.sheet_id, g.group_id, si, s.num_slots,
                     s.sheet_name, s.sheet_title, s.sheet_number))


def sync_sheet(sheet):
    """Sincroniza contenido completo de una hoja a la BD (borra y reescribe)."""
    con = get_mem()
    sid = sheet.sheet_id
    with con:
        # Borrar datos previos respetando dependencias
        old_conns = [r[0] for r in con.execute(
            'SELECT conn_id FROM connections WHERE sheet_id=?', (sid,))]
        if old_conns:
            ph = ','.join('?' * len(old_conns))
            con.execute(f'DELETE FROM waypoints WHERE conn_id IN ({ph})', old_conns)
        old_blocks = [r[0] for r in con.execute(
            'SELECT block_id FROM blocks WHERE sheet_id=?', (sid,))]
        if old_blocks:
            ph = ','.join('?' * len(old_blocks))
            con.execute(f'DELETE FROM block_ports WHERE block_id IN ({ph})', old_blocks)
        for tbl in ('slots','blocks','connections',
                    'branch_nodes','symbols','notes','textboxes'):
            con.execute(f'DELETE FROM {tbl} WHERE sheet_id=?', (sid,))
        # Slots
        for side, lst in (('left', sheet.slots_left), ('right', sheet.slots_right)):
            for idx, sd in enumerate(lst):
                con.execute("""
                    INSERT INTO slots
                      (slot_id,sheet_id,side,slot_index,description,
                       signal_desc,kks,kks2,sub_text)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (sd.slot_id, sid, side, idx, sd.description,
                     sd.signal_desc, sd.kks, sd.kks2, sd.sub_text))
        # Bloques
        for bd in sheet.blocks:
            con.execute("""
                INSERT INTO blocks
                  (block_id,sheet_id,type_id,x,y,w,h,
                   kks,inscription,label,show_type_label)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (bd.block_id, sid, bd.type_id, bd.x, bd.y, bd.w, bd.h,
                 bd.kks, bd.inscription, bd.label,
                 int(getattr(bd, 'show_type_label', False))))
            for pi, pd in enumerate(bd.inputs):
                con.execute("""
                    INSERT INTO block_ports
                      (port_id,block_id,side,port_index,name,number,
                       signal_type,negated)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (pd.port_id, bd.block_id, 'in', pi, pd.name,
                     pd.number, pd.signal_type, int(pd.negated)))
            for pi, pd in enumerate(bd.outputs):
                con.execute("""
                    INSERT INTO block_ports
                      (port_id,block_id,side,port_index,name,number,
                       signal_type,negated)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (pd.port_id, bd.block_id, 'out', pi, pd.name,
                     pd.number, pd.signal_type, int(pd.negated)))
        # Conexiones
        for cd in sheet.connections:
            con.execute("""
                INSERT INTO connections
                  (conn_id,sheet_id,src_id,src_kind,src_port_idx,
                   dst_id,dst_kind,dst_port_idx)
                VALUES (?,?,?,?,?,?,?,?)""",
                (cd.conn_id, sid,
                 cd.src.item_id, cd.src.kind, cd.src.port_idx,
                 cd.dst.item_id, cd.dst.kind, cd.dst.port_idx))
            for wi, (wx, wy) in enumerate(cd.waypoints):
                con.execute("""
                    INSERT INTO waypoints (wp_id,conn_id,order_idx,x,y)
                    VALUES (?,?,?,?,?)""",
                    (str(uuid.uuid4()), cd.conn_id, wi, wx, wy))
        # Branch nodes
        for bnd in getattr(sheet, 'branch_nodes', []):
            con.execute("""
                INSERT INTO branch_nodes (branch_id,sheet_id,parent_conn_id,x,y)
                VALUES (?,?,?,?,?)""",
                (bnd.branch_id, sid, bnd.parent_conn_id, bnd.x, bnd.y))
        # Simbolos
        for sy in sheet.symbols:
            con.execute("""
                INSERT INTO symbols
                  (sym_id,sheet_id,sym_type,port_side,x,y,kks,num_slots)
                VALUES (?,?,?,?,?,?,?,?)""",
                (sy.sym_id, sid, sy.sym_type, sy.port_side,
                 sy.x, sy.y, sy.kks, getattr(sy, 'num_slots', 12)))
        # Notas
        for nd in sheet.notes:
            con.execute("""
                INSERT INTO notes (note_id,sheet_id,text,x,y,font_size_px,text_width)
                VALUES (?,?,?,?,?,?,?)""",
                (nd.note_id, sid, nd.text, nd.x, nd.y,
                 getattr(nd, 'font_size_px', 0),
                 getattr(nd, 'text_width', 0.0)))
        # Cajas de texto
        for tb in getattr(sheet, 'textboxes', []):
            con.execute("""
                INSERT INTO textboxes
                  (box_id,sheet_id,text,x,y,w,h,font_size_px,signal_type)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (tb.textbox_id, sid, tb.text, tb.x, tb.y,
                 getattr(tb, 'w', 0), getattr(tb, 'h', 0),
                 getattr(tb, 'font_size_px', 0),
                 getattr(tb, 'signal_type', 'analog')))
    sheet._loaded = True


def init_from_document(doc):
    """Vuelca DocumentData completo a BD en memoria (nuevo doc o migracion JSON)."""
    reset_mem()
    sync_document(doc)
    for g in doc.groups:
        for s in g.sheets:
            if getattr(s, '_loaded', True):
                sync_sheet(s)


# ── puntos de entrada publicos ────────────────────────────────────────────

def sync_xsheet_links(doc):
    """Persiste en BD todos los enlaces cruzados entre conectores del documento.

    Para cada slot que tenga linked_sheets/linked_slots, escribe en xsheet_links:
      (src_slot_id, dst_sheet_id, dst_slot_idx, dst_side)
    usando los sheet_ids reales del documento como clave estable.

    Borra y reescribe toda la tabla para garantizar consistencia.
    Requiere que todas las hojas con links estén cargadas (_loaded=True).
    """
    con  = get_mem()
    flat = doc.flat_sheets()

    # Mapa sheet_id → SheetData para resolver links inversos
    sid_to_sheet = {s.sheet_id: s for s, _ in flat}

    with con:
        con.execute('DELETE FROM xsheet_links')
        for fi, (sheet, _) in enumerate(flat):
            for side, slots in (('right', sheet.slots_right),
                                ('left',  sheet.slots_left)):
                for slot_idx, sd in enumerate(slots):
                    if not sd.linked_sheets:
                        continue
                    for dst_fi, dst_si in zip(sd.linked_sheets, sd.linked_slots):
                        if not (0 <= dst_fi < len(flat)):
                            continue
                        dst_sheet, _ = flat[dst_fi]
                        import uuid as _uuid
                        con.execute(
                            'INSERT INTO xsheet_links '
                            '(link_id, src_slot_id, dst_sheet_id, dst_slot_idx, dst_side) '
                            'VALUES (?,?,?,?,?)',
                            (str(_uuid.uuid4()), sd.slot_id,
                             dst_sheet.sheet_id, dst_si,
                             'left' if side == 'right' else 'right'))


def resolve_xsheet_links(doc):
    """Reconstruye linked_sheets/linked_slots en todos los slots del documento
    leyendo desde xsheet_links.

    Requiere que todos los slots estén cargados (se fuerza load_sheet_content).
    Usa sheet_id como clave estable, independientemente de cambios en flat_idx.
    """
    con  = get_mem()
    flat = doc.flat_sheets()

    # Asegurar que todas las hojas están cargadas
    for sheet, _ in flat:
        if not getattr(sheet, '_loaded', False):
            try:
                load_sheet_content(sheet)
            except Exception:
                pass

    # Mapa sheet_id → flat_idx (post-movimiento)
    sid_to_fi = {s.sheet_id: i for i, (s, _) in enumerate(flat)}

    # Mapa slot_id → SlotData (para encontrar el slot origen)
    slot_by_id: dict = {}
    for sheet, _ in flat:
        for sd in sheet.slots_left + sheet.slots_right:
            slot_by_id[sd.slot_id] = sd

    # Limpiar links existentes en memoria antes de reconstruir
    for sheet, _ in flat:
        for sd in sheet.slots_left + sheet.slots_right:
            sd.linked_sheets = []
            sd.linked_slots  = []

    # Reconstruir desde xsheet_links
    rows = con.execute(
        'SELECT src_slot_id, dst_sheet_id, dst_slot_idx FROM xsheet_links'
    ).fetchall()

    for src_slot_id, dst_sheet_id, dst_slot_idx in rows:
        src_sd = slot_by_id.get(src_slot_id)
        if src_sd is None:
            continue
        dst_fi = sid_to_fi.get(dst_sheet_id)
        if dst_fi is None:
            continue
        if dst_fi not in src_sd.linked_sheets:
            src_sd.linked_sheets.append(dst_fi)
            src_sd.linked_slots.append(dst_slot_idx)


def resolve_linked_sheets(doc):
    """Reconstruye linked_sheets/linked_slots en TODOS los slots del documento.

    Uso: tras operaciones estructurales (clonar, mover, abrir, rollback) que
    invalidan todos los flat_idx. Fuerza carga de hojas no visitadas.
    """
    con  = get_mem()
    flat = doc.flat_sheets()

    # Cargar hojas que no estén en memoria
    for sheet, _ in flat:
        if not getattr(sheet, '_loaded', False):
            try:
                load_sheet_content(sheet)
            except Exception:
                pass

    # Mapa slot_id → (flat_idx, slot_idx)  y  slot_id → SlotData
    sid_to_ref:  dict = {}
    slot_by_sid: dict = {}
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_left):
            sid_to_ref[sd.slot_id]  = (fi, si)
            slot_by_sid[sd.slot_id] = sd
        for si, sd in enumerate(sheet.slots_right):
            sid_to_ref[sd.slot_id]  = (fi, si)
            slot_by_sid[sd.slot_id] = sd

    # Limpiar y reconstruir desde slot_links
    for sd in slot_by_sid.values():
        sd.linked_sheets = []
        sd.linked_slots  = []

    rows = con.execute('SELECT src_slot_id, dst_slot_id FROM slot_links').fetchall()
    for row in rows:
        src_sid = row['src_slot_id']
        dst_sid = row['dst_slot_id']
        if src_sid == dst_sid:
            continue
        src_ref = sid_to_ref.get(src_sid)
        dst_ref = sid_to_ref.get(dst_sid)
        if src_ref is None or dst_ref is None:
            continue
        src_fi, src_si = src_ref
        dst_fi, dst_si = dst_ref
        src_sd = slot_by_sid[src_sid]
        dst_sd = slot_by_sid[dst_sid]
        if dst_fi not in src_sd.linked_sheets:
            src_sd.linked_sheets.append(dst_fi)
            src_sd.linked_slots.append(dst_si)
        if src_fi not in dst_sd.linked_sheets:
            dst_sd.linked_sheets.append(src_fi)
            dst_sd.linked_slots.append(src_si)


def resolve_sheet_links(doc, sheet):
    """Reconstruye linked_sheets/linked_slots solo para los slots de una hoja.

    Uso: en navegación, cuando se carga una hoja lazy. Los flat_idx del resto
    del documento ya son correctos — solo hay que resolver esta hoja concreta.
    No toca ninguna otra hoja. O(slots_de_hoja × links_por_slot).
    """
    con  = get_mem()
    flat = doc.flat_sheets()

    # Encontrar el flat_idx de esta hoja
    fi = next((i for i, (s, _) in enumerate(flat) if s is sheet), None)
    if fi is None:
        return

    # Construir mapa slot_id → (flat_idx, slot_idx) para TODO el documento
    # (necesitamos saber a qué hoja apunta cada dst_slot_id)
    # Solo construimos el mapa de slots cargados; los no cargados no tienen links aún.
    sid_to_ref:  dict = {}
    slot_by_sid: dict = {}
    for fj, (s, _) in enumerate(flat):
        if not getattr(s, '_loaded', False):
            continue
        for sj, sd in enumerate(s.slots_left):
            sid_to_ref[sd.slot_id]  = (fj, sj)
            slot_by_sid[sd.slot_id] = sd
        for sj, sd in enumerate(s.slots_right):
            sid_to_ref[sd.slot_id]  = (fj, sj)
            slot_by_sid[sd.slot_id] = sd

    # Recopilar los slot_ids de esta hoja
    this_sids = set()
    for sd in sheet.slots_left + sheet.slots_right:
        sd.linked_sheets = []
        sd.linked_slots  = []
        this_sids.add(sd.slot_id)
        slot_by_sid[sd.slot_id] = sd

    if not this_sids:
        return

    # Buscar en slot_links solo las filas que involucren a esta hoja
    ph = ','.join('?' * len(this_sids))
    sids = list(this_sids)
    rows = con.execute(
        f'SELECT src_slot_id, dst_slot_id FROM slot_links '
        f'WHERE src_slot_id IN ({ph}) OR dst_slot_id IN ({ph})',
        sids + sids).fetchall()

    for row in rows:
        src_sid = row['src_slot_id']
        dst_sid = row['dst_slot_id']
        if src_sid == dst_sid:
            continue
        src_ref = sid_to_ref.get(src_sid)
        dst_ref = sid_to_ref.get(dst_sid)
        if src_ref is None or dst_ref is None:
            continue
        src_fi, src_si = src_ref
        dst_fi, dst_si = dst_ref
        src_sd = slot_by_sid.get(src_sid)
        dst_sd = slot_by_sid.get(dst_sid)
        if src_sd and dst_fi not in src_sd.linked_sheets:
            src_sd.linked_sheets.append(dst_fi)
            src_sd.linked_slots.append(dst_si)
        if dst_sd and src_fi not in dst_sd.linked_sheets:
            dst_sd.linked_sheets.append(src_fi)
            dst_sd.linked_slots.append(src_si)


def load_document_from_path(path):
    """Abre .sdg (JSON v10 o SQLite v11). Migra automaticamente."""
    path = Path(path)
    raw  = path.read_bytes()
    is_json = raw[:20].lstrip(b'\xef\xbb\xbf \t\r\n').startswith(b'{')
    if is_json:
        from io_utils.json_io import _dict_to_doc
        import json as _json
        doc = _dict_to_doc(_json.loads(raw.decode('utf-8')))
        for g in doc.groups:
            for s in g.sheets:
                s._loaded = True
        init_from_document(doc)
    else:
        load_db(path)
        doc = load_document()
    return doc


def save_document_to_path(doc, path):
    """Sincroniza documento a BD y vuelca al fichero."""
    sync_document(doc)
    save_db(Path(path))
