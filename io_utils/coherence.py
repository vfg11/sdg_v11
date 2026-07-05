"""
io_utils/coherence.py — Análisis de coherencia del documento.

Uso:
    from io_utils.coherence import analyze
    issues = analyze(doc)        # doc debe tener todas las hojas cargadas

Cada Issue tiene:
    severity  : 'error' | 'warning' | 'info'
    category  : str
    message   : str
    sheet_idx : int  (-1 = global)
    slot_side : 'left' | 'right' | None
    slot_idx  : int  (-1 = N/A)
    fix       : callable | None   (lambda que corrige el problema, o None)
    fix_label : str               (etiqueta del botón de reparación)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


# ── Estructura de incidencia ───────────────────────────────────────────────

@dataclass
class Issue:
    severity:  str                    # 'error' | 'warning' | 'info'
    category:  str
    message:   str
    sheet_idx: int       = -1         # hoja afectada (-1 = global)
    slot_side: str | None = None      # 'left' | 'right' | None
    slot_idx:  int       = -1
    fix:       Optional[Callable] = field(default=None, repr=False)
    fix_label: str       = ''

    @property
    def is_fixable(self) -> bool:
        return self.fix is not None

    @property
    def severity_order(self) -> int:
        return {'error': 0, 'warning': 1, 'info': 2}.get(self.severity, 9)


# ── Función principal ──────────────────────────────────────────────────────

def analyze(doc) -> list[Issue]:
    """
    Analiza el documento completo y devuelve la lista de Issues ordenada
    por severidad. Todas las hojas deben estar cargadas antes de llamar.
    """
    issues: list[Issue] = []
    flat = list(doc.flat_sheets())
    n_sheets = len(flat)

    # Índices de acceso rápido
    # slot_id → (flat_idx, side, slot_idx, SlotData)
    slot_map: dict[str, tuple] = {}
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_left):
            slot_map[sd.slot_id] = (fi, 'left', si, sd)
        for si, sd in enumerate(sheet.slots_right):
            slot_map[sd.slot_id] = (fi, 'right', si, sd)

    # conn_id → set por hoja
    conn_ids_by_sheet:   list[set] = []
    block_ids_by_sheet:  list[set] = []
    slot_ids_by_sheet:   list[set] = []
    branch_ids_by_sheet: list[set] = []
    symbol_ids_by_sheet: list[set] = []
    textbox_ids_by_sheet: list[set] = []
    for fi, (sheet, _) in enumerate(flat):
        conn_ids_by_sheet.append({cd.conn_id for cd in sheet.connections})
        block_ids_by_sheet.append({bd.block_id for bd in sheet.blocks})
        slot_ids_by_sheet.append(
            {sd.slot_id for sd in sheet.slots_left} |
            {sd.slot_id for sd in sheet.slots_right})
        branch_ids_by_sheet.append(
            {bnd.branch_id for bnd in getattr(sheet, 'branch_nodes', [])})
        symbol_ids_by_sheet.append(
            {sy.sym_id for sy in getattr(sheet, 'symbols', [])
             if hasattr(sy, 'sym_id')})
        textbox_ids_by_sheet.append(
            {tb.textbox_id for tb in getattr(sheet, 'textboxes', [])})

    # ── 1. Referencias rotas en slots ENTRADA (left) ──────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_left):
            bad_links = []
            for li, (r_fi, r_sl) in enumerate(
                    zip(sd.linked_sheets, sd.linked_slots)):
                if not (0 <= r_fi < n_sheets):
                    bad_links.append(li)
                    continue
                r_sheet = flat[r_fi][0]
                if not (0 <= r_sl < len(r_sheet.slots_right)):
                    bad_links.append(li)
            if bad_links:
                _sd = sd   # captura para lambda
                _bad = list(bad_links)
                def _fix_broken_left(s=_sd, bad=_bad):
                    for i in sorted(bad, reverse=True):
                        if i < len(s.linked_sheets):
                            s.linked_sheets.pop(i)
                            s.linked_slots.pop(i)
                    if not s.linked_sheets:
                        s.sub_text = ''
                issues.append(Issue(
                    severity='error',
                    category='Referencias',
                    message=(f'{sheet_label} · Entrada {si+1}: '
                             f'{len(bad_links)} enlace(s) apuntan a hoja/slot inexistente'),
                    sheet_idx=fi, slot_side='left', slot_idx=si,
                    fix=_fix_broken_left,
                    fix_label='Eliminar enlaces rotos'))

    # ── 2. Referencias rotas en slots SALIDA (right) ──────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_right):
            bad_links = []
            for li, (r_fi, r_sl) in enumerate(
                    zip(sd.linked_sheets, sd.linked_slots)):
                if not (0 <= r_fi < n_sheets):
                    bad_links.append(li); continue
                r_sheet = flat[r_fi][0]
                if not (0 <= r_sl < len(r_sheet.slots_left)):
                    bad_links.append(li); continue
                # ¿la entrada referencia de vuelta a esta salida?
                r_sd = r_sheet.slots_left[r_sl]
                back = any(s == fi and sl == si
                           for s, sl in zip(r_sd.linked_sheets, r_sd.linked_slots))
                if not back:
                    bad_links.append(li)
            if bad_links:
                _sd = sd; _bad = list(bad_links); _fi = fi; _si = si
                def _fix_orphan_right(s=_sd, bad=_bad, src_fi=_fi, src_si=_si):
                    for i in sorted(bad, reverse=True):
                        if i < len(s.linked_sheets):
                            s.linked_sheets.pop(i)
                            s.linked_slots.pop(i)
                    s.rebuild_sub_text(doc, 'right', src_fi, src_si)
                issues.append(Issue(
                    severity='error',
                    category='Referencias',
                    message=(f'{sheet_label} · Salida {si+1}: '
                             f'{len(bad_links)} enlace(s) sin contrapartida en la entrada'),
                    sheet_idx=fi, slot_side='right', slot_idx=si,
                    fix=_fix_orphan_right,
                    fix_label='Eliminar enlaces huérfanos'))

    # ── 3. sub_text desincronizado ─────────────────────────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for side, slots in (('left', sheet.slots_left),
                             ('right', sheet.slots_right)):
            for si, sd in enumerate(slots):
                if not sd.linked_sheets:
                    if sd.sub_text:
                        _sd = sd
                        def _fix_subtext_empty(s=_sd):
                            s.sub_text = ''
                        issues.append(Issue(
                            severity='warning',
                            category='sub_text',
                            message=(f'{sheet_label} · '
                                     f'{"Entrada" if side=="left" else "Salida"} {si+1}: '
                                     f'sub_text "{sd.sub_text}" sin enlaces activos'),
                            sheet_idx=fi, slot_side=side, slot_idx=si,
                            fix=_fix_subtext_empty, fix_label='Limpiar sub_text'))
                    continue
                # Calcular sub_text esperado
                expected = _expected_sub_text(sd, doc, side, fi, si, flat)
                if sd.sub_text != expected:
                    _sd = sd; _exp = expected; _fi = fi; _si = si; _side = side
                    def _fix_subtext(s=_sd, ex=_exp):
                        s.sub_text = ex
                    issues.append(Issue(
                        severity='warning',
                        category='sub_text',
                        message=(f'{sheet_label} · '
                                 f'{"Entrada" if side=="left" else "Salida"} {si+1}: '
                                 f'sub_text desincronizado'),
                        sheet_idx=fi, slot_side=side, slot_idx=si,
                        fix=_fix_subtext, fix_label='Recalcular sub_text'))

    # ── 4. KKS de ENTRADA sin enlace pero con KKS de SALIDA coincidente ───
    # Construir índice de salidas por clave KKS
    output_kks: dict[str, list[tuple]] = {}  # clave → [(fi, si, sd), ...]
    for fi, (sheet, _) in enumerate(flat):
        for si, sd in enumerate(sheet.slots_right):
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if key:
                output_kks.setdefault(key, []).append((fi, si, sd))

    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_left):
            if sd.is_linked():
                continue
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if not key:
                continue
            matches = output_kks.get(key, [])
            if matches:
                _sd = sd; _fi = fi; _si = si; _matches = matches
                def _fix_missing_link(s=_sd, dst_fi=_fi, dst_si=_si,
                                      srcs=_matches, d=doc):
                    src_fi, src_si, src_sd = srcs[0]
                    src_sd.add_link(dst_fi, dst_si)
                    s.linked_sheets = [src_fi]
                    s.linked_slots  = [src_si]
                    s.description   = src_sd.description
                    s.signal_desc   = src_sd.signal_desc
                    s.kks           = src_sd.kks
                    s.kks2          = src_sd.kks2
                    src_sd.rebuild_sub_text(d, 'right', src_fi, src_si)
                    s.sub_text = _expected_sub_text(s, d, 'left', dst_fi, dst_si,
                                                    list(d.flat_sheets()))
                issues.append(Issue(
                    severity='warning',
                    category='KKS',
                    message=(f'{sheet_label} · Entrada {si+1} '
                             f'KKS "{sd.kks}" coincide con salida pero no está enlazada'),
                    sheet_idx=fi, slot_side='left', slot_idx=si,
                    fix=_fix_missing_link, fix_label='Establecer enlace'))

    # ── 5. KKS duplicado en SALIDAS ───────────────────────────────────────
    seen_output_kks: dict[str, tuple] = {}
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_right):
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if not key:
                continue
            if key in seen_output_kks:
                prev_fi, prev_si = seen_output_kks[key]
                prev_label = _sheet_label(prev_fi, flat[prev_fi][1], doc)
                issues.append(Issue(
                    severity='warning',
                    category='KKS',
                    message=(f'KKS "{sd.kks}" duplicado: '
                             f'{prev_label}·S{prev_si+1} y {sheet_label}·S{si+1}'),
                    sheet_idx=fi, slot_side='right', slot_idx=si))
            else:
                seen_output_kks[key] = (fi, si)

    # ── 6. ENTRADA enlazada con KKS desincronizado respecto a la SALIDA ───
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_left):
            if not sd.is_linked():
                continue
            r_fi = sd.linked_sheets[0]
            r_sl = sd.linked_slots[0]
            if not (0 <= r_fi < n_sheets):
                continue
            r_sheet = flat[r_fi][0]
            if not (0 <= r_sl < len(r_sheet.slots_right)):
                continue
            src_sd = r_sheet.slots_right[r_sl]
            src_key = (src_sd.kks.strip() + src_sd.kks2.strip()).upper()
            dst_key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if src_key and dst_key and src_key != dst_key:
                _sd = sd; _src = src_sd
                def _fix_kks_sync(s=_sd, src=_src):
                    s.kks  = src.kks
                    s.kks2 = src.kks2
                    s.description = src.description
                    s.signal_desc = src.signal_desc
                issues.append(Issue(
                    severity='warning',
                    category='KKS',
                    message=(f'{sheet_label} · Entrada {si+1}: '
                             f'KKS "{sd.kks}" difiere del de la salida "{src_sd.kks}"'),
                    sheet_idx=fi, slot_side='left', slot_idx=si,
                    fix=_fix_kks_sync, fix_label='Sincronizar KKS desde salida'))

    # ── 7. Solapamiento de sheet_number_base ──────────────────────────────
    ranges = []
    for g in doc.groups:
        n = len(g.sheets)
        ranges.append((g.sheet_number_base, g.sheet_number_base + n - 1, g))
    for i, (a0, a1, ga) in enumerate(ranges):
        for j, (b0, b1, gb) in enumerate(ranges):
            if j <= i: continue
            if a0 <= b1 and b0 <= a1:
                issues.append(Issue(
                    severity='error',
                    category='Estructura',
                    message=(f'Solapamiento de numeración: '
                             f'"{ga.description}" (H{a0}-H{a1}) y '
                             f'"{gb.description}" (H{b0}-H{b1})')))

    # ── 8. Conexiones con endpoints inexistentes ───────────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        valid_ids = (block_ids_by_sheet[fi]
                     | slot_ids_by_sheet[fi]
                     | branch_ids_by_sheet[fi]
                     | symbol_ids_by_sheet[fi]
                     | textbox_ids_by_sheet[fi])
        bad_conns = []
        for cd in sheet.connections:
            src_ok = (cd.src is None or cd.src.kind == 'branch'
                      or cd.src.item_id in valid_ids)
            dst_ok = (cd.dst is None or cd.dst.kind == 'branch'
                      or cd.dst.item_id in valid_ids)
            # Para kind='branch' verificar que el branch_id existe
            if cd.src is not None and cd.src.kind == 'branch':
                src_ok = cd.src.item_id in branch_ids_by_sheet[fi]
            if cd.dst is not None and cd.dst.kind == 'branch':
                dst_ok = cd.dst.item_id in branch_ids_by_sheet[fi]
            if not (src_ok and dst_ok):
                bad_conns.append(cd)
        if bad_conns:
            _sheet = sheet; _bad = list(bad_conns)
            def _fix_bad_conns(s=_sheet, bad=_bad):
                for cd in bad:
                    if cd in s.connections:
                        s.connections.remove(cd)
            issues.append(Issue(
                severity='error',
                category='Conexiones',
                message=(f'{sheet_label}: {len(bad_conns)} conexión(es) '
                         f'con origen/destino inexistente'),
                sheet_idx=fi,
                fix=_fix_bad_conns, fix_label='Eliminar conexiones rotas'))

    # ── 9. branch_nodes con parent_conn_id inexistente ────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        bad_bns = [bn for bn in sheet.branch_nodes
                   if bn.parent_conn_id not in conn_ids_by_sheet[fi]]
        if bad_bns:
            _sheet = sheet; _bad = list(bad_bns)
            def _fix_bad_bns(s=_sheet, bad=_bad):
                for bn in bad:
                    if bn in s.branch_nodes:
                        s.branch_nodes.remove(bn)
            issues.append(Issue(
                severity='error',
                category='Conexiones',
                message=(f'{sheet_label}: {len(bad_bns)} nodo(s) de bifurcación '
                         f'sin conexión padre'),
                sheet_idx=fi,
                fix=_fix_bad_bns, fix_label='Eliminar nodos huérfanos'))

    # ── 10. num_slots inconsistente ────────────────────────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        real = max(len(sheet.slots_left), len(sheet.slots_right))
        if real != sheet.num_slots and real > 0:
            _sheet = sheet; _real = real
            def _fix_num_slots(s=_sheet, r=_real):
                s.num_slots = r
            issues.append(Issue(
                severity='warning',
                category='Estructura',
                message=(f'{sheet_label}: num_slots={sheet.num_slots} '
                         f'pero hay {real} slots reales'),
                sheet_idx=fi,
                fix=_fix_num_slots, fix_label='Corregir num_slots'))

    # ── 11. Aviso: ENTRADA con KKS sin enlace (ninguna salida coincide) ───
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        for si, sd in enumerate(sheet.slots_left):
            if sd.is_linked() or not sd.kks.strip():
                continue
            key = (sd.kks.strip() + sd.kks2.strip()).upper()
            if key not in output_kks:
                issues.append(Issue(
                    severity='info',
                    category='KKS',
                    message=(f'{sheet_label} · Entrada {si+1}: '
                             f'KKS "{sd.kks}" sin salida coincidente en el documento'),
                    sheet_idx=fi, slot_side='left', slot_idx=si))

    # ── 12. Aviso: bloque sin ningún puerto conectado ─────────────────────
    for fi, (sheet, group) in enumerate(flat):
        sheet_label = _sheet_label(fi, group, doc)
        connected_ids: set[str] = set()
        for cd in sheet.connections:
            if cd.src: connected_ids.add(cd.src.item_id)
            if cd.dst: connected_ids.add(cd.dst.item_id)
        for bd in sheet.blocks:
            if bd.block_id not in connected_ids and (bd.inputs or bd.outputs):
                issues.append(Issue(
                    severity='info',
                    category='Bloques',
                    message=(f'{sheet_label}: bloque "{bd.label or bd.kks or bd.type_id}" '
                             f'sin ningún puerto conectado'),
                    sheet_idx=fi))

    return sorted(issues, key=lambda i: (i.severity_order, i.sheet_idx))


# ── Helpers ────────────────────────────────────────────────────────────────

def _sheet_label(fi: int, group, doc) -> str:
    num = doc.sheet_ref(fi) if hasattr(doc, 'sheet_ref') else str(fi + 1)
    desc = group.description or group.kks or f'Grupo {fi}'
    return f'H{num} {desc}'


def _expected_sub_text(sd, doc, side: str, fi: int, si: int, flat: list) -> str:
    """Calcula el sub_text correcto para un slot dado su estado de enlaces."""
    if not sd.linked_sheets:
        return ''
    refs = []
    for r_fi, r_sl in zip(sd.linked_sheets, sd.linked_slots):
        if 0 <= r_fi < len(flat):
            _, r_group = flat[r_fi]
            num = r_group.sheet_number_base + sum(
                1 for j, (_, g2) in enumerate(flat)
                if j < r_fi and g2.group_id == r_group.group_id)
            refs.append(f'H.{num}:{r_sl+1:02d}')
    return ', '.join(refs)


def apply_fix(issue: Issue, doc, scene=None) -> bool:
    """
    Aplica la corrección de un Issue.
    Si se pasa la escena activa, también persiste el cambio en BD.
    Devuelve True si tuvo éxito.
    """
    if not issue.is_fixable:
        return False
    try:
        issue.fix()
        if scene is not None:
            from io_utils.db_io import sync_sheet
            # Persistir todas las hojas afectadas
            if issue.sheet_idx >= 0:
                flat = list(doc.flat_sheets())
                if 0 <= issue.sheet_idx < len(flat):
                    sync_sheet(flat[issue.sheet_idx][0])
        return True
    except Exception:
        return False
