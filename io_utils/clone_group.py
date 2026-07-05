"""
io_utils/clone_group.py — Clonar un grupo completo en la BD SQLite en memoria.

Operaciones:
  clone_group(doc, src_group_idx, insert_before_group_idx, rules)
      Clona el grupo src en posición insert_before_group_idx,
      aplica las reglas de sustitución de texto y recalcula todos
      los slot_links internos + auto-link KKS del documento.

  apply_kks_autolink(doc)
      Recorre todo el documento y, para cada slot SALIDA cuya clave
      kks+kks2 coincide con la de un slot ENTRADA, añade el link
      si no existe ya. Coexiste con los links manuales.

  validate_rules(rules) → list[str]
      Comprueba coherencia de las reglas. Devuelve lista de errores
      (vacía si todo OK).
"""
from __future__ import annotations
import re
import uuid
from io_utils.db_io import get_mem


# ── Validación de reglas ────────────────────────────────────────────────────

def validate_rules(rules: list[tuple[str, str]]) -> list[str]:
    """
    rules: lista de (patron, reemplazo). Cadenas vacías en ambos = fila vacía, se ignora.
    Devuelve lista de strings de error.
    """
    errors = []
    for i, (pat, rep) in enumerate(rules):
        if not pat and not rep:
            continue
        if not pat:
            errors.append(f"Fila {i+1}: patrón vacío con reemplazo '{rep}'.")
            continue
        # Contar wildcards
        n_star_p = pat.count('*')
        n_q_p    = pat.count('?')
        n_star_r = rep.count('*')
        n_q_r    = rep.count('?')
        if n_star_r > n_star_p:
            errors.append(
                f"Fila {i+1}: el reemplazo tiene más '*' ({n_star_r}) que el patrón ({n_star_p}).")
        if n_q_r > n_q_p:
            errors.append(
                f"Fila {i+1}: el reemplazo tiene más '?' ({n_q_r}) que el patrón ({n_q_p}).")
        # Comprobar que el patrón compila como regex
        try:
            _pattern_to_regex(pat)
        except re.error as e:
            errors.append(f"Fila {i+1}: patrón inválido — {e}")
    return errors


# ── Motor de sustitución wildcard ───────────────────────────────────────────

def _pattern_to_regex(pat: str) -> re.Pattern:
    """Convierte patrón con * y ? a regex con grupos de captura."""
    parts = re.split(r'(\*|\?)', pat)
    rx = ''
    for p in parts:
        if p == '*':
            rx += '(.*?)'
        elif p == '?':
            rx += '(.)'
        else:
            rx += re.escape(p)
    return re.compile('^' + rx + '$', re.IGNORECASE)


def _apply_rule(text: str, pat: str, rep: str) -> str:
    """Aplica una regla (pat→rep) a text. Devuelve el texto transformado."""
    if not pat or not text:
        return text
    regex = _pattern_to_regex(pat)
    m = regex.match(text)
    if not m:
        return text
    groups = list(m.groups())  # capturas posicionales de * y ?

    # Reconstruir reemplazo sustituyendo * y ? por sus capturas en orden
    result = ''
    g_idx  = 0
    for ch in rep:
        if ch in ('*', '?'):
            if g_idx < len(groups):
                result += groups[g_idx]
                g_idx  += 1
            # si faltan grupos simplemente se omite
        else:
            result += ch
    return result


def apply_rules(text: str, rules: list[tuple[str, str]]) -> str:
    """Aplica todas las reglas en orden."""
    for pat, rep in rules:
        if pat:
            text = _apply_rule(text, pat, rep)
    return text


# ── Auto-link KKS ───────────────────────────────────────────────────────────

def clear_all_xsheet_links(doc):
    """Elimina todos los enlaces cruzados entre conectores del documento.

    Borra linked_sheets, linked_slots y sub_text de todos los slots de todas
    las hojas. Se usa antes de rebuild_xsheet_links para partir de cero.
    Las hojas no cargadas se cargan primero para que el borrado sea completo.
    """
    for sheet, _ in doc.flat_sheets():
        if not getattr(sheet, '_loaded', False):
            try:
                from io_utils.db_io import load_sheet_content
                load_sheet_content(sheet)
            except Exception:
                pass
        for sd in sheet.slots_left + sheet.slots_right:
            sd.linked_sheets = []
            sd.linked_slots  = []
            sd.sub_text      = ''


def rebuild_xsheet_links(doc) -> int:
    """Limpia todos los enlaces cruzados y los reconstruye desde cero
    usando la regla KKS: salida.kks+kks2 == entrada.kks+kks2 → enlace.

    Reconstruye también los sub_text de salidas y entradas enlazadas.
    Devuelve el número de enlaces creados.
    """
    clear_all_xsheet_links(doc)
    flat      = doc.flat_sheets()
    new_links = 0

    # Índice de salidas por clave KKS → [(flat_idx, slot_idx, SlotData)]
    outputs: dict[str, list] = {}
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_right):
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if key:
                outputs.setdefault(key, []).append((fi, si, sd))

    # Para cada entrada, enlazar con la salida de clave coincidente
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_left):
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if not key:
                continue
            for src_fi, src_si, src_sd in outputs.get(key, []):
                if src_fi == fi and src_si == si:
                    continue
                src_sd.add_link(fi, si)
                sd.linked_sheets.append(src_fi)
                sd.linked_slots.append(src_si)
                new_links += 1

    # Reconstruir sub_texts
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_right):
            if sd.linked_sheets:
                sd.rebuild_sub_text(doc, 'right', fi, si)
        for si, sd in enumerate(sheet.slots_left):
            if sd.linked_sheets:
                sd.rebuild_sub_text(doc, 'left', fi, si)

    # Persistir slots actualizados a BD y reconstruir slot_links cruzados
    from io_utils.db_io import sync_sheet as _sync_sheet, get_mem as _get_mem
    import uuid as _uuid

    con = _get_mem()

    # Recopilar mapa slot_id → SlotData para resolver los dst slot_ids
    slot_by_id: dict = {}
    for sheet, _ in flat:
        for sd in sheet.slots_left + sheet.slots_right:
            slot_by_id[sd.slot_id] = sd

    # Mapa flat_idx → {side: {slot_idx: slot_id}}
    # y mapa inverso slot_id → (flat_idx, side, slot_idx) para lookup
    sid_to_ref: dict = {}   # slot_id → (flat_idx, side, slot_idx)
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_left):
            sid_to_ref[sd.slot_id] = (fi, 'left', si)
        for si, sd in enumerate(sheet.slots_right):
            sid_to_ref[sd.slot_id] = (fi, 'right', si)

    with con:
        # Limpiar slot_links cruzados que ya no sean válidos
        # (mantener los intra-sheet que gestiona otro código)
        # Identificar todos los slot_ids activos en este doc
        all_sids = set(sid_to_ref.keys())
        old = con.execute('SELECT link_id, src_slot_id, dst_slot_id FROM slot_links').fetchall()
        for row in old:
            if row['src_slot_id'] in all_sids and row['dst_slot_id'] in all_sids:
                src_ref = sid_to_ref[row['src_slot_id']]
                dst_ref = sid_to_ref[row['dst_slot_id']]
                if src_ref[0] != dst_ref[0]:   # cross-sheet → borrar, se reescribirá
                    con.execute('DELETE FROM slot_links WHERE link_id=?', (row['link_id'],))

        # Escribir los nuevos links cruzados
        for fi, (sheet, _) in enumerate(flat):
            for si, src_sd in enumerate(sheet.slots_right):
                for dst_fi, dst_si in zip(src_sd.linked_sheets, src_sd.linked_slots):
                    if dst_fi == fi:
                        continue
                    if not (0 <= dst_fi < len(flat)):
                        continue
                    dst_sheet, _ = flat[dst_fi]
                    if dst_si < len(dst_sheet.slots_left):
                        dst_sd = dst_sheet.slots_left[dst_si]
                        con.execute(
                            'INSERT INTO slot_links (link_id, src_slot_id, dst_slot_id) '
                            'VALUES (?,?,?)',
                            (str(_uuid.uuid4()), src_sd.slot_id, dst_sd.slot_id))

    for sheet, _ in flat:
        if getattr(sheet, '_loaded', False):
            try:
                _sync_sheet(sheet)
            except Exception:
                pass

    return new_links


def apply_kks_autolink(doc) -> int:
    """Alias de rebuild_xsheet_links para compatibilidad con código existente."""
    return rebuild_xsheet_links(doc)


# ── Clonado de grupo en SQLite ──────────────────────────────────────────────

def clone_group_sql(src_group_id: str,
                    doc_id: str, rules: list[tuple[str, str]],
                    override_base: int | None = None,
                    # parámetro legacy ignorado, mantenido por compatibilidad
                    insert_before_group_id: str = '') -> str:
    """
    Clona el grupo src_group_id en la BD en memoria.

    Posicionamiento y desplazamiento:
      - El nuevo grupo se inserta en la posición que corresponde a new_base
        (sheet_number_base del clon = override_base).
      - Solo se desplazan los grupos necesarios para hacer hueco:
          * Se busca el primer grupo cuyo rango de hojas solapa con
            [new_base, new_base + src_count - 1].
          * Si hay solapamiento, todos los grupos con base >= base_conflicto
            se desplazan: su base += (new_base + src_count - base_conflicto).
          * Si no hay solapamiento, no se toca ningún grupo.

    Devuelve el nuevo group_id.
    """
    con = get_mem()
    cur = con.cursor()

    # ── 1. Leer orden actual de grupos ──────────────────────────────────
    rows = cur.execute(
        "SELECT group_id, order_idx, sheet_number_base FROM groups "
        "WHERE doc_id=? ORDER BY order_idx", (doc_id,)).fetchall()
    grp_order = [(r[0], r[1], r[2]) for r in rows]  # (gid, oidx, base)

    # ── 2. Número de hojas del grupo origen ─────────────────────────────
    src_sheet_count = cur.execute(
        "SELECT COUNT(*) FROM sheets WHERE group_id=?",
        (src_group_id,)).fetchone()[0]

    # ── 3. Calcular new_base ─────────────────────────────────────────────
    if override_base is not None:
        new_base = override_base
    else:
        # Sin override: insertar al final
        if grp_order:
            last_gid, _, last_base = grp_order[-1]
            last_count = cur.execute(
                "SELECT COUNT(*) FROM sheets WHERE group_id=?",
                (last_gid,)).fetchone()[0]
            new_base = last_base + last_count
        else:
            new_base = 1

    new_end = new_base + src_sheet_count - 1   # última hoja del nuevo grupo

    # ── 4. Calcular desplazamiento necesario ─────────────────────────────
    # Obtener número de hojas de cada grupo existente
    grp_full = []
    for gid, oidx, base in grp_order:
        cnt = cur.execute(
            "SELECT COUNT(*) FROM sheets WHERE group_id=?",
            (gid,)).fetchone()[0]
        grp_full.append((gid, oidx, base, cnt))

    # Buscar el primer grupo que solapa con [new_base, new_end]
    # Solapamiento: base <= new_end  Y  base+cnt-1 >= new_base
    conflict_base = None
    for gid, oidx, base, cnt in grp_full:
        grp_end = base + cnt - 1
        if base <= new_end and grp_end >= new_base:
            if conflict_base is None or base < conflict_base:
                conflict_base = base

    shift = 0
    if conflict_base is not None:
        shift = new_base + src_sheet_count - conflict_base

    # ── 5. Aplicar desplazamiento y recalcular order_idx ─────────────────
    # Grupos con base >= conflict_base: base += shift, order_idx sube en 1
    # (se insertará el nuevo antes de ellos)
    if shift > 0:
        # Recorrer en orden inverso para no colisionar los order_idx únicos
        for gid, oidx, base, cnt in reversed(grp_full):
            if base >= conflict_base:
                cur.execute(
                    "UPDATE groups SET order_idx=?, sheet_number_base=? "
                    "WHERE group_id=?",
                    (oidx + 1, base + shift, gid))

    # ── 6. Calcular order_idx del nuevo grupo ────────────────────────────
    # Es el número de grupos existentes cuya base (tras el desplazamiento)
    # es menor que new_base. Como el desplazamiento no cambia el orden
    # relativo de los grupos anteriores a conflict_base, simplemente:
    #   order_idx_nuevo = número de grupos con base_original < conflict_base
    #                     (o len(grp_order) si no hay conflicto)
    if conflict_base is not None:
        new_order_idx = sum(1 for _, _, base, _ in grp_full
                            if base < conflict_base)
    else:
        # Sin conflicto: insertar ordenado por new_base
        new_order_idx = sum(1 for _, _, base, _ in grp_full
                            if base < new_base)
        # Desplazar order_idx de los grupos que quedan después
        for gid, oidx, base, cnt in reversed(grp_full):
            if base >= new_base:
                cur.execute(
                    "UPDATE groups SET order_idx=? WHERE group_id=?",
                    (oidx + 1, gid))


    # ── 4. Clonar datos del grupo origen ─────────────────────────────────
    src_grp = cur.execute(
        "SELECT system, description, kks, revision, date FROM groups "
        "WHERE group_id=?", (src_group_id,)).fetchone()

    txt = lambda s: apply_rules(s or '', rules)

    new_group_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO groups (group_id, doc_id, order_idx, system, description, "
        "kks, revision, date, sheet_number_base) VALUES (?,?,?,?,?,?,?,?,?)",
        (new_group_id, doc_id, new_order_idx, txt(src_grp[0]), txt(src_grp[1]),
         txt(src_grp[2]), txt(src_grp[3]), txt(src_grp[4]), new_base))

    # ── 5. Clonar hojas ──────────────────────────────────────────────────
    src_sheets = cur.execute(
        "SELECT sheet_id, order_idx, num_slots, sheet_name, sheet_title, sheet_number "
        "FROM sheets WHERE group_id=? ORDER BY order_idx", (src_group_id,)).fetchall()

    sheet_id_map: dict[str, str] = {}   # old_sheet_id → new_sheet_id
    for sh in src_sheets:
        old_sid, oidx, ns, sname, stitle, snum = sh
        new_sid = str(uuid.uuid4())
        sheet_id_map[old_sid] = new_sid
        cur.execute(
            "INSERT INTO sheets (sheet_id, group_id, order_idx, num_slots, "
            "sheet_name, sheet_title, sheet_number) VALUES (?,?,?,?,?,?,?)",
            (new_sid, new_group_id, oidx, ns,
             txt(sname), txt(stitle), snum))

        # ── 5a. Slots ────────────────────────────────────────────────────
        slot_id_map: dict[str, str] = {}
        slots = cur.execute(
            "SELECT slot_id, side, slot_index, description, signal_desc, "
            "kks, kks2, sub_text, signal_type FROM slots WHERE sheet_id=?",
            (old_sid,)).fetchall()
        for sl in slots:
            old_slid = sl[0]
            new_slid = str(uuid.uuid4())
            slot_id_map[old_slid] = new_slid
            cur.execute(
                "INSERT INTO slots (slot_id, sheet_id, side, slot_index, "
                "description, signal_desc, kks, kks2, sub_text, signal_type) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_slid, new_sid, sl[1], sl[2],
                 txt(sl[3]), txt(sl[4]), txt(sl[5]), txt(sl[6]),
                 '',   # sub_text se recalcula después
                 sl[8]))

        # ── 5b. Blocks + ports ───────────────────────────────────────────
        block_id_map: dict[str, str] = {}
        blocks = cur.execute(
            "SELECT block_id, type_id, x, y, w, h, kks, inscription, label, show_type_label "
            "FROM blocks WHERE sheet_id=?", (old_sid,)).fetchall()
        for bl in blocks:
            old_bid = bl[0]
            new_bid = str(uuid.uuid4())
            block_id_map[old_bid] = new_bid
            cur.execute(
                "INSERT INTO blocks (block_id, sheet_id, type_id, x, y, w, h, "
                "kks, inscription, label, show_type_label) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (new_bid, new_sid, bl[1], bl[2], bl[3], bl[4], bl[5],
                 txt(bl[6]), txt(bl[7]), txt(bl[8]), bl[9]))

            ports = cur.execute(
                "SELECT port_id, side, port_index, name, number, signal_type, negated "
                "FROM block_ports WHERE block_id=?", (old_bid,)).fetchall()
            for po in ports:
                cur.execute(
                    "INSERT INTO block_ports (port_id, block_id, side, port_index, "
                    "name, number, signal_type, negated) VALUES (?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), new_bid, po[1], po[2],
                     po[3], po[4], po[5], po[6]))

        # ── 5c. Branch_nodes primero (sus ids se usan como src/dst en connections)
        branch_id_map: dict[str, str] = {}
        bns = cur.execute(
            "SELECT branch_id, parent_conn_id, x, y FROM branch_nodes WHERE sheet_id=?",
            (old_sid,)).fetchall()
        # Guardamos los branch_nodes pendientes; parent_conn_id se remapeará
        # después de construir conn_id_map (dos pasadas)
        pending_bns = list(bns)
        for bn in pending_bns:
            new_bid = str(uuid.uuid4())
            branch_id_map[bn[0]] = new_bid   # old_branch_id → new_branch_id

        # ── 5d. Connections + waypoints ──────────────────────────────────
        conn_id_map: dict[str, str] = {}
        conns = cur.execute(
            "SELECT conn_id, src_id, src_kind, src_port_idx, "
            "dst_id, dst_kind, dst_port_idx FROM connections WHERE sheet_id=?",
            (old_sid,)).fetchall()
        for cn in conns:
            old_cid = cn[0]
            new_cid = str(uuid.uuid4())
            conn_id_map[old_cid] = new_cid
            # Remap src/dst: slot, bloque o branch_node
            new_src = (slot_id_map.get(cn[1])
                       or block_id_map.get(cn[1])
                       or branch_id_map.get(cn[1])
                       or cn[1])
            new_dst = (slot_id_map.get(cn[4])
                       or block_id_map.get(cn[4])
                       or branch_id_map.get(cn[4])
                       or cn[4])
            cur.execute(
                "INSERT INTO connections (conn_id, sheet_id, src_id, src_kind, "
                "src_port_idx, dst_id, dst_kind, dst_port_idx) VALUES (?,?,?,?,?,?,?,?)",
                (new_cid, new_sid, new_src, cn[2], cn[3],
                 new_dst, cn[5], cn[6]))

            wps = cur.execute(
                "SELECT order_idx, x, y FROM waypoints WHERE conn_id=? ORDER BY order_idx",
                (old_cid,)).fetchall()
            for wp in wps:
                cur.execute(
                    "INSERT INTO waypoints (wp_id, conn_id, order_idx, x, y) VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), new_cid, wp[0], wp[1], wp[2]))

        # Insertar branch_nodes ahora que conn_id_map está completo
        for bn in pending_bns:
            new_parent = conn_id_map.get(bn[1], bn[1])
            cur.execute(
                "INSERT INTO branch_nodes (branch_id, sheet_id, parent_conn_id, x, y) "
                "VALUES (?,?,?,?,?)",
                (branch_id_map[bn[0]], new_sid, new_parent, bn[2], bn[3]))

        # ── 5d. Symbols ──────────────────────────────────────────────────
        syms = cur.execute(
            "SELECT sym_type, port_side, x, y, kks, num_slots "
            "FROM symbols WHERE sheet_id=?", (old_sid,)).fetchall()
        for sy in syms:
            cur.execute(
                "INSERT INTO symbols (sym_id, sheet_id, sym_type, port_side, "
                "x, y, kks, num_slots) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), new_sid, sy[0], sy[1],
                 sy[2], sy[3], txt(sy[4]), sy[5]))

        # ── 5e. Notes + textboxes ─────────────────────────────────────────
        notes = cur.execute(
            "SELECT text, x, y, font_size_px, text_width FROM notes WHERE sheet_id=?",
            (old_sid,)).fetchall()
        for nt in notes:
            cur.execute(
                "INSERT INTO notes (note_id, sheet_id, text, x, y, font_size_px, text_width) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), new_sid, txt(nt[0]), nt[1], nt[2], nt[3],
                 nt[4] if len(nt) > 4 else 0.0))

        tbs = cur.execute(
            "SELECT text, x, y, w, h, font_size_px, signal_type "
            "FROM textboxes WHERE sheet_id=?", (old_sid,)).fetchall()
        for tb in tbs:
            cur.execute(
                "INSERT INTO textboxes (box_id, sheet_id, text, x, y, w, h, "
                "font_size_px, signal_type) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), new_sid, txt(tb[0]),
                 tb[1], tb[2], tb[3], tb[4], tb[5], tb[6]))

    # ── 6. Recrear slot_links internos del clon ──────────────────────────
    # Links que conectan slots dentro del grupo origen → remapear a ids nuevos
    all_old_ids = set(sheet_id_map.keys())
    # slot_id_map acumulado por sheet: reconstruirlo consultando la BD
    all_slot_map: dict[str, str] = {}
    for old_sid, new_sid in sheet_id_map.items():
        old_slots = cur.execute(
            "SELECT slot_id FROM slots WHERE sheet_id=?", (old_sid,)).fetchall()
        new_slots = cur.execute(
            "SELECT slot_id FROM slots WHERE sheet_id=?", (new_sid,)).fetchall()
        for (o,), (n,) in zip(old_slots, new_slots):
            all_slot_map[o] = n

    links = cur.execute(
        "SELECT src_slot_id, dst_slot_id FROM slot_links").fetchall()
    for src_sl, dst_sl in links:
        if src_sl in all_slot_map and dst_sl in all_slot_map:
            cur.execute(
                "INSERT INTO slot_links (link_id, src_slot_id, dst_slot_id) VALUES (?,?,?)",
                (str(uuid.uuid4()), all_slot_map[src_sl], all_slot_map[dst_sl]))

    # No se hace commit aquí: el llamador (worker con savepoint o _clone_group)
    # es responsable de commit/rollback para mantener el control transaccional.
    return new_group_id
