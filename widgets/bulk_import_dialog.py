"""
widgets/bulk_import_dialog.py — Diálogo de importación masiva de grupos.

Flujo:
  1. El usuario selecciona el fichero Excel con los pares origen/destino.
  2. Opcionalmente selecciona un documento .sde origen (típicos).
     Si se deja vacío, los grupos origen se buscan en el documento actual.
  3. Pulsa "Previsualizar" → se parsea el Excel, se valida, se muestra tabla.
  4. Si no hay errores, pulsa "Ejecutar importación".
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialogButtonBox,
    QProgressBar, QTextEdit, QFrame, QFileDialog, QSizePolicy,
    QMessageBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont


class BulkImportDialog(QDialog):
    """
    Diálogo unificado: selección de ficheros + previsualización + ejecución.
    """

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc       = doc
        self._ops      = []
        self._errors   = []
        self._worker   = None
        self._new_gids: list[str] = []

        self.setWindowTitle("Importación masiva de grupos")
        self.setMinimumSize(880, 640)
        self._build()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # ── Selectores de fichero ─────────────────────────────────────────
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Excel
        hb_xls = QHBoxLayout()
        self._edit_xls = QLineEdit()
        self._edit_xls.setPlaceholderText("Selecciona el fichero Excel de clonación…")
        self._edit_xls.setReadOnly(True)
        btn_xls = QPushButton("Examinar…")
        btn_xls.setFixedWidth(90)
        btn_xls.clicked.connect(self._browse_excel)
        hb_xls.addWidget(self._edit_xls)
        hb_xls.addWidget(btn_xls)
        form.addRow("Fichero Excel:", hb_xls)

        # Doc origen (opcional)
        hb_src = QHBoxLayout()
        self._edit_src = QLineEdit()
        self._edit_src.setPlaceholderText(
            "Opcional — vacío = clonar desde el documento actual")
        self._edit_src.setReadOnly(True)
        btn_src = QPushButton("Examinar…")
        btn_src.setFixedWidth(90)
        btn_src.clicked.connect(self._browse_src)
        btn_clr = QPushButton("✕")
        btn_clr.setFixedWidth(28)
        btn_clr.setToolTip("Limpiar — usar documento actual como origen")
        btn_clr.clicked.connect(lambda: self._edit_src.clear())
        hb_src.addWidget(self._edit_src)
        hb_src.addWidget(btn_src)
        hb_src.addWidget(btn_clr)
        form.addRow("Documento origen:", hb_src)

        lay.addLayout(form)

        # ── Botón previsualizar ───────────────────────────────────────────
        hb_prev = QHBoxLayout()
        self._btn_preview = QPushButton("🔍  Previsualizar")
        self._btn_preview.setStyleSheet(
            "background:#2E4057; color:white; font-weight:bold; padding:6px 18px;")
        self._btn_preview.clicked.connect(self._on_preview)
        hb_prev.addWidget(self._btn_preview)
        hb_prev.addStretch()
        lay.addLayout(hb_prev)

        # ── Separador ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(sep)

        # ── Zona de resultados (inicialmente vacía) ───────────────────────
        self._lbl_summary = QLabel("— Selecciona los ficheros y pulsa Previsualizar —")
        self._lbl_summary.setStyleSheet("color:#666; font-style:italic; padding:4px;")
        lay.addWidget(self._lbl_summary)

        # Tabla de operaciones
        self._tbl = QTableWidget(0, 6)
        self._tbl.setHorizontalHeaderLabels(
            ["Par", "KKS origen", "KKS destino",
             "Descripción destino", "Hoja destino", "Reglas"])
        self._tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        for col in (0, 4, 5):
            self._tbl.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._tbl, stretch=3)

        # Panel de errores
        self._frm_errors = QFrame()
        self._frm_errors.setFrameShape(QFrame.Shape.StyledPanel)
        self._frm_errors.setStyleSheet(
            "QFrame{background:#FFF0F0;border:1px solid #C00;"
            "border-radius:4px;padding:4px;}")
        frm_lay = QVBoxLayout(self._frm_errors)
        frm_lay.setContentsMargins(6, 4, 6, 4)
        self._lbl_err_title = QLabel()
        frm_lay.addWidget(self._lbl_err_title)
        self._txt_errors = QTextEdit()
        self._txt_errors.setReadOnly(True)
        self._txt_errors.setMaximumHeight(100)
        self._txt_errors.setStyleSheet(
            "font-family:Consolas,monospace; font-size:9pt;")
        frm_lay.addWidget(self._txt_errors)
        self._frm_errors.setVisible(False)
        lay.addWidget(self._frm_errors)

        # Advertencia de commit
        self._lbl_warn = QLabel(
            "⚠  <b>Atención:</b> antes de ejecutar se guardará el estado "
            "actual del documento. La operación no se puede deshacer con Ctrl+Z. "
            "Si algo falla se realizará un <b>rollback automático</b>.")
        self._lbl_warn.setWordWrap(True)
        self._lbl_warn.setStyleSheet(
            "background:#FFFBE6;border:1px solid #E6C200;"
            "border-radius:4px;padding:8px;color:#5C4A00;")
        self._lbl_warn.setVisible(False)
        lay.addWidget(self._lbl_warn)

        # Progreso
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        lay.addWidget(self._progress)
        self._lbl_prog = QLabel()
        self._lbl_prog.setVisible(False)
        self._lbl_prog.setStyleSheet("color:#1a6e3c; font-weight:bold;")
        lay.addWidget(self._lbl_prog)

        # ── Botones ───────────────────────────────────────────────────────
        bb = QDialogButtonBox()
        self._btn_exec = bb.addButton(
            "✅  Ejecutar importación",
            QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_exec.setStyleSheet(
            "background:#1a6e3c;color:white;font-weight:bold;padding:6px 16px;")
        self._btn_exec.setEnabled(False)
        self._btn_exec.clicked.connect(self._on_execute)
        self._btn_cancel = bb.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._btn_cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    # ── Selectores ───────────────────────────────────────────────────────

    def _browse_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar fichero Excel", "",
            "Excel (*.xlsx *.xls)")
        if path:
            self._edit_xls.setText(path)
            self._reset_preview()

    def _browse_src(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar documento origen", "",
            "Signal Diagram (*.sde);;Todos los ficheros (*)")
        if path:
            self._edit_src.setText(path)
            self._reset_preview()

    def _reset_preview(self):
        self._ops = []
        self._errors = []
        self._tbl.setRowCount(0)
        self._frm_errors.setVisible(False)
        self._lbl_warn.setVisible(False)
        self._btn_exec.setEnabled(False)
        self._lbl_summary.setText(
            "— Selecciona los ficheros y pulsa Previsualizar —")
        self._lbl_summary.setStyleSheet(
            "color:#666; font-style:italic; padding:4px;")

    # ── Previsualización ─────────────────────────────────────────────────

    def _on_preview(self):
        xls_path = self._edit_xls.text().strip()
        src_path = self._edit_src.text().strip() or None

        if not xls_path:
            QMessageBox.warning(self, "Fichero requerido",
                                "Selecciona el fichero Excel de clonación.")
            return

        from io_utils.bulk_clone import parse_bulk_excel, validate_bulk, BulkParseError

        # Parsear Excel
        try:
            ops = parse_bulk_excel(xls_path)
        except BulkParseError as e:
            QMessageBox.critical(self, "Error al leer el Excel", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Error inesperado", str(e))
            return

        if not ops:
            QMessageBox.information(
                self, "Sin operaciones",
                "El fichero no contiene pares de clonación válidos.")
            return

        # Abrir BD origen si se especificó
        src_con = None
        if src_path:
            try:
                import sqlite3
                src_con = sqlite3.connect(src_path, check_same_thread=False)
                src_con.row_factory = sqlite3.Row
            except Exception as e:
                QMessageBox.critical(
                    self, "Error al abrir documento origen",
                    f"No se pudo abrir '{src_path}':\n{e}")
                return

        # Validar
        try:
            errors = validate_bulk(ops, self.doc, src_con=src_con)
        finally:
            if src_con:
                try: src_con.close()
                except Exception: pass

        self._ops    = ops
        self._errors = errors
        self._src_path = Path(src_path) if src_path else None

        # Rellenar tabla
        self._tbl.setRowCount(len(ops))
        bad_pairs = {op.row_pair for op in ops if not op.src_group_id}
        for r, op in enumerate(ops):
            is_bad = op.row_pair in bad_pairs
            color  = QColor("#FFE0E0") if is_bad else QColor("#F0FFF0")
            items  = [
                str(op.row_pair),
                op.src_kks,
                op.dst_kks,
                op.dst_desc,
                f"H{op.dst_sheet:02d}",
                ', '.join(f'"{p}"→"{s}"' for p, s in op.rules) or '—',
            ]
            for c, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                it.setBackground(color)
                self._tbl.setItem(r, c, it)

        # Actualizar estado
        n_ok  = len(ops) - len(bad_pairs)
        n_err = len(errors)
        src_label = (f"← {Path(src_path).name}" if src_path
                     else "← documento actual")
        self._lbl_summary.setText(
            f"<b>{len(ops)}</b> operación(es)  {src_label}  —  "
            f"<span style='color:{'red' if n_err else 'green'}'>"
            f"{'⚠ ' + str(n_err) + ' error(es)' if n_err else '✅ sin errores'}"
            f"</span>")
        self._lbl_summary.setStyleSheet("padding:4px; font-size:12px;")

        if errors:
            self._lbl_err_title.setText(
                f"<b style='color:red'>⚠  {len(errors)} error(es) de validación "
                f"— no se puede ejecutar la importación:</b>")
            self._txt_errors.setPlainText('\n'.join(errors))
            self._frm_errors.setVisible(True)
            self._lbl_warn.setVisible(False)
            self._btn_exec.setEnabled(False)
        else:
            self._frm_errors.setVisible(False)
            self._lbl_warn.setVisible(True)
            self._btn_exec.setEnabled(True)

    # ── Ejecución ────────────────────────────────────────────────────────

    def _on_execute(self):
        from io_utils.db_io import get_mem, sync_document, sync_sheet
        from widgets.bulk_clone_dialog import _BulkWorker

        try:
            sync_document(self.doc)
            for g in self.doc.groups:
                for s in g.sheets:
                    if getattr(s, '_loaded', False):
                        sync_sheet(s)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar",
                                 f"No se pudo guardar el documento:\n{e}")
            return

        doc_id = getattr(self.doc, '_doc_id', None) or 'main'
        src_path = getattr(self, '_src_path', None)

        self._btn_exec.setEnabled(False)
        self._btn_cancel.setEnabled(False)
        self._btn_preview.setEnabled(False)
        self._progress.setRange(0, len(self._ops))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._lbl_prog.setVisible(True)

        self._worker = _BulkWorker(self._ops, doc_id, src_path=src_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, cur: int, total: int, msg: str):
        self._progress.setValue(cur)
        self._lbl_prog.setText(msg)

    def _on_finished(self, new_gids: list[str]):
        self._new_gids = new_gids
        self._progress.setValue(len(self._ops))
        self._lbl_prog.setText(
            f"✅  Importación completada. {len(new_gids)} grupo(s) creado(s).")
        self._btn_cancel.setText("Cerrar")
        self._btn_cancel.setEnabled(True)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1200, self.accept)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._lbl_prog.setVisible(False)
        self._btn_cancel.setEnabled(True)
        self._btn_exec.setEnabled(True)
        self._btn_preview.setEnabled(True)
        QMessageBox.critical(
            self, "Error en la importación",
            f"Se produjo un error y se realizó rollback automático:\n\n{msg}\n\n"
            "El documento quedó sin cambios.")

    def new_group_ids(self) -> list[str]:
        return self._new_gids
