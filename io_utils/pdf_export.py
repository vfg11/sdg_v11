"""
io_utils/pdf_export.py — Exportar a PDF con portada y márgenes.

- export_pdf()          → hoja activa, con márgenes
- export_pdf_all()      → portada + todas las hojas, con márgenes
- export_svg()
- print_dialog()
"""
from __future__ import annotations
from pathlib import Path
from PyQt6.QtGui import QPainter, QPageSize, QPageLayout, QFont, QColor
from PyQt6.QtCore import QRectF, QMarginsF, Qt
from const import PAGE_W, PAGE_H, PDF_MARGIN


def _layout() -> QPageLayout:
    return QPageLayout(
        QPageSize(QPageSize.PageSizeId.A3),
        QPageLayout.Orientation.Landscape,
        QMarginsF(0, 0, 0, 0),
    )


# ── Exportar hoja activa ──────────────────────────────────────────────────

def export_pdf(scene, path: str | Path):
    from PyQt6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(_layout())

    painter = QPainter(printer)
    _render_sheet(painter, scene)
    painter.end()


# ── Exportar todas las hojas (portada + páginas con márgenes) ────────────

def export_pdf_all(document, base_scene, path: str | Path):
    """
    document   : DocumentData
    base_scene : DiagramScene ya inicializada (se reutiliza para renderizar cada hoja)
    path       : ruta del PDF de salida
    """
    from PyQt6.QtPrintSupport import QPrinter
    from scene import DiagramScene

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(_layout())

    painter = QPainter(printer)
    first   = True

    # ── Portada ──
    if document.cover.show:
        if not first: printer.newPage()
        _render_cover(painter, document)
        first = False

    # ── Índice ──
    if not first: printer.newPage()
    _render_index(painter, document)
    first = False

    # ── Hojas ──
    tmp = DiagramScene()
    for i in range(document.sheet_count()):
        if not first: printer.newPage()
        tmp.load_sheet(document, i)
        _render_sheet(painter, tmp)
        first = False

    painter.end()


# ── Renderizado de una hoja con márgenes ─────────────────────────────────

def _render_sheet(painter: QPainter, scene):
    """Renderiza la escena dejando PDF_MARGIN de margen blanco alrededor."""
    vp  = QRectF(painter.viewport())           # tamaño total del papel en device px
    # Área de contenido = viewport reducido por los márgenes proporcionales
    mx  = vp.width()  * (PDF_MARGIN / PAGE_W)
    my  = vp.height() * (PDF_MARGIN / PAGE_H)
    content_rect = vp.adjusted(mx, my, -mx, -my)

    # Fondo blanco completo (margen en blanco)
    painter.fillRect(vp, QColor('#FFFFFF'))

    # Renderizar escena en el área de contenido
    scene.render(painter, content_rect, QRectF(0, 0, PAGE_W, PAGE_H))


# ── Portada ───────────────────────────────────────────────────────────────

def _render_cover(painter: QPainter, document):
    """Dibuja una portada sencilla con los datos del cajetín."""
    from PyQt6.QtGui import QLinearGradient, QBrush

    vp  = QRectF(painter.viewport())
    tb  = document.title_block
    cv  = document.cover

    # Fondo
    painter.fillRect(vp, QColor('#FFFFFF'))

    # Banda de color superior (40% del alto)
    band_h = vp.height() * 0.40
    grad   = QLinearGradient(0, 0, 0, band_h)
    grad.setColorAt(0, QColor('#1A2A4A'))
    grad.setColorAt(1, QColor('#2A4A7A'))
    painter.fillRect(QRectF(0, 0, vp.width(), band_h), QBrush(grad))

    # Línea decorativa bajo la banda
    painter.setPen(QColor('#E05500'))
    lw = vp.height() * 0.006
    painter.fillRect(QRectF(0, band_h, vp.width(), lw), QColor('#E05500'))

    px_w = vp.width()

    def draw_centered(text, y, px_size, bold=False, color='#FFFFFF'):
        if not text: return
        f = QFont('Segoe UI', 1)
        f.setPixelSize(int(px_size)); f.setBold(bold)
        painter.setFont(f)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(px_w * 0.1, y, px_w * 0.8, px_size * 2.2),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         text)

    def draw_left(text, y, px_size, bold=False, color='#334455'):
        if not text: return
        f = QFont('Segoe UI', 1)
        f.setPixelSize(int(px_size)); f.setBold(bold)
        painter.setFont(f)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(px_w * 0.1, y, px_w * 0.8, px_size * 2.2),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         text)

    # Empresa (parte superior de la banda)
    draw_centered(tb.company, vp.height() * 0.06,
                  vp.height() * 0.032, color='#AABBCC')

    # Título principal
    draw_centered(tb.title, vp.height() * 0.14,
                  vp.height() * 0.065, bold=True, color='#FFFFFF')

    # Subtítulo
    if cv.subtitle:
        draw_centered(cv.subtitle, vp.height() * 0.24,
                      vp.height() * 0.035, color='#CCE0FF')

    # Descripción (bajo la banda)
    if cv.description:
        y0 = band_h + lw + vp.height() * 0.05
        f  = QFont('Segoe UI', 1)
        f.setPixelSize(int(vp.height() * 0.028))
        painter.setFont(f)
        painter.setPen(QColor('#445566'))
        painter.drawText(
            QRectF(px_w * 0.1, y0, px_w * 0.8, vp.height() * 0.25),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap,
            cv.description)

    # Bloque de metadatos abajo a la derecha
    meta_y   = vp.height() * 0.70
    meta_gap = vp.height() * 0.042
    meta_px  = vp.height() * 0.028
    for lbl, val in [
        ('Documento:',  tb.doc_number),
        ('Proyecto:',   tb.project),
        ('Planta:',     tb.plant),
        ('Revisión:',   f'{tb.revision}  {tb.date}'),
    ]:
        draw_left(f'{lbl}  {val}', meta_y, meta_px, color='#556677')
        meta_y += meta_gap

    # Firmas en la parte inferior (sin separador — pisaba el texto de revisión)
    firma_y  = vp.height() * 0.88
    firma_px = vp.height() * 0.024
    for role, name in [('Elaborado:', tb.drawn_by),
                       ('Revisado:',  tb.checked_by),
                       ('Aprobado:',  tb.approved_by)]:
        if name:
            draw_left(f'{role}  {name}', firma_y, firma_px, color='#667788')
            firma_y += firma_px * 2.2

    # Número de hojas
    draw_centered(
        f'{document.sheet_count()} hoja{"s" if document.sheet_count()>1 else ""}',
        vp.height() * 0.92, vp.height() * 0.024, color='#889AAB')



def _render_index(painter: QPainter, document):
    """Dibuja una página de índice con una fila por hoja: Nº | KKS | Título."""
    from PyQt6.QtGui import QFont as _QF, QPen as _QP

    vp    = QRectF(painter.viewport())
    tb    = document.title_block
    pw    = vp.width()
    ph    = vp.height()
    marg  = pw * 0.08

    # ── Fondo ──
    painter.fillRect(vp, QColor('#FFFFFF'))

    # ── Cabecera ──
    hdr_h = ph * 0.07
    painter.fillRect(QRectF(0, 0, pw, hdr_h), QColor('#1A2A4A'))
    f = _QF('Segoe UI', 1); f.setPixelSize(int(ph * 0.032)); f.setBold(True)
    painter.setFont(f); painter.setPen(QColor('#FFFFFF'))
    painter.drawText(QRectF(marg, 0, pw - 2*marg, hdr_h),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     'ÍNDICE DEL DOCUMENTO')
    # Número de documento a la derecha
    f2 = _QF('Segoe UI', 1); f2.setPixelSize(int(ph * 0.022))
    painter.setFont(f2)
    painter.drawText(QRectF(0, 0, pw - marg, hdr_h),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     tb.doc_number)

    # ── Cabecera de columnas ──
    row_h   = ph * 0.042
    col_y   = hdr_h + ph * 0.015
    col_num = pw * 0.10    # ancho col Nº hoja
    col_kks = pw * 0.25    # ancho col KKS
    # col título ocupa el resto
    col_x0  = marg

    painter.fillRect(QRectF(col_x0, col_y, pw - 2*marg, row_h), QColor('#E8EEF8'))
    f_hdr = _QF('Segoe UI', 1); f_hdr.setPixelSize(int(ph * 0.022)); f_hdr.setBold(True)
    painter.setFont(f_hdr); painter.setPen(QColor('#1A2A4A'))

    def draw_col(text, x, w, y, h, align=Qt.AlignmentFlag.AlignLeft):
        pad = pw * 0.01
        painter.drawText(QRectF(x + pad, y, w - 2*pad, h),
                         Qt.AlignmentFlag.AlignVCenter | align, text)

    draw_col('Hoja',   col_x0,               col_num, col_y, row_h,
             Qt.AlignmentFlag.AlignHCenter)
    draw_col('KKS',    col_x0 + col_num,     col_kks, col_y, row_h)
    draw_col('Título', col_x0 + col_num + col_kks,
             pw - 2*marg - col_num - col_kks, col_y, row_h)

    # ── Línea separadora ──
    painter.setPen(_QP(QColor('#AABBCC'), ph * 0.002))
    sep_y = col_y + row_h
    painter.drawLine(int(col_x0), int(sep_y), int(pw - marg), int(sep_y))

    # ── Filas de hojas ──
    f_row = _QF('Segoe UI', 1); f_row.setPixelSize(int(ph * 0.022))
    f_row_b = _QF('Segoe UI', 1); f_row_b.setPixelSize(int(ph * 0.022)); f_row_b.setBold(True)

    y_cur = sep_y + row_h * 0.3
    row_max = int((ph - y_cur - marg) / row_h)

    for flat_i, (sheet, group) in enumerate(document.flat_sheets()):
        if flat_i >= row_max:
            break   # seguridad: no salir del margen
        num_str = document.sheet_ref(flat_i)
        kks_str = group.kks or ''
        title   = group.title_for_sheet(
            sum(1 for j, (_, g2) in enumerate(document.flat_sheets())
                if j < flat_i and g2.group_id == group.group_id)
        )
        # Alternar color de fila
        if flat_i % 2 == 0:
            painter.fillRect(QRectF(col_x0, y_cur, pw - 2*marg, row_h),
                             QColor('#F5F8FF'))

        painter.setPen(QColor('#223344'))
        painter.setFont(f_row_b)
        draw_col(f'H{int(num_str):02d}', col_x0, col_num, y_cur, row_h,
                 Qt.AlignmentFlag.AlignHCenter)
        painter.setFont(f_row)
        draw_col(kks_str,  col_x0 + col_num, col_kks, y_cur, row_h)
        draw_col(title,    col_x0 + col_num + col_kks,
                 pw - 2*marg - col_num - col_kks, y_cur, row_h)
        y_cur += row_h

    # ── Pie ──
    painter.setPen(_QP(QColor('#CCDDEE'), ph * 0.002))
    painter.drawLine(int(marg), int(ph - ph*0.05),
                     int(pw - marg), int(ph - ph*0.05))
    f_foot = _QF('Segoe UI', 1); f_foot.setPixelSize(int(ph * 0.020))
    painter.setFont(f_foot); painter.setPen(QColor('#889AAB'))
    painter.drawText(QRectF(marg, ph - ph*0.05, pw - 2*marg, ph*0.04),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     f'{document.sheet_count()} hoja{"s" if document.sheet_count()>1 else ""}')


# ── SVG ───────────────────────────────────────────────────────────────────

def export_svg(scene, path: str | Path):
    from PyQt6.QtSvg import QSvgGenerator
    from PyQt6.QtCore import QSize

    gen = QSvgGenerator()
    gen.setFileName(str(path))
    gen.setSize(QSize(int(PAGE_W), int(PAGE_H)))
    gen.setViewBox(QRectF(0, 0, PAGE_W, PAGE_H))
    gen.setTitle('Diagrama de señales')

    painter = QPainter(gen)
    scene.render(painter, QRectF(0, 0, PAGE_W, PAGE_H),
                 QRectF(0, 0, PAGE_W, PAGE_H))
    painter.end()


# ── Imprimir ──────────────────────────────────────────────────────────────

def print_dialog(scene, parent=None):
    from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageLayout(_layout())
    dlg = QPrintDialog(printer, parent)
    if dlg.exec():
        painter = QPainter(printer)
        _render_sheet(painter, scene)
        painter.end()
