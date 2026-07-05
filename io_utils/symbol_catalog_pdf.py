"""
io_utils/symbol_catalog_pdf.py — Exporta el catálogo de símbolos /NNN a PDF.

Genera una tabla de dos columnas: índice | símbolo dibujado
una fila por símbolo, ordenadas por índice.
"""
from __future__ import annotations
from pathlib import Path


def export_symbol_catalog(path: str | Path) -> Path:
    """
    Genera el PDF del catálogo de símbolos en la ruta indicada.
    Devuelve el Path del fichero generado.
    """
    from PyQt6.QtGui import (QPainter, QFont, QPen, QColor,
                              QPageSize, QPageLayout)
    from PyQt6.QtCore import Qt, QRectF, QMarginsF, QSizeF
    from PyQt6.QtPrintSupport import QPrinter
    from symbols import SYMBOLS, draw_symbol_qt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # ── Configurar impresora ──────────────────────────────────────────────
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))

    ps = QPageSize(QPageSize.PageSizeId.A4)
    printer.setPageSize(ps)
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setPageMargins(QMarginsF(15, 15, 15, 15),
                           QPageLayout.Unit.Millimeter)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("No se pudo iniciar QPainter sobre el PDF")

    dpi   = printer.resolution()
    mm_px = dpi / 25.4          # píxeles por mm

    PW = printer.pageRect(QPrinter.Unit.DevicePixel).width()
    PH = printer.pageRect(QPrinter.Unit.DevicePixel).height()

    # ── Métricas de tabla ─────────────────────────────────────────────────
    COL_W    = PW / 2           # dos columnas
    ROW_H    = mm_px * 22       # alto de fila
    HDR_H    = mm_px * 12       # encabezado
    SYM_PAD  = mm_px * 2        # margen interior de la celda del símbolo
    IDX_W    = mm_px * 18       # ancho de la columna de índice

    # ── Fuentes ───────────────────────────────────────────────────────────
    f_title = QFont('Segoe UI'); f_title.setPixelSize(int(mm_px * 6)); f_title.setBold(True)
    f_hdr   = QFont('Segoe UI'); f_hdr.setPixelSize(int(mm_px * 4));   f_hdr.setBold(True)
    f_idx   = QFont('Courier New'); f_idx.setPixelSize(int(mm_px * 4.5))
    f_name  = QFont('Segoe UI'); f_name.setPixelSize(int(mm_px * 3.8))

    pen_grid = QPen(QColor('#AABBCC'), max(1, int(mm_px * 0.3)))
    pen_text = QPen(QColor('#1a2a3a'))
    pen_sym  = QPen(QColor('#334466'), max(2, int(mm_px * 0.5)))
    pen_sym.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen_sym.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    # ── Título ────────────────────────────────────────────────────────────
    painter.setFont(f_title)
    painter.setPen(pen_text)
    title_rect = QRectF(0, 0, PW, HDR_H)
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter,
                     'Catálogo de símbolos gráficos')

    # ── Encabezados de columna ────────────────────────────────────────────
    y_hdr = HDR_H
    for col in range(2):
        ox = col * COL_W
        painter.setPen(pen_grid)
        painter.drawRect(QRectF(ox, y_hdr, IDX_W, mm_px * 7))
        painter.drawRect(QRectF(ox + IDX_W, y_hdr, COL_W - IDX_W, mm_px * 7))
        painter.setFont(f_hdr)
        painter.setPen(pen_text)
        painter.drawText(QRectF(ox, y_hdr, IDX_W, mm_px * 7),
                         Qt.AlignmentFlag.AlignCenter, 'Índice')
        painter.drawText(QRectF(ox + IDX_W, y_hdr, COL_W - IDX_W, mm_px * 7),
                         Qt.AlignmentFlag.AlignCenter, 'Símbolo / Nombre')

    y_start = y_hdr + mm_px * 7
    indices = sorted(SYMBOLS.keys())

    # ── Filas ─────────────────────────────────────────────────────────────
    row_in_page = 0
    max_rows    = int((PH - y_start) / ROW_H)   # filas por página por columna
    page_rows   = max_rows * 2                    # total por página (2 col)

    for pos, idx in enumerate(indices):
        sym  = SYMBOLS[idx]
        page_pos = pos % page_rows
        col      = page_pos // max_rows
        row      = page_pos % max_rows

        # Salto de página
        if pos > 0 and page_pos == 0:
            printer.newPage()

        ox = col * COL_W
        oy = y_start + row * ROW_H

        # Celdas
        painter.setPen(pen_grid)
        painter.drawRect(QRectF(ox, oy, IDX_W, ROW_H))
        painter.drawRect(QRectF(ox + IDX_W, oy, COL_W - IDX_W, ROW_H))

        # Índice  /NNN
        painter.setFont(f_idx)
        painter.setPen(pen_text)
        painter.drawText(
            QRectF(ox, oy, IDX_W, ROW_H),
            Qt.AlignmentFlag.AlignCenter,
            f'/{idx:03d}')

        # Símbolo dibujado (izquierda de la celda derecha)
        sym_cell_h = ROW_H - 2 * SYM_PAD
        sym_size   = min(IDX_W * 1.4, sym_cell_h)
        sx = ox + IDX_W + SYM_PAD
        sy = oy + (ROW_H - sym_size) / 2
        painter.setPen(pen_sym)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        draw_symbol_qt(painter, idx, sx, sy, sym_size, sym_size)

        # Nombre del símbolo (a la derecha del dibujo)
        name_x = sx + sym_size + SYM_PAD
        name_w = (ox + COL_W) - name_x - SYM_PAD
        if name_w > mm_px * 5:
            painter.setFont(f_name)
            painter.setPen(pen_text)
            painter.drawText(
                QRectF(name_x, oy, name_w, ROW_H),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                sym['name'])

    painter.end()
    return path
