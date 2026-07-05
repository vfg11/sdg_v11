"""
widgets/bulk_clone_dialog.py — Diálogo de previsualización y confirmación
para la clonación masiva de grupos desde fichero Excel.

Flujo:
  1. Se muestra la tabla de operaciones parseadas del Excel.
  2. Si hay errores de validación se muestran y se bloquea la ejecución.
  3. El usuario lee la advertencia sobre commit (la BD actual se guardará
     antes de ejecutar; no habrá forma de deshacer con Ctrl+Z).
  4. Al confirmar se ejecutan las clonaciones con barra de progreso.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialogButtonBox, QProgressBar, QTextEdit, QSizePolicy,
    QFrame, QSplitter, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon

from io_utils.bulk_clone import BulkOp


# ── Worker thread para no bloquear la UI ─────────────────────────────────────

class _BulkWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, msg
    finished = pyqtSignal(list)            # list[str] nuevos group_ids
    error    = pyqtSignal(str)             # mensaje de error

    def __init__(self, ops, doc_id, src_path=None):
        super().__init__()
        self.ops      = ops
        self.doc_id   = doc_id
        self.src_path = src_path   # Path al .sde origen, o None

    def run(self):
        import sqlite3
        from io_utils.db_io import get_mem
        con = get_mem()
        src_con = None
        try:
            # Abrir BD origen si se especificó
            if self.src_path:
                src_con = sqlite3.connect(str(self.src_path),
                                          check_same_thread=False)
                src_con.row_factory = sqlite3.Row

            # Iniciar savepoint para rollback automático si algo falla
            con.execute("SAVEPOINT bulk_clone")
            from io_utils.bulk_clone import execute_bulk

            def _prog(cur, tot, msg):
                self.progress.emit(cur, tot, msg)

            new_gids = execute_bulk(self.ops, self.doc_id,
                                    on_progress=_prog, src_con=src_con)
            con.execute("RELEASE SAVEPOINT bulk_clone")
            self.finished.emit(new_gids)
        except Exception as e:
            try:
                con.execute("ROLLBACK TO SAVEPOINT bulk_clone")
                con.execute("RELEASE SAVEPOINT bulk_clone")
            except Exception:
                pass
            self.error.emit(str(e))
        finally:
            if src_con:
                try: src_con.close()
                except Exception: pass


# ── Diálogo principal ─────────────────────────────────────────────────────────

class BulkCloneDialog(QDialog):
    """
    Recibe la lista de BulkOp ya parseada y validada.
    errors: lista de errores de validación (si no está vacía, bloquea ejecución).
    """

    def __init__(self, ops: list[BulkOp], errors: list[str],
                 doc, src_path=None, parent=None):
        super().__init__(parent)
        self.ops      = ops
        self.errors   = errors
        self.doc      = doc
        self.src_path = src_path   # Path al .sde externo, o None
        self._worker  = None
        self._new_gids: list[str] = []

        self.setWindowTitle("Clonación masiva de grupos")
        self.setMinimumSize(820, 580)
        self._build()

    # ── construcción UI ──────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # Título
        lbl_title = QLabel(
            f"<b>Importación masiva:</b> {len(self.ops)} operación(es) de clonado")
        lbl_title.setStyleSheet("font-size:13px; padding:4px;")
        lay.addWidget(lbl_title)

        # ── Tabla de operaciones ──────────────────────────────────────────
        self._tbl = QTableWidget(len(self.ops), 6)
        self._tbl.setHorizontalHeaderLabels(
            ["Par", "KKS origen", "KKS destino", "Descripción destino",
             "Hoja destino", "Reglas"])
        self._tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setAlternatingRowColors(True)

        has_errors = bool(self.errors)
        # IDs de ops con error (src_group_id vacío = no resuelto)
        bad_pairs = {op.row_pair for op in self.ops if not op.src_group_id}

        for r, op in enumerate(self.ops):
            is_bad = op.row_pair in bad_pairs
            bg = QColor("#FFE0E0") if is_bad else QColor("#FFFFFF")

            def _item(text, row=r, bad=is_bad):
                it = QTableWidgetItem(text)
                it.setBackground(QColor("#FFE0E0") if bad else QColor("#F0FFF0")
                                 if not bad else QColor("#FFFFFF"))
                return it

            self._tbl.setItem(r, 0, _item(str(op.row_pair)))
            self._tbl.setItem(r, 1, _item(op.src_kks))
            self._tbl.setItem(r, 2, _item(op.dst_kks))
            self._tbl.setItem(r, 3, _item(op.dst_desc))
            self._tbl.setItem(r, 4, _item(f"H{op.dst_sheet:02d}"))
            rules_txt = ', '.join(f'"{p}"→"{s}"' for p, s in op.rules) or '—'
            self._tbl.setItem(r, 5, _item(rules_txt))

            # Color de fondo por estado
            color = QColor("#FFE0E0") if is_bad else QColor("#F0FFF0")
            for c in range(6):
                item = self._tbl.item(r, c)
                if item:
                    item.setBackground(color)

        lay.addWidget(self._tbl, stretch=3)

        # ── Errores de validación ─────────────────────────────────────────
        if has_errors:
            frm = QFrame()
            frm.setFrameShape(QFrame.Shape.StyledPanel)
            frm.setStyleSheet(
                "QFrame { background:#FFF0F0; border:1px solid #C00; "
                "border-radius:4px; padding:4px; }")
            frm_lay = QVBoxLayout(frm)
            lbl_err = QLabel(
                f"<b style='color:red'>⚠  {len(self.errors)} error(es) de validación "
                f"— no se puede ejecutar la importación:</b>")
            frm_lay.addWidget(lbl_err)
            txt_err = QTextEdit()
            txt_err.setReadOnly(True)
            txt_err.setMaximumHeight(100)
            txt_err.setPlainText('\n'.join(self.errors))
            txt_err.setStyleSheet("font-family:Consolas,monospace; font-size:9pt;")
            frm_lay.addWidget(txt_err)
            lay.addWidget(frm)

        # ── Advertencia de commit ─────────────────────────────────────────
        if not has_errors:
            warn = QLabel(
                "⚠  <b>Atención:</b> antes de ejecutar se guardará el estado "
                "actual del documento en la base de datos. "
                "La operación no se puede deshacer con Ctrl+Z. "
                "Si algo falla se realizará un <b>rollback automático</b> "
                "y el documento quedará como estaba.")
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "background:#FFFBE6; border:1px solid #E6C200; "
                "border-radius:4px; padding:8px; color:#5C4A00;")
            lay.addWidget(warn)

        # ── Barra de progreso ─────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, len(self.ops))
        lay.addWidget(self._progress)

        self._lbl_progress = QLabel()
        self._lbl_progress.setVisible(False)
        self._lbl_progress.setStyleSheet("color:#1a6e3c; font-weight:bold;")
        lay.addWidget(self._lbl_progress)

        # ── Botones ───────────────────────────────────────────────────────
        bb = QDialogButtonBox()
        if not has_errors:
            self._btn_ok = bb.addButton(
                "✅  Ejecutar importación",
                QDialogButtonBox.ButtonRole.AcceptRole)
            self._btn_ok.setStyleSheet(
                "background:#1a6e3c; color:white; font-weight:bold; padding:6px 16px;")
            self._btn_ok.clicked.connect(self._on_execute)
        self._btn_cancel = bb.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._btn_cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    # ── ejecución ────────────────────────────────────────────────────────

    def _on_execute(self):
        from io_utils.db_io import get_mem, sync_document, sync_sheet
        # Commit del estado actual a la BD antes de operar
        try:
            sync_document(self.doc)
            for g in self.doc.groups:
                for s in g.sheets:
                    if getattr(s, '_loaded', False):
                        sync_sheet(s)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error al guardar",
                                 f"No se pudo guardar el documento:\n{e}")
            return

        # Obtener doc_id real
        doc_id = getattr(self.doc, '_doc_id', None) or 'main'

        # Bloquear UI
        self._btn_ok.setEnabled(False)
        self._btn_cancel.setEnabled(False)
        self._progress.setVisible(True)
        self._lbl_progress.setVisible(True)

        # Lanzar worker
        self._worker = _BulkWorker(self.ops, doc_id, src_path=self.src_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, cur: int, total: int, msg: str):
        self._progress.setValue(cur)
        self._lbl_progress.setText(msg)

    def _on_finished(self, new_gids: list[str]):
        self._new_gids = new_gids
        self._progress.setValue(len(self.ops))
        self._lbl_progress.setText(
            f"✅  Importación completada. {len(new_gids)} grupo(s) creado(s).")
        self._btn_cancel.setText("Cerrar")
        self._btn_cancel.setEnabled(True)
        # Aceptar automáticamente después de un momento
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1200, self.accept)

    def _on_error(self, msg: str):
        from PyQt6.QtWidgets import QMessageBox
        self._progress.setVisible(False)
        self._lbl_progress.setVisible(False)
        self._btn_cancel.setEnabled(True)
        QMessageBox.critical(
            self, "Error en la importación",
            f"Se produjo un error y se realizó rollback automático:\n\n{msg}\n\n"
            "El documento quedó sin cambios.")

    def new_group_ids(self) -> list[str]:
        return self._new_gids
