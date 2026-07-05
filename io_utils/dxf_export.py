"""
io_utils/dxf_export.py — Exportar hojas + índice a DXF.
Backend nativo DXF R12/R2000 (sin dependencias externas).
Unidades DXF: mm.  Factor interno→mm: /10.
"""
from __future__ import annotations
from pathlib import Path
_S = 10.0

# ── Capas ─────────────────────────────────────────────────────────────────
L_BORDER='BORDE'; L_HEADER='CABECERA'; L_SLOTS='CONECTORES'; L_GRID='REJILLA'
L_BLOCKS='BLOQUES'; L_CONNS='CONEXIONES'; L_CONNS_DIG='CONEX_DIGITAL'
L_TB='CAJETIN'; L_TEXT='TEXTO'; L_INDEX='INDICE'
_LAYERS = [
    (L_BORDER,7,50),(L_HEADER,5,35),(L_SLOTS,2,18),(L_GRID,9,9),
    (L_BLOCKS,1,50),(L_CONNS,4,35),(L_TB,5,35),(L_TEXT,7,13),(L_INDEX,6,18),
]

# ── Unicode → DXF safe ────────────────────────────────────────────────────
_UNI_MAP = {
    '°': '%%d', '±': '%%p', 'Ø': '%%c', 'ø': '%%c',
    '&': '&', 'Σ': 'Sigma', 'σ': 'sigma', 'α': 'alpha', 'β': 'beta',
    '×': 'x',  '÷': '/', 'µ': 'u', 'Δ': 'D', '∞': 'inf',
    '≥': '>=', '≤': '<=', '≠': '!=', '⊕': '+', '⊟': '-',
    '⋚': '<=>', '⚙': '[M]',
}

def _dxf_str(s: str) -> str:
    r"""Texto seguro para DXF R2000 (AC1015).
    Convierte caracteres comunes con _UNI_MAP y el resto a \U+XXXX."""
    if not s: return ''
    out = []
    for ch in str(s):
        if ord(ch) < 128:
            out.append(ch)
        elif ch in _UNI_MAP:
            out.append(_UNI_MAP[ch])
        else:
            out.append('\\U+' + format(ord(ch), '04X'))
    return ''.join(out)[:300]


# ── Punto de entrada ──────────────────────────────────────────────────────

def export_dxf_all(document, base_scene, output_dir):
    from scene import DiagramScene
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = DiagramScene()
    exported = []
    _write_index(document, output_dir / '00_indice.dxf')
    exported.append(output_dir / '00_indice.dxf')
    for flat_i, (sheet, group) in enumerate(document.flat_sheets()):
        scene.load_sheet(document, flat_i)
        num   = document.sheet_ref(flat_i)
        slug  = _slugify((group.description or ('hoja_' + str(num))).upper())
        kks_slug = _slugify(group.kks.upper()) if group.kks else slug
        fname = output_dir / (format(int(num), '02d') + '_' + kks_slug.upper() + '.dxf')
        _write_sheet(scene, document, flat_i, fname)
        exported.append(fname)
    return exported


# ═══ GENERADOR DXF R2000 (AC1015) ═════════════════════════════════════════
# Estructura mínima: HEADER → TABLES → ENTITIES (sin BLOCKS, sin OBJECTS).
# AC1015 soporta \U+XXXX → Unicode completo en textos.
# Sin HATCH para máxima compatibilidad con LibreCAD.

class _D:
    """Generador DXF R2000 (AC1015). API en mm. Y visual = desde arriba."""

    def __init__(self, pw_mm, ph_mm):
        self.pw = pw_mm; self.ph = ph_mm; self._b = []
        self._header(); self._tables()
        self._b.append('  0\nSECTION\n  2\nENTITIES')

    def _y(self, y_mm):
        return self.ph - y_mm

    # ── primitivas ───────────────────────────────────────────────────────
    def line(self, x0, y0, x1, y1, ly):
        a0 = f'{x0:.4f}'; a1 = f'{self._y(y0):.4f}'
        b0 = f'{x1:.4f}'; b1 = f'{self._y(y1):.4f}'
        self._b.append(
            f'  0\nLINE\n  8\n{ly}\n'
            f' 10\n{a0}\n 20\n{a1}\n 30\n0.0\n'
            f' 11\n{b0}\n 21\n{b1}\n 31\n0.0')

    def rect(self, x0, y0, x1, y1, ly):
        self.line(x0,y0,x1,y0,ly); self.line(x1,y0,x1,y1,ly)
        self.line(x1,y1,x0,y1,ly); self.line(x0,y1,x0,y0,ly)

    def txt(self, s, x, y, h, ly):
        if not s: return
        safe = _dxf_str(s)
        self._b.append(
            f'  0\nTEXT\n  8\n{ly}\n'
            f' 10\n{x:.4f}\n 20\n{self._y(y):.4f}\n 30\n0.0\n'
            f' 40\n{h:.4f}\n  1\n{safe}')

    def txt_center(self, s, xc, y, h, ly):
        """Texto centrado — R12 admite group 72=1 con punto de alineación."""
        if not s: return
        safe = _dxf_str(s)
        yf = self._y(y)
        self._b.append(
            f'  0\nTEXT\n  8\n{ly}\n'
            f' 10\n{xc:.4f}\n 20\n{yf:.4f}\n 30\n0.0\n'
            f' 40\n{h:.4f}\n  1\n{safe}\n'
            f' 72\n1\n'
            f' 11\n{xc:.4f}\n 21\n{yf:.4f}\n 31\n0.0')

    def pline(self, pts_mm, ly, dashed=False):
        if len(pts_mm) < 2: return
        lt = '\n  6\nDASHED' if dashed else ''
        self._b.append(f'  0\nPOLYLINE\n  8\n{ly}{lt}\n 66\n1\n 70\n0')
        for x, y in pts_mm:
            self._b.append(
                f'  0\nVERTEX\n  8\n{ly}\n'
                f' 10\n{x:.4f}\n 20\n{self._y(y):.4f}\n 30\n0.0')
        self._b.append('  0\nSEQEND')

    def circle_mm(self, cx, cy, r, ly):
        self._b.append(
            f'  0\nCIRCLE\n  8\n{ly}\n'
            f' 10\n{cx:.4f}\n 20\n{self._y(cy):.4f}\n 30\n0.0\n'
            f' 40\n{r:.4f}')

    def ellipse_mm(self, x0, y0, w, h, ly):
        if abs(w - h) < 0.1:
            self.circle_mm(x0 + w/2, y0 + h/2, w/2, ly)
        else:
            import math
            cx = x0+w/2; cy = y0+h/2; a = w/2; b = h/2
            pts = [(cx + a*math.cos(math.radians(t)),
                    cy + b*math.sin(math.radians(t))) for t in range(0, 361, 10)]
            self.pline(pts, ly)

    # Sin relleno en R12 — solo contorno para compatibilidad total
    def hatch_rect_mm(self, x0, y0, x1, y1, ly):
        pass   # omitido: HATCH es R2000

    def hatch_circle_mm(self, cx, cy, r, ly):
        pass   # omitido: HATCH es R2000

    def solid_dot_mm(self, cx, cy, r, ly):
        self.circle_mm(cx, cy, r, ly)   # solo contorno

    def save(self, path):
        self._b.append('  0\nENDSEC\n  0\nEOF')
        Path(path).write_text('\n'.join(self._b), encoding='utf-8')

    def _header(self):
        self._b += [
            '  0\nSECTION\n  2\nHEADER',
            '  9\n$ACADVER\n  1\nAC1015',
            '  9\n$INSUNITS\n 70\n4',
            '  9\n$EXTMIN\n 10\n0.0\n 20\n0.0\n 30\n0.0',
            f'  9\n$EXTMAX\n 10\n{self.pw:.3f}\n 20\n{self.ph:.3f}\n 30\n0.0',
            '  0\nENDSEC']

    def _tables(self):
        self._b += [
            '  0\nSECTION\n  2\nTABLES',
            '  0\nTABLE\n  2\nLTYPE\n 70\n2',
            '  0\nLTYPE\n  2\nCONTINUOUS\n 70\n0\n  3\nSolid\n 72\n65\n 73\n0\n 40\n0.0',
            '  0\nLTYPE\n  2\nDASHED\n 70\n0\n  3\n__ __ __\n 72\n65\n 73\n2\n 40\n0.75\n 49\n0.5\n 49\n-0.25',
            '  0\nENDTAB',
            '  0\nTABLE\n  2\nLAYER\n 70\n' + str(len(_LAYERS))]
        for nm, col, _ in _LAYERS:
            ltype = 'DASHED' if nm == 'CONEX_DIGITAL' else 'CONTINUOUS'
            self._b.append(
                f'  0\nLAYER\n  2\n{nm}\n 70\n0\n 62\n{col}\n  6\n{ltype}')
        self._b += [
            '  0\nENDTAB',
            '  0\nTABLE\n  2\nSTYLE\n 70\n1',
            '  0\nSTYLE\n  2\nSTANDARD\n 70\n0\n 40\n0.0\n 41\n1.0\n 50\n0.0\n 71\n0\n 42\n0.2\n  3\ntxt\n  4\n ',
            '  0\nENDTAB',
            '  0\nENDSEC']



# ═══ HOJA ═════════════════════════════════════════════════════════════════

def _write_sheet(scene, document, flat_i, path):
    from const import (PAGE_W, PAGE_H, HEADER_H, WORK_Y, WORK_H,
                       COL_W, COL_L_X, COL_R_X, TB_H, TB_Y, PORT_R,
                       CONN_NUM_PCT, CONN_DESC_PCT, CONN_SIG_PCT, CONN_KKS_PCT,
                       TB_COL_FRACS, mm)

    group = document.group_at(flat_i)
    sheet = document.sheet_at(flat_i)
    num   = document.sheet_ref(flat_i)
    tb    = document.title_block
    NS    = sheet.num_slots
    flat  = list(document.flat_sheets())
    li    = sum(1 for j,(_, g2) in enumerate(flat)
                if j < flat_i and g2.group_id == group.group_id)
    sheet_title = sheet.sheet_title or group.title_for_sheet(li)

    # Todo en mm desde aquí
    PW = PAGE_W/_S;  PH  = PAGE_H/_S
    HH = HEADER_H/_S             # alto cabecera
    WY = WORK_Y/_S               # top zona trabajo  ← ya en mm
    WH = WORK_H/_S               # alto zona trabajo
    CW = COL_W/_S                # ancho columna
    CL = COL_L_X/_S              # x columna izq
    CR = COL_R_X/_S              # x columna der
    TY = TB_Y/_S                 # top cajetín
    TH = TB_H/_S                 # alto cajetín

    d = _D(PW, PH)

    # ── Borde ──
    d.rect(0, 0, PW, PH, L_BORDER)

    # ── Cabecera ──
    d.rect(0, 0, PW, HH, L_HEADER)
    d.line(0, HH, PW, HH, L_BORDER)
    pad_h = PW * 0.01
    # Texto: baseline en HH - pequeño margen (texto sube desde baseline hacia arriba)
    h_hdr1 = HH * 0.45
    h_hdr2 = HH * 0.36
    d.txt(_dxf_str(tb.title), pad_h, HH - HH*0.20, h_hdr1, L_TEXT)
    d.txt(_dxf_str('Hoja ' + str(num) + '  ' + sheet_title),
          PW*0.55, HH - HH*0.20, h_hdr2, L_HEADER)

    # ── Columnas de conectores ──
    # Zona trabajo: de WY (top, bajo cabecera) a TY (top cajetín)
    # Los slots deben llenar exactamente WY→TY
    slot_h = WH / NS             # alto de cada slot en mm
    UPPER  = 2.0/3.0             # fracción zona superior
    LOWER  = 1.0/3.0             # fracción zona referencia

    NW = CW * CONN_NUM_PCT       # ancho celda número
    DW = CW * CONN_DESC_PCT      # ancho descripción equipo
    SW = CW * CONN_SIG_PCT       # ancho descripción señal
    KW = CW * CONN_KKS_PCT       # ancho KKS

    for side, slots, cx in [('left',  sheet.slots_left,  CL),
                             ('right', sheet.slots_right, CR)]:
        # Marco exterior: de WY a TY (tangente al cajetín)
        d.rect(cx, WY, cx+CW, TY, L_SLOTS)

        # Divisor vertical num: izq para left, der para right (full height)
        xnum_div = cx + NW if side == 'left' else cx + CW - NW
        d.line(xnum_div, WY, xnum_div, TY, L_GRID)

        for i, sd in enumerate(slots[:NS]):
            y0 = WY + i * slot_h
            yu = y0 + slot_h * UPPER
            y1 = y0 + slot_h

            d.line(cx, y1, cx+CW, y1, L_GRID)
            # Upper/lower — no cruza la celda de número
            if side == 'left':
                d.line(cx+NW, yu, cx+CW, yu, L_GRID)
            else:
                d.line(cx, yu, cx+CW-NW, yu, L_GRID)

            if side == 'left':
                # izq→der: num | desc | sig | kks
                d.line(cx+NW+DW,    y0, cx+NW+DW,    yu, L_GRID)
                d.line(cx+NW+DW+SW, y0, cx+NW+DW+SW, yu, L_GRID)
                xd = cx+NW; xs = cx+NW+DW; xk = cx+NW+DW+SW
                xnum_cx = cx + NW/2
            else:
                # izq→der: kks | sig | desc | num
                d.line(cx+KW,    y0, cx+KW,    yu, L_GRID)
                d.line(cx+KW+SW, y0, cx+KW+SW, yu, L_GRID)
                xk = cx; xs = cx+KW; xd = cx+KW+SW
                xnum_cx = cx + CW - NW/2

            # ── Textos ──
            hu   = slot_h * UPPER
            hl   = slot_h * LOWER
            # Alturas tipográficas: texto está encima del baseline
            # h_txt debe ser ≤ hu/2 para que quepan 2 líneas
            h_txt = min(hu * 0.27, 2.1)   # tamaño texto desc/señal/kks
            h_num = min(hu * 0.38, 3.0)   # tamaño número conector
            h_ref = min(hl * 0.50, 1.9)   # tamaño referencia
            slp   = CW * 0.008             # padding horizontal

            # Número centrado en su celda
            d.txt_center(format(i+1, '02d'),
                         xnum_cx,
                         y0 + hu * 0.65,
                         h_num, L_TEXT)

            # Textos alineados al mismo baseline superior
            y_l1 = y0 + hu * 0.38    # línea 1
            y_l2 = y0 + hu * 0.72    # línea 2

            if sd.description:
                lns = sd.description.split('\n')
                d.txt(_dxf_str(lns[0][:28]), xd+slp, y_l1, h_txt, L_TEXT)
                if len(lns) > 1 and lns[1].strip():
                    d.txt(_dxf_str(lns[1][:28]), xd+slp, y_l2, h_txt, L_TEXT)

            if sd.signal_desc:
                d.txt(_dxf_str(sd.signal_desc[:22]), xs+slp, y_l1, h_txt, L_TEXT)

            if sd.kks:
                d.txt(_dxf_str(sd.kks[:18]),  xk+slp, y_l1, h_txt, L_TEXT)
            if sd.kks2:
                d.txt(_dxf_str(sd.kks2[:18]), xk+slp, y_l2, h_txt, L_TEXT)

            # Referencia (zona lower): baseline al 65% del lower
            if sd.sub_text:
                d.txt(_dxf_str(sd.sub_text),
                      cx+NW+slp, yu + hl*0.65, h_ref, L_TEXT)

    # ── Constantes de negación ──
    _NR  = PORT_R * 0.9 / _S   # radio del círculo de negación (mm)
    _PR  = PORT_R / _S          # radio del puerto (mm)
    # Offset que recorre la conexión desde el centro del puerto hasta el borde
    # exterior del círculo de negación (= donde debe terminar/empezar la línea)
    _NEG_TRIM = _PR + 2 * _NR   # mm

    def _conn_pts(ci):
        """Puntos de la conexión directamente desde el modelo, sin recortes."""
        try:
            pts_q = ci._full_pts()
        except Exception:
            return []
        return [(p.x()/_S, p.y()/_S) for p in pts_q]

    # ── Conexiones primero (para que símbolos las cubran) ──
    for ci in scene.conn_items:
        try:
            pts    = _conn_pts(ci)
            if len(pts) < 2:
                continue
            is_dig = ci.signal_type() == 'digital'
            ly     = L_CONNS_DIG if is_dig else L_CONNS
            d.pline(pts, ly, dashed=is_dig)
        except Exception:
            pass

    # ── Puntos sólidos en BranchNodes ──
    _DOT_R = _PR * 0.9   # radio del punto de bifurcación (mm)
    for bn in scene.branch_nodes:
        try:
            sp = bn.scenePos()
            d.solid_dot_mm(sp.x()/_S, sp.y()/_S, _DOT_R, L_CONNS)
        except Exception:
            pass

    # ── Bloques: inscripción, nombres de puertos DENTRO, círculos de negación ──
    from model import LIBRARY_BY_ID
    for bi in scene.block_items:
        bd  = bi.data
        bx  = bd.x/_S; by = bd.y/_S; bw = bd.w/_S; bh = bd.h/_S
        d.rect(bx, by, bx+bw, by+bh, L_BLOCKS)

        # Inscripción centrada (texto, símbolo /NNN o mezcla)
        bt   = LIBRARY_BY_ID.get(bd.type_id)
        insc = bd.inscription or (bt.inscription if bt else '')
        if insc:
            from symbols import tokenize_inscription, draw_symbol_dxf, SYMBOLS
            tokens = tokenize_inscription(insc)
            if len(tokens) == 1 and tokens[0][0] == 'symbol':
                # Un único símbolo vectorial
                sym_sz = min(bw, bh) * 0.62
                draw_symbol_dxf(d, tokens[0][1], bx + bw/2, by + bh/2,
                                sym_sz, sym_sz, L_BLOCKS)
            else:
                # Mezcla símbolo+texto o texto puro
                # Separar tokens símbolo de tokens texto
                sym_tokens  = [t for t in tokens if t[0] == 'symbol']
                txt_tokens  = [t for t in tokens if t[0] == 'text']
                txt_str = _dxf_str(''.join(t[1] for t in txt_tokens)).strip()
                h_insc  = min(bh * 0.32, 5.0)
                if sym_tokens and txt_str:
                    # Símbolo en parte izquierda, texto a la derecha
                    sym_sz  = min(bw * 0.55, bh * 0.62)
                    sym_cx  = bx + sym_sz / 2 + bw * 0.04
                    sym_cy  = by + bh / 2
                    draw_symbol_dxf(d, sym_tokens[0][1],
                                    sym_cx, sym_cy, sym_sz, sym_sz, L_BLOCKS)
                    # Texto a la derecha del símbolo, centrado verticalmente
                    txt_x = bx + sym_sz + bw * 0.08
                    txt_y = by + bh * 0.58
                    d.txt(_dxf_str(txt_str), txt_x, txt_y, h_insc, L_TEXT)
                elif sym_tokens:
                    # Solo símbolo (no debería llegar aquí, pero por si acaso)
                    sym_sz = min(bw, bh) * 0.62
                    draw_symbol_dxf(d, sym_tokens[0][1],
                                    bx + bw/2, by + bh/2, sym_sz, sym_sz, L_BLOCKS)
                else:
                    # Solo texto
                    d.txt_center(_dxf_str(''.join(t[1] for t in tokens)),
                                 bx + bw/2, by + bh*0.58, h_insc, L_TEXT)

        # Etiqueta inferior
        if bd.label:
            h_lbl = min(bh * 0.14, 2.2)
            d.txt(_dxf_str(bd.label), bx + bw*0.06, by + bh*0.88, h_lbl, L_TEXT)

        # Puertos: nombres DENTRO del bloque + círculo de negación FUERA
        from const import BLOCK_PORT_SEP, mm as _mm
        _lbl_pad = _mm(1.5) / _S   # mm
        for pi in bi.port_items_in + bi.port_items_out:
            try:
                sp   = pi.scenePos()
                px   = sp.x()/_S; py = sp.y()/_S
                h_pn = min(bh * 0.13, 2.2)
                name = _dxf_str(pi.name)
                if pi.side == 'in':
                    # Puerto en borde izquierdo → nombre va HACIA LA DERECHA (dentro)
                    d.txt(name, px + _lbl_pad, py, h_pn, L_TEXT)
                else:
                    # Puerto en borde derecho → nombre va HACIA LA IZQUIERDA (dentro)
                    char_w = h_pn * 0.62 * max(len(pi.name), 1)
                    d.txt(name, px - _lbl_pad - char_w, py, h_pn, L_TEXT)

                # Círculo de negación: FUERA del bloque, tangente al borde
                if getattr(pi, 'negated', False) and getattr(pi, 'signal_type', '') == 'digital':
                    # Centro del círculo a (PORT_R + neg_r) del borde del bloque
                    cx_neg = (px - (_PR + _NR)) if pi.side == 'in' else (px + _PR + _NR)
                    d.circle_mm(cx_neg, py, _NR, L_BLOCKS)
            except Exception:
                pass

    # ── Símbolos de campo CON FONDO BLANCO (cubren conexiones que pasan por detrás) ──
    for si in scene.symbol_items:
        try:
            sp = si.scenePos()
            from const import SYM_SIZE
            sx = sp.x()/_S; sy = sp.y()/_S
            ss = SYM_SIZE/_S   # lado en mm
            h2 = ss / 2

            if si.sym_type == 'CIRCLE':
                # Fondo blanco (HATCH) → cubre la línea que pasaría por dentro
                d.hatch_circle_mm(sx + h2, sy + h2, h2, L_BLOCKS)
                # Contorno
                d.ellipse_mm(sx, sy, ss, ss, L_BLOCKS)

            elif si.sym_type == 'SENSOR':
                # Fondo blanco cuadrado
                d.hatch_rect_mm(sx, sy, sx+ss, sy+ss, L_BLOCKS)
                d.rect(sx, sy, sx+ss, sy+ss, L_BLOCKS)
                m = ss * 0.12
                d.ellipse_mm(sx+m, sy+m, ss-2*m, ss-2*m, L_BLOCKS)
                d.line(sx, sy+h2, sx+ss, sy+h2, L_BLOCKS)

            elif si.sym_type == 'ACTUATOR':
                # Fondo blanco hexágono (aproximado con rectángulo inscrito)
                d.hatch_rect_mm(sx, sy, sx+ss, sy+ss, L_BLOCKS)
                d.pline([(sx,       sy+h2),
                         (sx+ss*0.25, sy),
                         (sx+ss*0.75, sy),
                         (sx+ss,    sy+h2),
                         (sx+ss*0.75, sy+ss),
                         (sx+ss*0.25, sy+ss),
                         (sx,       sy+h2)], L_BLOCKS)
                d.line(sx, sy+h2, sx+ss, sy+h2, L_BLOCKS)

            # KKS
            if si.kks:
                d.txt(_dxf_str(si.kks), sx, sy + ss + ss*0.1,
                      min(ss*0.28, 2.0), L_TEXT)
        except Exception:
            pass

    # ── Cajetín ──
    xs = [0.0]
    for f in TB_COL_FRACS:
        xs.append(xs[-1] + PW*f)
    xs.append(PW)

    mid = TY + TH/2; h1 = TH/2; sub = TH/3
    pad = PW * 0.005
    lh  = min(TH * 0.09, 1.8)   # altura etiqueta
    vh  = min(TH * 0.16, 3.0)   # altura valor

    d.rect(0, TY, PW, PH, L_TB)
    for x in xs[1:-1]:
        d.line(x, TY, x, PH, L_TB)
    d.line(xs[0], mid, xs[4], mid, L_TB)
    for k in [1, 2]:
        d.line(xs[4], TY+k*sub, xs[5], TY+k*sub, L_TB)

    def cell(x0, y0, hc, lbl, val):
        # Etiqueta: baseline a 22% desde top de celda → texto aparece en 22%-lh%
        d.txt(_dxf_str(lbl), x0+pad, y0 + hc*0.28, lh, L_TB)
        # Valor: baseline a 62%
        d.txt(_dxf_str(val or ''), x0+pad, y0 + hc*0.68, vh, L_TEXT)

    cell(xs[0], TY, h1, 'EMPRESA', tb.company)
    cell(xs[1], TY, h1, 'TITULO DEL DOCUMENTO', tb.title)
    cell(xs[1], mid, h1, 'TITULO DE HOJA', sheet_title)
    cell(xs[2], TY, h1, 'N DOCUMENTO', tb.doc_number)
    cell(xs[2], mid, h1, 'REV. / FECHA',
         _dxf_str(tb.revision) + '  ' + _dxf_str(tb.date))
    cell(xs[3], TY, h1, 'PROYECTO', tb.project)
    cell(xs[3], mid, h1, 'PLANTA / INSTALACION', tb.plant)
    for k, (role, person) in enumerate([
        ('ELABORADO POR', tb.drawn_by),
        ('REVISADO POR',  tb.checked_by),
        ('APROBADO POR',  tb.approved_by),
    ]):
        cell(xs[4], TY + k*sub, sub, role, person)

    # Número de hoja: grande, centrado, sin "H"
    d.txt(_dxf_str('HOJA'), xs[5]+pad, TY + TH*0.25, lh, L_TB)
    num_h = min(TH * 0.46, 13.0)
    xc_n  = (xs[5] + xs[6]) / 2
    d.txt_center(_dxf_str(str(int(num))), xc_n, TY + TH*0.72, num_h, L_TEXT)

    # ── Notas de texto ──
    for nd in sheet.notes:
        try:
            nx   = nd.x / _S
            ny   = nd.y / _S
            htxt = max(1.5, (getattr(nd, 'font_size_px', 0) or int(mm(3.5))) / _S)
            for li, line in enumerate(nd.text.split('\n')):
                line = line.strip()
                if line:
                    d.txt(_dxf_str(line), nx, ny + li * htxt * 1.5, htxt, L_TEXT)
        except Exception:
            pass

    # ── Cajas de texto con puerto ──
    for td in getattr(sheet, 'textboxes', []):
        try:
            tx   = td.x / _S
            ty   = td.y / _S
            htxt = max(1.5, (getattr(td, 'font_size_px', 0) or int(mm(3.5))) / _S)
            pad  = mm(2) / _S
            lines = td.text.split('\n')
            max_chars = max((len(l) for l in lines), default=1)
            tw = max(htxt * max_chars * 0.65 + 2 * pad, mm(20) / _S)
            th = htxt * 1.5 * len(lines) + 2 * pad
            d.rect(tx, ty, tx + tw, ty + th, L_BLOCKS)
            # Centrado vertical: baseline de la primera línea
            text_block_h = htxt * (1 + 1.5 * (len(lines) - 1))
            first_baseline = ty + (th - text_block_h) / 2 + htxt * 0.75
            for li, line in enumerate(lines):
                line = line.strip()
                if line:
                    d.txt(_dxf_str(line), tx + pad,
                          first_baseline + li * htxt * 1.5, htxt, L_TEXT)
            # Puerto de salida: pequeño círculo en borde derecho
            d.circle_mm(tx + tw, ty + th / 2, PORT_R / _S, L_BLOCKS)
        except Exception:
            pass

    d.save(path)


# ═══ ÍNDICE ═══════════════════════════════════════════════════════════════

def _write_index(document, path):
    from const import PAGE_W, PAGE_H
    PW = PAGE_W/_S; PH = PAGE_H/_S
    flat = list(document.flat_sheets())
    tb   = document.title_block

    marg  = PW * 0.05
    hdr_h = PH * 0.08
    row_h = PH * 0.034
    c_num = PW * 0.08
    c_sys = PW * 0.18
    c_kks = PW * 0.20

    d = _D(PW, PH)
    d.rect(0, 0, PW, PH, L_BORDER)
    d.rect(0, 0, PW, hdr_h, L_INDEX)
    d.txt('INDICE DEL DOCUMENTO', marg, hdr_h*0.65, hdr_h*0.45, L_TEXT)
    d.txt(_dxf_str(tb.doc_number), PW*0.70, hdr_h*0.65, hdr_h*0.35, L_TEXT)

    th  = hdr_h + PH*0.01
    rh  = min(row_h * 0.42, 3.0)
    d.rect(marg, th, PW-marg, th+row_h, L_INDEX)
    pad = PW*0.005
    for lbl, x in [('HOJA', marg), ('SISTEMA', marg+c_num),
                   ('KKS',  marg+c_num+c_sys),
                   ('TITULO', marg+c_num+c_sys+c_kks)]:
        d.txt(lbl, x+pad, th+row_h*0.65, rh, L_INDEX)
    d.line(marg, th+row_h, PW-marg, th+row_h, L_INDEX)

    y_cur = th + row_h
    for flat_i, (sheet, group) in enumerate(flat):
        if y_cur + row_h > PH - marg: break
        num   = document.sheet_ref(flat_i)
        li    = sum(1 for j,(_, g2) in enumerate(flat)
                    if j < flat_i and g2.group_id == group.group_id)
        title = sheet.sheet_title or group.title_for_sheet(li)
        d.txt(format(int(num), '02d'),      marg+pad,             y_cur+row_h*0.65, rh, L_TEXT)
        d.txt(_dxf_str(group.system or ''), marg+c_num+pad,       y_cur+row_h*0.65, rh, L_TEXT)
        d.txt(_dxf_str(group.kks or ''),    marg+c_num+c_sys+pad, y_cur+row_h*0.65, rh, L_TEXT)
        d.txt(_dxf_str(title or ''),        marg+c_num+c_sys+c_kks+pad, y_cur+row_h*0.65, rh, L_TEXT)
        d.line(marg, y_cur+row_h, PW-marg, y_cur+row_h, L_GRID)
        y_cur += row_h

    d.save(path)


# ── Utilidades ────────────────────────────────────────────────────────────

def _slugify(text, max_len=40):
    import re
    s = re.sub(r'[^\w\s-]', '', str(text))
    s = re.sub(r'[\s_-]+', '_', s).strip('_')
    return s[:max_len] or 'hoja'
