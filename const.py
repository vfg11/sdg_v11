"""
const.py — Constantes globales.
1 unidad = 0.1 mm  →  PAGE_W=4200, PAGE_H=2970
"""

def mm(x):
    return x * 10.0

# ── Página A3 apaisada ───────────────────────────────────────────────────
PAGE_W  = mm(420)
PAGE_H  = mm(297)

# ── Márgenes en PDF ───────────────────────────────────────────────────────
PDF_MARGIN = mm(5)   # 5 mm blanco alrededor en el PDF

# ── Cabecera ─────────────────────────────────────────────────────────────
HEADER_H = mm(12)

# ── Cajetín inferior ─────────────────────────────────────────────────────
TB_H    = mm(32)
TB_Y    = PAGE_H - TB_H

# ── Área de trabajo ──────────────────────────────────────────────────────
WORK_Y  = HEADER_H
WORK_H  = PAGE_H - HEADER_H - TB_H

# ── Columnas laterales ───────────────────────────────────────────────────
COL_W   = mm(88)   # ampliado para fuentes legibles en conectores (+10mm)
COL_L_X = mm(0)
COL_R_X = PAGE_W - COL_W

# ── Área central ─────────────────────────────────────────────────────────
CANVAS_X = COL_W
CANVAS_Y = WORK_Y
CANVAS_W = PAGE_W - 2 * COL_W
CANVAS_H = WORK_H

# ── Cajones ──────────────────────────────────────────────────────────────
DEFAULT_SLOTS = 23
KKS_CHARS     = 18   # eliminado campo señal, KKS ampliado

def slot_h(n_slots=DEFAULT_SLOTS):
    return WORK_H / n_slots

# ── Cuadrícula ───────────────────────────────────────────────────────────
GRID = mm(5)

# ── Puertos ──────────────────────────────────────────────────────────────
PORT_R   = mm(1.1)   # reducido para aspecto más fino
PORT_HIT = mm(4)

# ── Fuentes (pixelSize en unidades de escena) ─────────────────────────────
F_SLOT_NUM    = int(mm(3.5))   # número de conector
F_SLOT_KKS    = int(mm(4.2))   # KKS (retrocompat.)
F_SLOT_SUB    = int(mm(3.2))   # referencia de hoja (origen/destino)

# ── Fuentes nuevo layout de conector ─────────────────────────────────────
F_CONN_NUM    = int(mm(5.5))   # número de conector (celda 8%)
F_CONN_TEXT   = 44             # texto desc/señal/KKS (px fijo, Courier New) — doble
F_CONN_REF    = int(mm(4.0))   # referencia automática (celda inferior)

# ── Proporciones del conector ─────────────────────────────────────────────
CONN_NUM_PCT  = 0.06   # fracción ancho para número
CONN_DESC_PCT = 0.46   # fracción ancho para descripción equipo
CONN_SIG_PCT  = 0.20   # fracción ancho para descripción señal
CONN_KKS_PCT  = 0.28   # fracción ancho para KKS
CONN_UPPER_H  = 0.82   # fracción altura zona superior (textos) — ampliado
CONN_LOWER_H  = 0.18   # fracción altura zona inferior (referencia)
F_BLOCK_TYPE  = int(mm(4.2))   # nombre tipo bloque
F_BLOCK_KKS   = int(mm(3.2))   # KKS / etiqueta bloque
F_PORT_LABEL  = int(mm(2.8))   # etiqueta de puerto
F_HEADER_TITLE= int(mm(6.0))
F_HEADER_INFO = int(mm(3.5))
F_COL_LABEL   = int(mm(3.5))
F_TB_FIELD_LBL= int(mm(2.8))
F_TB_VALUE    = int(mm(4.2))
F_TB_TITLE    = int(mm(6.5))
F_TB_SHEET    = int(mm(9.0))

# ── Bloque central (más pequeño) ─────────────────────────────────────────
BLOCK_MIN_W    = mm(10)
BLOCK_MIN_H    = mm(14)
BLOCK_PORT_SEP = mm(7)

# ── Símbolos de campo ────────────────────────────────────────────────────
SYM_SIZE     = mm(10.0)  # lado del cuadrado contenedor (≈91% cajón a 23 ranuras)

# ── Textos de anotación ───────────────────────────────────────────────────
F_NOTE       = int(mm(3.8))   # fuente de notas
COLOR_NOTE   = '#334466'

# ── Conexiones ───────────────────────────────────────────────────────────
CONN_PEN_W     = mm(0.5)
CONN_STUB      = mm(5)     # tramo horizontal fijo en origen y destino
CONN_SEP       = mm(4.0)   # separación mínima entre segmentos solapados
CONN_DOT_R     = mm(1.0)   # radio del punto de derivación (junction dot)
CONN_COLOR     = '#1a1a2e'
CONN_SEL_COLOR = '#E05500'
WP_HANDLE_R    = mm(2.5)

# ── Colores ──────────────────────────────────────────────────────────────
COLOR_PAGE           = '#FFFFFF'
COLOR_COL_BG         = '#F0F4F8'
COLOR_COL_BORDER     = '#8899AA'
COLOR_SLOT_USED      = '#FFFFFF'
COLOR_SLOT_EMPTY     = '#F8FAFC'
COLOR_SLOT_LINE      = '#C8D6E5'
COLOR_SLOT_LINKED    = '#E8F4E8'   # cajón con enlace inter-hoja
COLOR_SLOT_PENDING   = '#FFF4CC'   # cajón seleccionado esperando enlace
COLOR_BLOCK_BG       = '#E8F0FE'
COLOR_BLOCK_BDR      = '#3355AA'
COLOR_PORT_IN        = '#2255CC'
COLOR_PORT_OUT       = '#CC3322'
COLOR_GRID           = '#DDE5EE'
COLOR_HEADER         = '#1a2a4a'
COLOR_HEADER_TXT     = '#FFFFFF'
COLOR_TB_BG          = '#F5F8FF'
COLOR_TB_BORDER      = '#2A3A5A'
COLOR_TB_LINE        = '#8899BB'

# ── Cajetín: proporciones de columnas ───────────────────────────────────
# [logo | título | doc/rev | proyecto/planta | firmas | hoja]
TB_COL_FRACS = [0.10, 0.30, 0.14, 0.18, 0.20, 0.08]
