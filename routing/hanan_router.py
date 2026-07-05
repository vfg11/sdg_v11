"""
routing/hanan_router.py — Router ortogonal Hanan-grid + A*

FUNDAMENTO
----------
El teorema de Hanan garantiza que la solución óptima de rutado rectilíneo
siempre existe en la rejilla formada por las líneas X e Y que pasan por
las esquinas de los obstáculos y los puntos de inicio/fin.

COSTES DE ARISTA
----------------
- Longitud del segmento (Manhattan)
- COST_CROSS: penalización por cruzar una conexión existente
- COST_NEAR:  penalización por ir paralelo y cerca de otra ruta
- COST_TURN:  pequeña penalización por cambio de dirección

ENTRADA
-------
route(src, dst, obstacles, existing_paths, canvas) -> list[(x,y)]
  src, dst          — (x, y) en unidades internas
  obstacles         — list of (x0,y0,x1,y1) — bloques expandidos
  existing_paths    — list of list[(x,y)] — rutas ya dibujadas
  canvas            — (x0, y0, x1, y1) — límites del canvas

SALIDA
------
Lista de puntos (x, y) del camino óptimo, simplificada.
"""
from __future__ import annotations
import heapq

COST_CROSS   = 800.0
COST_NEAR    = 300.0
COST_TURN    = 20.0
NEAR_THRESH  = 60.0   # ~6 mm — umbral mayor para detectar paralelas cercanas
PAD_OBSTACLE = 35.0   # ~3.5 mm
_TOL         = 1.0

# Límite duro de nodos expandidos: evita freeze con grafos grandes
_MAX_NODES   = 4000


# ── Geometría de segmentos ─────────────────────────────────────────────────

def _is_h(x0, y0, x1, y1): return abs(y1 - y0) < _TOL
def _is_v(x0, y0, x1, y1): return abs(x1 - x0) < _TOL


def _crosses(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1) -> bool:
    """True si los dos segmentos ortogonales se cruzan (no sólo se tocan)."""
    ah = _is_h(ax0, ay0, ax1, ay1)
    bh = _is_h(bx0, by0, bx1, by1)
    if ah == bh:
        return False
    if ah:
        hx0, hx1, hy = min(ax0,ax1), max(ax0,ax1), ay0
        vx, vy0, vy1 = bx0, min(by0,by1), max(by0,by1)
    else:
        hx0, hx1, hy = min(bx0,bx1), max(bx0,bx1), by0
        vx, vy0, vy1 = ax0, min(ay0,ay1), max(ay0,ay1)
    return (hx0 + _TOL < vx < hx1 - _TOL and
            vy0 + _TOL < hy < vy1 - _TOL)


def _near_parallel(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1, thresh) -> bool:
    """True si ambos son paralelos, cercanos y se solapan en su proyección."""
    ah = _is_h(ax0, ay0, ax1, ay1)
    bh = _is_h(bx0, by0, bx1, by1)
    if ah != bh:
        return False
    if ah:
        if abs(ay0 - by0) > thresh:
            return False
        return (max(min(ax0,ax1), min(bx0,bx1)) <
                min(max(ax0,ax1), max(bx0,bx1)) - _TOL)
    else:
        if abs(ax0 - bx0) > thresh:
            return False
        return (max(min(ay0,ay1), min(by0,by1)) <
                min(max(ay0,ay1), max(by0,by1)) - _TOL)


def _blocked_by_rect(sx0, sy0, sx1, sy1, rx0, ry0, rx1, ry1) -> bool:
    """True si el segmento pasa por el interior del rectángulo."""
    if _is_h(sx0, sy0, sx1, sy1):
        if not (ry0 < sy0 < ry1):
            return False
        x0, x1 = min(sx0,sx1), max(sx0,sx1)
        return x0 < rx1 and x1 > rx0
    else:
        if not (rx0 < sx0 < rx1):
            return False
        y0, y1 = min(sy0,sy1), max(sy0,sy1)
        return y0 < ry1 and y1 > ry0


# ── Rejilla Hanan ──────────────────────────────────────────────────────────

# Límite de líneas de la rejilla para mantener el grafo manejable
_MAX_GRID_LINES = 24

def _build_grid(src, dst, obstacles, canvas):
    cx0, cy0, cx1, cy1 = canvas
    xs = {cx0, cx1, src[0], dst[0]}
    ys = {cy0, cy1, src[1], dst[1]}
    for (ox0, oy0, ox1, oy1) in obstacles:
        for x in (ox0 - PAD_OBSTACLE, ox0, ox1, ox1 + PAD_OBSTACLE):
            if cx0 <= x <= cx1:
                xs.add(round(x))
        for y in (oy0 - PAD_OBSTACLE, oy0, oy1, oy1 + PAD_OBSTACLE):
            if cy0 <= y <= cy1:
                ys.add(round(y))

    xs = sorted(xs)
    ys = sorted(ys)

    # Si la rejilla es muy grande, reducirla manteniendo src, dst y los
    # obstáculos más relevantes (los más cercanos al segmento src→dst)
    def _thin(lst, keep, maxn):
        if len(lst) <= maxn:
            return lst
        keep_set = set(keep)
        others   = [v for v in lst if v not in keep_set]
        # Submuestrear uniformemente los que no son obligatorios
        step = max(1, len(others) // (maxn - len(keep_set)))
        sampled = others[::step]
        combined = sorted(keep_set | set(sampled))
        return combined[:maxn]

    xs = _thin(xs, {cx0, cx1, src[0], dst[0]}, _MAX_GRID_LINES)
    ys = _thin(ys, {cy0, cy1, src[1], dst[1]}, _MAX_GRID_LINES)
    return xs, ys


# ── A* ────────────────────────────────────────────────────────────────────

def route(src, dst, obstacles, existing_paths, canvas):
    """Retorna list[(x,y)] — la ruta óptima ortogonal de src a dst."""
    xs, ys = _build_grid(src, dst, obstacles, canvas)
    if len(xs) < 2 or len(ys) < 2:
        return [src, dst]

    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}

    def snap(v, lst):
        return min(lst, key=lambda a: abs(a - v))

    sx, sy = snap(src[0], xs), snap(src[1], ys)
    dx, dy = snap(dst[0], xs), snap(dst[1], ys)
    start  = (xi[sx], yi[sy])
    goal   = (xi[dx], yi[dy])

    if start == goal:
        return [src, dst]

    # Pre-computar segmentos existentes como tuplas planas
    ex_segs = []
    for path in existing_paths:
        for i in range(len(path) - 1):
            ex_segs.append((path[i][0], path[i][1],
                             path[i+1][0], path[i+1][1]))

    # Pre-computar obstáculos expandidos
    obs = obstacles[:]

    NX, NY = len(xs), len(ys)

    def edge_cost(ix0, iy0, ix1, iy1, ldx, ldy):
        x0, y0 = xs[ix0], ys[iy0]
        x1, y1 = xs[ix1], ys[iy1]
        length = abs(x1 - x0) + abs(y1 - y0)
        if length < _TOL:
            return 0.0

        # Obstáculos
        for (ox0, oy0, ox1, oy1) in obs:
            if _blocked_by_rect(x0, y0, x1, y1, ox0, oy0, ox1, oy1):
                return None   # bloqueado

        cost = length

        # Penalizaciones
        for (ex0, ey0, ex1, ey1) in ex_segs:
            if _crosses(x0, y0, x1, y1, ex0, ey0, ex1, ey1):
                cost += COST_CROSS
            elif _near_parallel(x0, y0, x1, y1, ex0, ey0, ex1, ey1,
                                 NEAR_THRESH):
                cost += COST_NEAR

        # Giro
        cdx = 1 if x1 > x0 else (-1 if x1 < x0 else 0)
        cdy = 1 if y1 > y0 else (-1 if y1 < y0 else 0)
        if ldx is not None and (cdx, cdy) != (ldx, ldy):
            cost += COST_TURN

        return cost

    def h(ix, iy):
        return abs(xs[ix] - xs[goal[0]]) + abs(ys[iy] - ys[goal[1]])

    INF    = float('inf')
    dist   = {}
    prev   = {}
    state0 = (*start, None, None)
    dist[state0] = 0.0
    heap = [(h(*start), 0.0, state0)]
    nodes_expanded = 0

    while heap:
        _, g, state = heapq.heappop(heap)
        ix, iy, ldx, ldy = state

        if g > dist.get(state, INF) + _TOL:
            continue

        nodes_expanded += 1
        if nodes_expanded > _MAX_NODES:
            # Fallback rápido si el grafo es demasiado grande
            break

        if (ix, iy) == goal:
            # Reconstruir camino
            path_st = []
            cur = state
            while cur in prev:
                path_st.append(cur)
                cur = prev[cur]
            path_st.append(cur)
            path_st.reverse()
            pts = [(xs[s[0]], ys[s[1]]) for s in path_st]
            if pts:
                pts[0]  = src
                pts[-1] = dst
            return _simplify(pts)

        for ddx, ddy in ((1,0),(-1,0),(0,1),(0,-1)):
            nix, niy = ix + ddx, iy + ddy
            if not (0 <= nix < NX and 0 <= niy < NY):
                continue
            c = edge_cost(ix, iy, nix, niy, ldx, ldy)
            if c is None:
                continue
            ng     = g + c
            nstate = (nix, niy, ddx, ddy)
            if ng < dist.get(nstate, INF) - _TOL:
                dist[nstate] = ng
                prev[nstate] = state
                heapq.heappush(heap, (ng + h(nix, niy), ng, nstate))

    # Fallback
    return _simplify([src, (dst[0], src[1]), dst])


def _simplify(pts):
    if len(pts) <= 2:
        return list(pts)
    result = [pts[0]]
    for i in range(1, len(pts) - 1):
        px, py = result[-1]
        cx, cy = pts[i]
        nx, ny = pts[i + 1]
        if abs(cx - px) < _TOL and abs(nx - cx) < _TOL:
            continue
        if abs(cy - py) < _TOL and abs(ny - cy) < _TOL:
            continue
        result.append(pts[i])
    result.append(pts[-1])
    return result
