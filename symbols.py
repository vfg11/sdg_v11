"""
symbols.py — Catálogo de símbolos gráficos para inscripciones de bloque.

Uso en campos de inscripción:
  /001  /002  ...  /014   → símbolo correspondiente
  //                      → barra literal /

Cada símbolo se define en coordenadas normalizadas [0,1]×[0,1]
con Y=0 arriba, Y=1 abajo (igual que Qt/DXF-flip).

Comandos por símbolo (lista de tuplas):
  ('pl',  [(x,y),...])               — polilínea abierta
  ('ln',  x0, y0, x1, y1)           — segmento único
  ('txt', x, y, sz, 'texto', 'l'|'c'|'r')  — texto pequeño
         x,y = posición normalizada del baseline/anchor
         sz  = fracción del tamaño total (e.g. 0.22 = 22 % del alto del área)

Para añadir un símbolo nuevo: añadir entrada en SYMBOLS con el siguiente
índice de tres dígitos y la lista de comandos geométricos.
"""
from __future__ import annotations
import re

# ── Tokenizador de inscripciones ─────────────────────────────────────────
#
# Reglas:
#   /DDD  → símbolo (exactamente 3 dígitos tras la barra; el car. siguiente
#            puede ser cualquier cosa — nunca se lee un 4º dígito como parte
#            del código de símbolo)
#   //    → barra literal /
#   resto → texto

def tokenize_inscription(text: str) -> list[tuple[str, int | str]]:
    """
    Divide la inscripción en tokens ordenados:
      ('symbol', idx:int) — /NNN con exactamente 3 dígitos
      ('text',   str)     — cualquier otra cosa; // ya sustituido por /
    """
    tokens: list[tuple[str, int | str]] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '/':
            nxt = text[i + 1] if i + 1 < n else ''
            if nxt == '/':          # // → barra literal
                buf.append('/')
                i += 2
                continue
            if i + 4 <= n and text[i + 1:i + 4].isdigit():   # /DDD → símbolo
                if buf:
                    tokens.append(('text', ''.join(buf)))
                    buf = []
                tokens.append(('symbol', int(text[i + 1:i + 4])))
                i += 4
                continue
        buf.append(text[i])
        i += 1
    if buf:
        tokens.append(('text', ''.join(buf)))
    return tokens


def parse_inscription(text: str) -> tuple[str, int | str]:
    """
    Compatibilidad con código existente.
    Si la inscripción es exactamente un símbolo → ('symbol', idx).
    En cualquier otro caso → ('text', cadena con // → /).
    Para contenido mixto usar tokenize_inscription() directamente.
    """
    if not text:
        return ('text', '')
    tokens = tokenize_inscription(text.strip())
    if len(tokens) == 1 and tokens[0][0] == 'symbol':
        return tokens[0]
    # Caso mixto o texto puro: devolver como texto
    # (los consumidores que soportan mezcla deben llamar tokenize_inscription)
    return ('text', text.replace('//', '/'))


# ── Definiciones de símbolos ──────────────────────────────────────────────
#
# Coordenadas [0,1]×[0,1]: (0,0)=esquina superior izquierda, (1,1)=inferior derecha
#
SYMBOLS: dict[int, dict] = {

    # 001 — Flanco de subida  ___|‾‾‾
    1: {
        'name': 'Flanco subida',
        'cmds': [
            ('pl', [(0.05, 0.68), (0.42, 0.68),
                    (0.42, 0.32), (0.95, 0.32)]),
        ],
    },

    # 002 — Flanco de bajada  ‾‾‾|___
    2: {
        'name': 'Flanco bajada',
        'cmds': [
            ('pl', [(0.05, 0.32), (0.58, 0.32),
                    (0.58, 0.68), (0.95, 0.68)]),
        ],
    },

    # 003 — Mayor o igual  ≥
    3: {
        'name': 'Mayor o igual',
        'cmds': [
            ('pl', [(0.15, 0.18), (0.85, 0.50), (0.15, 0.78)]),   # >
            ('ln', 0.15, 0.88, 0.85, 0.88),                        # _
        ],
    },

    # 004 — Pulso  ___|‾‾‾|___
    4: {
        'name': 'Pulso',
        'cmds': [
            ('pl', [(0.04, 0.70), (0.22, 0.70),
                    (0.22, 0.30), (0.60, 0.30),
                    (0.60, 0.70), (0.96, 0.70)]),
        ],
    },

    # 005 — Temporizador  T → 0
    5: {
        'name': 'Temporizador T-0',
        'cmds': [
            ('ln', 0.10, 0.58, 0.90, 0.58),          # línea horizontal
            ('ln', 0.10, 0.38, 0.10, 0.78),          # límite izquierdo
            ('ln', 0.90, 0.38, 0.90, 0.78),          # límite derecho
            ('txt', 0.10, 0.34, 0.22, 'T', 'c'),     # T izquierda
            ('txt', 0.90, 0.34, 0.22, '0', 'c'),     # 0 derecha
            ('txt', 0.50, 0.34, 0.18, 'SEC', 'c'),   # SEC centro
        ],
    },

    # 006 — Temporizador  0 → T
    6: {
        'name': 'Temporizador 0-T',
        'cmds': [
            ('ln', 0.10, 0.58, 0.90, 0.58),
            ('ln', 0.10, 0.38, 0.10, 0.78),
            ('ln', 0.90, 0.38, 0.90, 0.78),
            ('txt', 0.10, 0.34, 0.22, '0', 'c'),
            ('txt', 0.90, 0.34, 0.22, 'T', 'c'),
            ('txt', 0.50, 0.34, 0.18, 'SEC', 'c'),
        ],
    },

    # 007 — Sigma mayúscula  Σ  (sumatorio)
    7: {
        'name': 'Sumatorio',
        'cmds': [
            ('ln', 0.15, 0.12, 0.85, 0.12),   # tope
            ('ln', 0.15, 0.88, 0.85, 0.88),   # base
            ('ln', 0.15, 0.12, 0.82, 0.50),   # diagonal superior
            ('ln', 0.15, 0.88, 0.82, 0.50),   # diagonal inferior
        ],
    },

    # 008 — Delta mayúscula  Δ  (diferencia)
    8: {
        'name': 'Diferencia',
        'cmds': [
            ('pl', [(0.50, 0.10), (0.08, 0.90),
                    (0.92, 0.90), (0.50, 0.10)]),
        ],
    },

    # 009 — Integral  ∫
    9: {
        'name': 'Integral',
        'cmds': [
            # trazo principal en S
            ('pl', [(0.62, 0.10), (0.54, 0.15), (0.50, 0.28),
                    (0.50, 0.50),
                    (0.50, 0.72), (0.46, 0.85), (0.38, 0.90)]),
        ],
    },

    # 010 — Raíz cuadrada  √
    10: {
        'name': 'Raiz cuadrada',
        'cmds': [
            ('pl', [(0.05, 0.58), (0.22, 0.90),
                    (0.40, 0.12), (0.95, 0.12)]),
            ('ln', 0.95, 0.12, 0.95, 0.28),   # tique derecho
        ],
    },

    # 011 — Mayor  >
    11: {
        'name': 'Mayor',
        'cmds': [
            ('pl', [(0.15, 0.18), (0.85, 0.50), (0.15, 0.82)]),
        ],
    },

    # 012 — Menor  <
    12: {
        'name': 'Menor',
        'cmds': [
            ('pl', [(0.85, 0.18), (0.15, 0.50), (0.85, 0.82)]),
        ],
    },

    # 013 — Límite superior  >|
    13: {
        'name': 'Limite superior',
        'cmds': [
            ('pl', [(0.08, 0.18), (0.72, 0.50), (0.08, 0.82)]),   # >
            ('ln', 0.86, 0.10, 0.86, 0.90),                        # |
        ],
    },

    # 014 — Límite inferior  |<
    14: {
        'name': 'Limite inferior',
        'cmds': [
            ('pl', [(0.92, 0.18), (0.28, 0.50), (0.92, 0.82)]),   # <
            ('ln', 0.14, 0.10, 0.14, 0.90),                        # |
        ],
    },

    # 015 — Comparación  >
    #                    —
    #                    <   (mayor, línea, menor en columna)
    15: {
        'name': 'Comparacion',
        'cmds': [
            # > arriba
            ('pl', [(0.12, 0.08), (0.72, 0.26), (0.12, 0.44)]),
            # — centro
            ('ln', 0.12, 0.50, 0.72, 0.50),
            # < abajo
            ('pl', [(0.72, 0.56), (0.12, 0.74), (0.72, 0.92)]),
        ],
    },

    # 016 — División  ÷  (punto, línea, punto)
    16: {
        'name': 'Division',
        'cmds': [
            ('ln', 0.15, 0.50, 0.85, 0.50),          # línea central
            ('pl', [(0.46, 0.22), (0.50, 0.18),       # punto superior (rombo)
                    (0.54, 0.22), (0.50, 0.26), (0.46, 0.22)]),
            ('pl', [(0.46, 0.74), (0.50, 0.70),       # punto inferior (rombo)
                    (0.54, 0.74), (0.50, 0.78), (0.46, 0.74)]),
        ],
    },
}


# ── Renderizador Qt (QPainter) ────────────────────────────────────────────

def draw_symbol_qt(painter, idx: int, x: float, y: float,
                   w: float, h: float) -> None:
    """
    Dibuja el símbolo idx dentro del rectángulo (x, y, w, h) en coords de escena.
    Llama desde paint() de un QGraphicsItem.
    """
    from PyQt6.QtGui import QPen, QFont, QFontMetrics
    from PyQt6.QtCore import Qt, QPointF

    sym = SYMBOLS.get(idx)
    if not sym:
        return

    pen = painter.pen()   # conservar pluma original

    def _px(nx): return x + nx * w
    def _py(ny): return y + ny * h

    for cmd in sym['cmds']:
        kind = cmd[0]
        if kind == 'pl':
            pts = cmd[1]
            for i in range(len(pts) - 1):
                painter.drawLine(
                    QPointF(_px(pts[i][0]),   _py(pts[i][1])),
                    QPointF(_px(pts[i+1][0]), _py(pts[i+1][1])))
        elif kind == 'ln':
            _, x0, y0, x1, y1 = cmd
            painter.drawLine(
                QPointF(_px(x0), _py(y0)),
                QPointF(_px(x1), _py(y1)))
        elif kind == 'txt':
            _, tx, ty, sz, text, align = cmd
            fs = max(6, int(h * sz))
            f  = QFont('Segoe UI')
            f.setPixelSize(fs)
            painter.setFont(f)
            fm  = QFontMetrics(f)
            tw  = fm.horizontalAdvance(text)
            px  = _px(tx)
            py  = _py(ty)
            if align == 'c':
                px -= tw / 2
            elif align == 'r':
                px -= tw
            painter.drawText(QPointF(px, py), text)

    painter.setPen(pen)


# ── Renderizador DXF ──────────────────────────────────────────────────────

def draw_symbol_dxf(d, idx: int, cx_mm: float, cy_mm: float,
                    w_mm: float, h_mm: float, layer: str) -> None:
    """
    Emite entidades DXF para el símbolo idx centrado en (cx_mm, cy_mm)
    dentro de un área w_mm × h_mm.
    d  — instancia de _D (dxf_export)
    Las coordenadas cx_mm/cy_mm son el CENTRO del área en mm.
    """
    sym = SYMBOLS.get(idx)
    if not sym:
        return

    x0 = cx_mm - w_mm / 2
    y0 = cy_mm - h_mm / 2

    def _mx(nx): return x0 + nx * w_mm
    def _my(ny): return y0 + ny * h_mm

    for cmd in sym['cmds']:
        kind = cmd[0]
        if kind == 'pl':
            pts = cmd[1]
            pts_mm = [(_mx(p[0]), _my(p[1])) for p in pts]
            d.pline(pts_mm, layer)
        elif kind == 'ln':
            _, x0n, y0n, x1n, y1n = cmd
            d.line(_mx(x0n), _my(y0n), _mx(x1n), _my(y1n), layer)
        elif kind == 'txt':
            _, tx, ty, sz, text, align = cmd
            h_txt = h_mm * sz
            px = _mx(tx)
            py = _my(ty)
            if align == 'c':
                d.txt_center(text, px, py, h_txt, layer)
            else:
                d.txt(text, px, py, h_txt, layer)
