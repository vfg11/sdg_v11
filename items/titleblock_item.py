"""
items/titleblock_item.py — Cajetín de rótulo inferior.

Estructura corregida:
  Col 0  Empresa       ┐
  Col 1  Título        ├ divididas en 2 filas horizontales (línea media solo hasta col 4)
  Col 2  Doc / Rev     │
  Col 3  Proyecto/Planta┘
  Col 4  Firmas         → dividida en 3 filas propias (sin línea media de las anteriores)
  Col 5  Nº hoja        → numeración libre, sin "de X"

Título de hoja: editable por hoja (sheet_title), mostrado en col 1 fila inferior.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (QGraphicsItemGroup, QGraphicsRectItem,
                              QGraphicsTextItem, QGraphicsLineItem)
from PyQt6.QtGui import QPen, QBrush, QColor, QFont
from PyQt6.QtCore import QRectF
from const import (PAGE_W, PAGE_H, TB_H, TB_Y, TB_COL_FRACS,
                   COLOR_TB_BG, COLOR_TB_BORDER, COLOR_TB_LINE,
                   F_TB_FIELD_LBL, F_TB_VALUE, F_TB_TITLE, F_TB_SHEET, mm)
from model import TitleBlockData, SheetData


def _f(px: int, bold=False, mono=False) -> QFont:
    f = QFont('Courier New' if mono else 'Segoe UI')
    f.setPixelSize(px)
    if bold: f.setBold(True)
    return f


class TitleBlockItem(QGraphicsItemGroup):

    def __init__(self, tb: TitleBlockData, sheet: SheetData, sheet_idx: int, document=None):
        super().__init__()
        self.tb         = tb
        self.sheet      = sheet
        self.sheet_idx  = sheet_idx
        self.document   = document
        self.setZValue(20)
        self._build()

    def _build(self):
        bpen = QPen(QColor(COLOR_TB_BORDER), mm(0.6))
        epen = QPen(QColor(COLOR_TB_LINE),   mm(0.3))

        # Fondo
        bg = QGraphicsRectItem(0, TB_Y, PAGE_W, TB_H)
        bg.setPen(bpen); bg.setBrush(QBrush(QColor(COLOR_TB_BG)))
        self.addToGroup(bg)

        # Calcular posiciones X de columnas
        xs = [0.0]
        for frac in TB_COL_FRACS:
            xs.append(xs[-1] + PAGE_W * frac)

        # Divisores verticales (todos)
        for x in xs[1:-1]:
            self.addToGroup(self._vline(x, bpen if x == xs[-2] else epen))

        # Línea horizontal media: SOLO columnas 0-3 (hasta xs[4])
        mid_y = TB_Y + TB_H / 2
        self.addToGroup(self._hline(xs[0], mid_y, xs[4], mid_y, epen))

        h1  = TB_H / 2
        pad = mm(2)

        # ── Col 0: Empresa ──────────────────────────────────────────────
        self._cell(xs[0], TB_Y,   xs[1]-xs[0], h1, 'EMPRESA',
                   self.tb.company, pad, bold=True)
        # fila inferior vacía (o logo si hubiera)

        # ── Col 1: Título documento (arriba) / Título hoja (abajo) ──────
        self._cell(xs[1], TB_Y,   xs[2]-xs[1], h1,
                   'TÍTULO DEL DOCUMENTO', self.tb.title, pad,
                   val_px=F_TB_TITLE, bold=True)
        if self.sheet.sheet_title:
            sheet_title = self.sheet.sheet_title
        elif self.document:
            g = self.document.group_at(self.sheet_idx)
            if g:
                flat = self.document.flat_sheets()
                li = sum(1 for i, (_, g2) in enumerate(flat)
                         if i < self.sheet_idx and g2.group_id == g.group_id)
                sheet_title = g.title_for_sheet(li)
            else:
                sheet_title = self.sheet.sheet_name
        else:
            sheet_title = self.sheet.sheet_name
        self._cell(xs[1], mid_y, xs[2]-xs[1], h1,
                   'TÍTULO DE HOJA', sheet_title, pad)

        # ── Col 2: Doc / Rev ─────────────────────────────────────────────
        self._cell(xs[2], TB_Y,   xs[3]-xs[2], h1,
                   'Nº DOCUMENTO', self.tb.doc_number, pad, bold=True, mono=True)
        self._cell(xs[2], mid_y, xs[3]-xs[2], h1,
                   'REV. / FECHA',
                   f'{self.tb.revision}  {self.tb.date}', pad)

        # ── Col 3: Proyecto / Planta ──────────────────────────────────────
        self._cell(xs[3], TB_Y,   xs[4]-xs[3], h1,
                   'PROYECTO', self.tb.project, pad, bold=True)
        self._cell(xs[3], mid_y, xs[4]-xs[3], h1,
                   'PLANTA / INSTALACIÓN', self.tb.plant, pad)

        # ── Col 4: Firmas — 3 filas propias ─────────────────────────────
        x0, x1 = xs[4], xs[5]
        sub_h = TB_H / 3
        roles = [('ELABORADO POR', self.tb.drawn_by),
                 ('REVISADO POR',  self.tb.checked_by),
                 ('APROBADO POR',  self.tb.approved_by)]
        for k in range(1, 3):
            sy = TB_Y + k * sub_h
            self.addToGroup(self._hline(x0, sy, x1, sy, epen))
        for k, (role, person) in enumerate(roles):
            sy = TB_Y + k * sub_h
            self._cell(x0, sy, x1-x0, sub_h, role, person, pad)

        # ── Col 5: Nº hoja (numeración libre, sin "de X") ─────────────
        x0, x1 = xs[5], xs[6]
        w5 = x1 - x0
        self._label_t(x0+pad, TB_Y+mm(1.5), 'HOJA')
        if self.document:
            num = self.document.sheet_ref(self.sheet_idx)
        elif self.sheet.sheet_number:
            num = self.sheet.sheet_number
        else:
            num = str(self.sheet_idx + 1)
        self._value_centered(x0, TB_Y + mm(1.5) + F_TB_FIELD_LBL + mm(1),
                             w5, num, F_TB_SHEET, bold=True)

    # ── helpers ───────────────────────────────────────────────────────────

    def _cell(self, cx, cy, cw, ch, lbl, val, pad,
              val_px=None, bold=False, mono=False):
        self._label_t(cx+pad, cy+mm(1.2), lbl)
        if val:
            px = val_px if val_px else F_TB_VALUE
            t = QGraphicsTextItem(val)
            t.setFont(_f(px, bold=bold, mono=mono))
            t.setDefaultTextColor(QColor('#1a2a4a'))
            t.setTextWidth(cw - 2*pad)
            t.setPos(cx+pad, cy + mm(1.2) + F_TB_FIELD_LBL + mm(1))
            self.addToGroup(t)

    def _label_t(self, x, y, text):
        t = QGraphicsTextItem(text)
        t.setFont(_f(F_TB_FIELD_LBL))
        t.setDefaultTextColor(QColor('#667788'))
        t.setPos(x, y)
        self.addToGroup(t)

    def _value_centered(self, col_x, y, col_w, text, px, bold=False):
        t = QGraphicsTextItem(text)
        t.setFont(_f(px, bold=bold))
        t.setDefaultTextColor(QColor('#1a2a4a'))
        t.setPos(col_x + (col_w - t.boundingRect().width()) / 2, y)
        self.addToGroup(t)

    def _vline(self, x, pen):
        l = QGraphicsLineItem(x, TB_Y, x, PAGE_H)
        l.setPen(pen); return l

    def _hline(self, x1, y1, x2, y2, pen):
        l = QGraphicsLineItem(x1, y1, x2, y2)
        l.setPen(pen); return l

    def rebuild(self, sheet: SheetData, sheet_idx: int):
        self.sheet     = sheet
        self.sheet_idx = sheet_idx
        for item in self.childItems():
            self.removeFromGroup(item)
        self._build()
