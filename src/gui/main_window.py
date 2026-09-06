"""Janela principal da ferramenta (PySide6).

A interface limita-se a chamar as funcoes dos modulos de src/: enumeracao de
dispositivos, varrimento de entradas apagadas, recuperacao, calculo de hash,
autenticacao e registo de auditoria. Nao contem logica de negocio propria.

O acesso as accoes e determinado pelo perfil da conta autenticada (ver
src/auth.py): o administrador faz tudo, o operador so escaneia e recupera.
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
    QDialog,
    QFileDialog,
    QFrame,
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
from src.auth import (
    PERMISSION_MANAGE_USERS,
    PERMISSION_RECOVER,
    PERMISSION_REPORT,
    PERMISSION_SCAN,
    AuthStore,
    has_permission,
)
from src.gui import theme
from src.gui.account_dialog import NovaContaDialog
from src.gui.login_dialog import LoginDialog

COLUNAS = ("Nome", "Tamanho (bytes)", "Data de modificacao")
AVISO_ADMIN = (
    "AVISO: sem privilegios de Administrador — o acesso a disco bruto vai falhar. "
    "Reinicie a aplicacao a partir de uma consola elevada."
)
ESTADO_ADMIN = "A correr como Administrador."
SEM_PERMISSAO = "O perfil %s nao tem permissao para esta accao."


def _formatar_tamanho(tamanho_bytes: int) -> str:
    unidades = ("B", "KB", "MB", "GB", "TB")
    valor = float(tamanho_bytes)
    for unidade in unidades:
        if valor < 1024 or unidade == unidades[-1]:
            return "%.1f %s" % (valor, unidade)
        valor /= 1024
    return "%.1f %s" % (valor, unidades[-1])


class MainWindow(QMainWindow):
    """Janela principal: dispositivos, varrimento, recuperacao e relatorio."""

    def __init__(self, user: dict | None = None, audit_log: AuditLog | None = None,
                 auth_store: AuthStore | None = None):
        super().__init__()
        self.user = user or {}
        self.audit_log = audit_log if audit_log is not None else AuditLog()
        self.auth_store = auth_store
        self.setWindowTitle("FRDA — Ferramenta de Recuperacao de Dados Apagados")
        self.resize(960, 600)

        self.setCentralWidget(self._construir_conteudo())
        self._construir_barra_de_estado()

        self.botao_escanear.clicked.connect(self.escanear)
        self.botao_recuperar.clicked.connect(self.recuperar_selecionados)
        self.botao_relatorio.clicked.connect(self.gerar_relatorio)
        self.botao_contas.clicked.connect(self.gerir_contas)

        self.aplicar_permissoes()
        self.carregar_dispositivos()
        self.avisar_privilegios()

    # ------------------------------------------------------------ construcao

    def _construir_conteudo(self) -> QWidget:
        titulo = QLabel("FRDA")
        titulo.setObjectName("tituloApp")
        subtitulo = QLabel("Ferramenta de Recuperacao de Dados Apagados")
        subtitulo.setObjectName("subtituloApp")
        identificacao = QVBoxLayout()
        identificacao.setSpacing(0)
        identificacao.addWidget(titulo)
        identificacao.addWidget(subtitulo)

        self.etiqueta_sessao = QLabel(self._descricao_da_sessao())
        self.etiqueta_sessao.setObjectName("utilizadorSessao")

        cabecalho_conteudo = QHBoxLayout()
        cabecalho_conteudo.setContentsMargins(16, 10, 16, 10)
        cabecalho_conteudo.addLayout(identificacao)
        cabecalho_conteudo.addStretch(1)
        cabecalho_conteudo.addWidget(self.etiqueta_sessao)
        cabecalho = QFrame()
        cabecalho.setObjectName("cabecalho")
        cabecalho.setLayout(cabecalho_conteudo)

        self.combo_dispositivos = QComboBox()
        self.botao_escanear = QPushButton("Escanear")
        self.botao_escanear.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_recuperar = QPushButton("Recuperar Selecionados")
        self.botao_recuperar.setObjectName(theme.BOTAO_SUCESSO)
        self.botao_recuperar.setEnabled(False)
        self.botao_relatorio = QPushButton("Gerar Relatorio")
        self.botao_relatorio.setObjectName(theme.BOTAO_NEUTRO)
        self.botao_contas = QPushButton("Contas")
        self.botao_contas.setObjectName(theme.BOTAO_NEUTRO)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Dispositivo:"))
        barra.addWidget(self.combo_dispositivos, 1)
        barra.addWidget(self.botao_escanear)
        barra.addWidget(self.botao_recuperar)
        barra.addWidget(self.botao_relatorio)
        barra.addWidget(self.botao_contas)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        corpo = QVBoxLayout()
        corpo.setContentsMargins(16, 12, 16, 12)
        corpo.addLayout(barra)
        corpo.addWidget(self.tabela)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(0, 0, 0, 0)
        conteudo.setSpacing(0)
        conteudo.addWidget(cabecalho)
        conteudo.addLayout(corpo)

        central = QWidget()
        central.setLayout(conteudo)
        return central

    def _construir_barra_de_estado(self) -> None:
        self.etiqueta_privilegios = QLabel("")
        self.statusBar().addPermanentWidget(self.etiqueta_privilegios)

    def _descricao_da_sessao(self) -> str:
        if not self.user:
            return "sem sessao iniciada"
        return "%s (%s)" % (self.user.get("username", "?"), self.user.get("role", "?"))

    # ----------------------------------------------------------- permissoes

    @property
    def perfil(self) -> str:
        return self.user.get("role", "")

    def pode(self, permissao: str) -> bool:
        """Indica se a conta autenticada tem a permissao indicada."""
        return has_permission(self.perfil, permissao)

    def aplicar_permissoes(self) -> None:
        """Esconde ou desactiva as accoes fora do perfil da conta."""
        self.botao_escanear.setEnabled(self.pode(PERMISSION_SCAN))
        self.botao_relatorio.setVisible(self.pode(PERMISSION_REPORT))
        self.botao_contas.setVisible(self.pode(PERMISSION_MANAGE_USERS))

    def _exigir(self, permissao: str, titulo: str) -> bool:
        if self.pode(permissao):
            return True
        QMessageBox.warning(self, titulo, SEM_PERMISSAO % (self.perfil or "sem sessao"))
        return False

    # ---------------------------------------------------------------- dados

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
            self.etiqueta_privilegios.setObjectName("estadoOk")
            self.etiqueta_privilegios.setText(ESTADO_ADMIN)
        else:
            self.etiqueta_privilegios.setObjectName("avisoPrivilegios")
            self.etiqueta_privilegios.setText(AVISO_ADMIN)
        # o objectName mudou: repolir para o tema aplicar a cor correspondente
        estilo = self.etiqueta_privilegios.style()
        estilo.unpolish(self.etiqueta_privilegios)
        estilo.polish(self.etiqueta_privilegios)

    def registar_evento(self, **campos) -> None:
        """Regista um evento de auditoria com o perito autenticado."""
        campos.setdefault("app_user", self.user.get("username"))
        self.audit_log.log_event(**campos)

    # ---------------------------------------------------------------- accoes

    def escanear(self) -> None:
        """Varre o dispositivo selecionado e preenche a tabela."""
        if not self._exigir(PERMISSION_SCAN, "Escanear"):
            return
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
        self.registar_evento(
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
        self.botao_recuperar.setEnabled(
            bool(entradas) and self.pode(PERMISSION_RECOVER)
        )

    def entradas_selecionadas(self) -> list[dict]:
        entradas = []
        for indice in self.tabela.selectionModel().selectedRows():
            item = self.tabela.item(indice.row(), 0)
            if item is not None:
                entradas.append(item.data(Qt.UserRole))
        return entradas

    def recuperar_selecionados(self) -> None:
        """Recupera as entradas selecionadas para uma pasta a escolher."""
        if not self._exigir(PERMISSION_RECOVER, "Recuperar"):
            return
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
                    self.registar_evento(
                        device_path=device_path,
                        action=ACTION_RECOVER,
                        file_path=caminho,
                        file_hash=hash_sha256,
                    )
                    self.registar_evento(
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
        if not self._exigir(PERMISSION_REPORT, "Relatorio"):
            return
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
            QMessageBox.critical(
                self, "Relatorio", "Falha ao gerar o relatorio:\n%s" % erro
            )
            return

        self.registar_evento(
            device_path=self.dispositivo_selecionado(),
            action=ACTION_REPORT,
            file_path=destino,
        )
        self.statusBar().showMessage("Relatorio gerado em %s." % destino)
        self.abrir_ficheiro(destino)

    def gerir_contas(self) -> None:
        """Cria uma conta de acesso (reservado ao perfil administrador)."""
        if not self._exigir(PERMISSION_MANAGE_USERS, "Contas"):
            return
        if self.auth_store is None:
            QMessageBox.warning(
                self, "Contas", "Repositorio de contas indisponivel nesta sessao."
            )
            return

        dialogo = NovaContaDialog(self.auth_store, self)
        if dialogo.exec() != QDialog.Accepted:
            return
        self.statusBar().showMessage("Conta '%s' criada." % dialogo.criada)
        QMessageBox.information(
            self, "Contas", "Conta '%s' criada com sucesso." % dialogo.criada
        )

    @staticmethod
    def abrir_ficheiro(caminho: str) -> None:
        """Abre o ficheiro na aplicacao predefinida do sistema."""
        try:
            os.startfile(caminho)  # noqa: S606 (apenas Windows, como a restante app)
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802 (nome imposto pelo Qt)
        self.audit_log.close()
        if self.auth_store is not None:
            self.auth_store.close()
        super().closeEvent(event)


def main() -> int:
    aplicacao = QApplication(sys.argv)
    theme.apply_theme(aplicacao)

    auth_store = AuthStore()
    auth_store.ensure_default_accounts()

    login = LoginDialog(auth_store)
    if login.exec() != QDialog.Accepted:
        auth_store.close()
        return 0

    janela = MainWindow(user=login.user, auth_store=auth_store)
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
