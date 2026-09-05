"""Janela principal da ferramenta (PySide6).

A interface limita-se a chamar as funcoes dos modulos de src/: enumeracao de
dispositivos, varrimento de entradas apagadas, recuperacao, calculo de hash e
registo de auditoria. Nao contem logica de negocio propria.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import device_reader, filesystem_parser, integrity, recovery, report
from src.audit_log import (
    ACTION_RECOVER,
    ACTION_REPORT,
    ACTION_SCAN,
    ACTION_VERIFY_FAILED,
    ACTION_VERIFY_OK,
    AuditLog,
)

COLUNAS = ("Nome", "Tamanho (bytes)", "Data de modificacao")
AVISO_ADMIN = (
    "AVISO: sem privilegios de Administrador — o acesso a disco bruto vai falhar. "
    "Reinicie a aplicacao a partir de uma consola elevada."
)


def _formatar_tamanho(tamanho_bytes: int) -> str:
    unidades = ("B", "KB", "MB", "GB", "TB")
    valor = float(tamanho_bytes)
    for unidade in unidades:
        if valor < 1024 or unidade == unidades[-1]:
            return "%.1f %s" % (valor, unidade)
        valor /= 1024
    return "%.1f %s" % (valor, unidades[-1])


class MainWindow(QMainWindow):
    """Janela principal: dispositivos, varrimento e recuperacao."""

    def __init__(self, audit_log: AuditLog | None = None):
        super().__init__()
        self.audit_log = audit_log if audit_log is not None else AuditLog()
        self.setWindowTitle("FRDA — Ferramenta de Recuperacao de Dados Apagados")
        self.resize(900, 560)

        self.combo_dispositivos = QComboBox()
        self.botao_escanear = QPushButton("Escanear")
        self.botao_recuperar = QPushButton("Recuperar Selecionados")
        self.botao_recuperar.setEnabled(False)
        self.botao_relatorio = QPushButton("Gerar Relatorio")

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Dispositivo:"))
        barra.addWidget(self.combo_dispositivos, 1)
        barra.addWidget(self.botao_escanear)
        barra.addWidget(self.botao_recuperar)
        barra.addWidget(self.botao_relatorio)

        conteudo = QVBoxLayout()
        conteudo.addLayout(barra)
        conteudo.addWidget(self.tabela)

        central = QWidget()
        central.setLayout(conteudo)
        self.setCentralWidget(central)

        self.botao_escanear.clicked.connect(self.escanear)
        self.botao_recuperar.clicked.connect(self.recuperar_selecionados)
        self.botao_relatorio.clicked.connect(self.gerar_relatorio)

        self.carregar_dispositivos()
        self.avisar_privilegios()

    # ------------------------------------------------------------------ dados

    def dispositivo_selecionado(self) -> str | None:
        return self.combo_dispositivos.currentData()

    def carregar_dispositivos(self) -> None:
        """Preenche a combo box com os discos devolvidos por device_reader."""
        self.combo_dispositivos.clear()
        for dispositivo in device_reader.list_physical_drives():
            etiqueta = "PhysicalDrive%d — %s" % (
                dispositivo["index"],
                _formatar_tamanho(dispositivo["size_bytes"]),
            )
            self.combo_dispositivos.addItem(etiqueta, dispositivo["path"])
        if self.combo_dispositivos.count() == 0:
            self.combo_dispositivos.addItem("Nenhum dispositivo detetado", None)

    def avisar_privilegios(self) -> None:
        """Mostra na barra de estado o aviso de falta de privilegios."""
        if device_reader.is_admin():
            self.statusBar().showMessage("A correr como Administrador.")
        else:
            self.statusBar().showMessage(AVISO_ADMIN)

    # ---------------------------------------------------------------- accoes

    def escanear(self) -> None:
        """Varre o dispositivo selecionado e preenche a tabela."""
        device_path = self.dispositivo_selecionado()
        if not device_path:
            QMessageBox.warning(self, "Escanear", "Selecione um dispositivo.")
            return

        self.statusBar().showMessage("A escanear %s..." % device_path)
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            entradas = filesystem_parser.scan_deleted_entries(device_path)
        except Exception as erro:
            QMessageBox.critical(self, "Escanear", "Falha ao escanear:\n%s" % erro)
            self.statusBar().showMessage("Varrimento falhado.")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        self.preencher_tabela(entradas)
        self.audit_log.log_event(
            device_path=device_path,
            action=ACTION_SCAN,
            file_path=None,
            file_hash=None,
        )
        self.statusBar().showMessage(
            "%d entradas apagadas encontradas em %s." % (len(entradas), device_path)
        )

    def preencher_tabela(self, entradas: list[dict]) -> None:
        self.tabela.setRowCount(len(entradas))
        for linha, entrada in enumerate(entradas):
            valores = (
                entrada.get("name", ""),
                str(entrada.get("size", 0)),
                entrada.get("mtime_iso") or "-",
            )
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == 0:
                    item.setData(Qt.UserRole, entrada)
                    item.setToolTip(entrada.get("path", ""))
                self.tabela.setItem(linha, coluna, item)
        self.botao_recuperar.setEnabled(bool(entradas))

    def entradas_selecionadas(self) -> list[dict]:
        entradas = []
        for indice in self.tabela.selectionModel().selectedRows():
            item = self.tabela.item(indice.row(), 0)
            if item is not None:
                entradas.append(item.data(Qt.UserRole))
        return entradas

    def recuperar_selecionados(self) -> None:
        """Recupera as entradas selecionadas para uma pasta a escolher."""
        entradas = self.entradas_selecionadas()
        if not entradas:
            QMessageBox.information(
                self, "Recuperar", "Selecione pelo menos uma entrada na tabela."
            )
            return

        destino = QFileDialog.getExistingDirectory(self, "Pasta de destino")
        if not destino:
            return

        device_path = self.dispositivo_selecionado()
        recuperados, falhados = [], []
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for entrada in entradas:
                try:
                    caminho = recovery.recover_file(device_path, entrada, destino)
                    hash_sha256 = integrity.compute_hash(caminho)
                    verificado = integrity.verify_integrity(hash_sha256, caminho)
                    self.audit_log.log_event(
                        device_path=device_path,
                        action=ACTION_RECOVER,
                        file_path=caminho,
                        file_hash=hash_sha256,
                    )
                    self.audit_log.log_event(
                        device_path=device_path,
                        action=ACTION_VERIFY_OK if verificado else ACTION_VERIFY_FAILED,
                        file_path=caminho,
                        file_hash=hash_sha256,
                    )
                    recuperados.append(caminho)
                except Exception as erro:
                    falhados.append("%s: %s" % (entrada.get("name", "?"), erro))
        finally:
            QGuiApplication.restoreOverrideCursor()

        self.statusBar().showMessage(
            "%d ficheiros recuperados para %s (%d falhas)."
            % (len(recuperados), destino, len(falhados))
        )
        if falhados:
            QMessageBox.warning(
                self,
                "Recuperar",
                "%d ficheiros recuperados.\nFalhas:\n%s"
                % (len(recuperados), "\n".join(falhados)),
            )
        else:
            QMessageBox.information(
                self, "Recuperar", "%d ficheiros recuperados." % len(recuperados)
            )

    def gerar_relatorio(self) -> None:
        """Exporta os eventos de auditoria para PDF e abre o ficheiro."""
        eventos = self.audit_log.get_events()
        if not eventos:
            QMessageBox.information(
                self, "Relatorio", "Ainda nao ha eventos de auditoria para relatar."
            )
            return

        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar relatorio", "relatorio_frda.pdf", "PDF (*.pdf)"
        )
        if not destino:
            return

        try:
            report.generate_report(eventos, destino)
        except Exception as erro:
            QMessageBox.critical(self, "Relatorio", "Falha ao gerar o relatorio:
%s" % erro)
            return

        self.audit_log.log_event(
            device_path=self.dispositivo_selecionado(),
            action=ACTION_REPORT,
            file_path=destino,
        )
        self.statusBar().showMessage("Relatorio gerado em %s." % destino)
        self.abrir_ficheiro(destino)

    @staticmethod
    def abrir_ficheiro(caminho: str) -> None:
        """Abre o ficheiro na aplicacao predefinida do sistema."""
        try:
            os.startfile(caminho)  # noqa: S606 (apenas Windows, como a restante app)
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802 (nome imposto pelo Qt)
        self.audit_log.close()
        super().closeEvent(event)


def main() -> int:
    aplicacao = QApplication(sys.argv)
    janela = MainWindow()
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
