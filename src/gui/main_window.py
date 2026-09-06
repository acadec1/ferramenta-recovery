"""Janela principal da ferramenta (PySide6).

Toda a aplicacao vive numa unica janela: a autenticacao, a lista de
dispositivos, os ficheiros apagados, o carving, a cadeia de custodia e as contas
sao paineis empilhados que se substituem no mesmo espaco, sem abrir janelas
novas. A janela limita-se a orquestrar os modulos de src/ — nao contem logica de
negocio propria.

O acesso a cada painel depende do perfil da conta autenticada (ver src/auth.py):
o administrador faz tudo, o operador so escaneia e recupera.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src import filesystem_parser, integrity, recovery, report
from src import carving as carving_module
from src import device_reader
from src.audit_log import (
    ACTION_CARVING,
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
from src.gui.pages.accounts import AccountsPage
from src.gui.pages.audit import AuditPage
from src.gui.pages.carving import CarvingPage
from src.gui.pages.devices import DevicesPage
from src.gui.pages.login import LoginPage
from src.gui.pages.results import ResultsPage
from src.gui.widgets import Banner

TITULO_JANELA = "FRDA — Ferramenta de Recuperacao de Dados Apagados"
AVISO_ADMIN = (
    "Sem privilegios de Administrador: o acesso a disco bruto vai falhar. "
    "Reinicie a partir de uma consola elevada."
)
ESTADO_ADMIN = "A correr como Administrador."
SEM_PERMISSAO = "O perfil %s nao tem permissao para esta accao."

# Paineis da barra lateral: chave, rotulo, seccao e permissao necessaria.
MENU = (
    ("dispositivos", "Dispositivos", "Recuperacao de dados", PERMISSION_SCAN),
    ("resultados", "Ficheiros apagados", "Recuperacao de dados", PERMISSION_RECOVER),
    ("carving", "Carving por assinatura", "Recuperacao de dados", PERMISSION_RECOVER),
    ("auditoria", "Cadeia de custodia", "Ferramentas", PERMISSION_REPORT),
    ("contas", "Contas de acesso", "Ferramentas", PERMISSION_MANAGE_USERS),
)


class MainWindow(QMainWindow):
    """Janela unica com barra lateral e paineis empilhados."""

    def __init__(self, user: dict | None = None, audit_log: AuditLog | None = None,
                 auth_store: AuthStore | None = None):
        super().__init__()
        self.audit_log = audit_log if audit_log is not None else AuditLog()
        self.auth_store = auth_store if auth_store is not None else AuthStore()
        self.user: dict = {}
        self.dispositivo_actual: str | None = None

        self.setWindowTitle(TITULO_JANELA)
        self.resize(1120, 660)
        self.setMinimumSize(980, 560)

        self.login_page = LoginPage(self.auth_store)
        self.janela = QStackedWidget()
        self.janela.addWidget(self.login_page)
        self.janela.addWidget(self._construir_aplicacao())
        self.setCentralWidget(self.janela)

        self.etiqueta_privilegios = QLabel("")
        self.statusBar().addPermanentWidget(self.etiqueta_privilegios)

        self._ligar_sinais()
        self.avisar_privilegios()

        if user:
            self.entrar(user)
        else:
            self.mostrar_login()

    # ------------------------------------------------------------ construcao

    def _construir_aplicacao(self) -> QWidget:
        aplicacao = QWidget()
        disposicao = QVBoxLayout(aplicacao)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addWidget(self._construir_cabecalho())

        corpo = QHBoxLayout()
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._construir_barra_lateral())
        corpo.addWidget(self._construir_conteudo(), 1)
        disposicao.addLayout(corpo, 1)
        return aplicacao

    def _construir_cabecalho(self) -> QFrame:
        titulo = QLabel("FRDA")
        titulo.setObjectName(theme.TITULO_JANELA)
        subtitulo = QLabel("Recuperacao forense de dados apagados")
        subtitulo.setObjectName(theme.SUBTITULO)
        identificacao = QVBoxLayout()
        identificacao.setSpacing(0)
        identificacao.addWidget(titulo)
        identificacao.addWidget(subtitulo)

        self.etiqueta_sessao = QLabel("")
        self.etiqueta_sessao.setObjectName(theme.SUBTITULO)
        self.botao_terminar_sessao = QPushButton("Terminar sessao")
        self.botao_terminar_sessao.setObjectName(theme.BOTAO_SECUNDARIO)

        conteudo = QHBoxLayout()
        conteudo.setContentsMargins(20, 12, 20, 12)
        conteudo.addLayout(identificacao)
        conteudo.addStretch(1)
        conteudo.addWidget(self.etiqueta_sessao)
        conteudo.addWidget(self.botao_terminar_sessao)

        cabecalho = QFrame()
        cabecalho.setObjectName(theme.CABECALHO)
        cabecalho.setLayout(conteudo)
        return cabecalho

    def _construir_barra_lateral(self) -> QWidget:
        self.menu = QListWidget()
        self.menu.setObjectName(theme.MENU_LATERAL)
        self.itens_do_menu: dict[str, QListWidgetItem] = {}
        self.cabecalhos_de_seccao: dict[str, QListWidgetItem] = {}

        seccao_actual = None
        for chave, rotulo, seccao, _permissao in MENU:
            if seccao != seccao_actual:
                cabecalho = QListWidgetItem(seccao)
                cabecalho.setFlags(Qt.NoItemFlags)
                self.menu.addItem(cabecalho)
                self.cabecalhos_de_seccao[seccao] = cabecalho
                seccao_actual = seccao
            item = QListWidgetItem(rotulo)
            item.setData(Qt.UserRole, chave)
            self.menu.addItem(item)
            self.itens_do_menu[chave] = item

        barra = QWidget()
        barra.setObjectName(theme.BARRA_LATERAL)
        barra.setFixedWidth(220)
        disposicao = QVBoxLayout(barra)
        disposicao.setContentsMargins(0, 8, 0, 8)
        disposicao.setSpacing(0)
        disposicao.addWidget(self.menu, 1)
        return barra

    def _construir_conteudo(self) -> QWidget:
        self.devices_page = DevicesPage()
        self.results_page = ResultsPage()
        self.carving_page = CarvingPage()
        self.audit_page = AuditPage()
        self.accounts_page = AccountsPage(self.auth_store)

        self.paineis = {
            "dispositivos": self.devices_page,
            "resultados": self.results_page,
            "carving": self.carving_page,
            "auditoria": self.audit_page,
            "contas": self.accounts_page,
        }

        self.conteudo = QStackedWidget()
        for chave, _rotulo, _seccao, _permissao in MENU:
            self.conteudo.addWidget(self.paineis[chave])

        self.banner = Banner()

        area = QWidget()
        disposicao = QVBoxLayout(area)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        margem_do_banner = QWidget()
        banner_layout = QVBoxLayout(margem_do_banner)
        banner_layout.setContentsMargins(20, 12, 20, 0)
        banner_layout.addWidget(self.banner)
        disposicao.addWidget(margem_do_banner)
        disposicao.addWidget(self.conteudo, 1)
        return area

    def _ligar_sinais(self) -> None:
        self.login_page.autenticado.connect(self.entrar)
        self.botao_terminar_sessao.clicked.connect(self.terminar_sessao)
        self.menu.currentItemChanged.connect(self._menu_mudou)
        self.devices_page.varrimento_pedido.connect(self.varrer)
        self.results_page.recuperacao_pedida.connect(self.recuperar)
        self.carving_page.carving_pedido.connect(self.executar_carving)
        self.audit_page.relatorio_pedido.connect(self.gerar_relatorio)
        self.accounts_page.conta_criada.connect(
            lambda nome: self.notificar("Conta '%s' criada." % nome, "sucesso")
        )

    # ---------------------------------------------------------------- sessao

    def mostrar_login(self) -> None:
        """Mostra o painel de autenticacao dentro da mesma janela."""
        self.user = {}
        self.login_page.preparar()
        self.janela.setCurrentWidget(self.login_page)

    def entrar(self, user: dict) -> None:
        """Abre a aplicacao para a conta autenticada."""
        self.user = user or {}
        self.etiqueta_sessao.setText(
            "%s • %s" % (self.user.get("username", "?"), self.user.get("role", "?"))
        )
        self.janela.setCurrentIndex(1)
        self.banner.limpar()
        self.aplicar_permissoes()
        self.devices_page.carregar()
        self.results_page.mostrar_entradas([])
        self.carving_page.mostrar_dispositivo(None)
        if self.pode(PERMISSION_MANAGE_USERS):
            self.accounts_page.carregar()
        self.ir_para("dispositivos")

    def terminar_sessao(self) -> None:
        """Volta ao painel de autenticacao, sem fechar a janela."""
        self.results_page.mostrar_entradas([])
        self.dispositivo_actual = None
        self.mostrar_login()

    # ------------------------------------------------------------ permissoes

    @property
    def perfil(self) -> str:
        return self.user.get("role", "")

    def pode(self, permissao: str) -> bool:
        """Indica se a conta autenticada tem a permissao indicada."""
        return has_permission(self.perfil, permissao)

    def aplicar_permissoes(self) -> None:
        """Esconde da barra lateral os paineis fora do perfil da conta."""
        visiveis_por_seccao: dict[str, bool] = {}
        for chave, _rotulo, seccao, permissao in MENU:
            permitido = self.pode(permissao)
            self.itens_do_menu[chave].setHidden(not permitido)
            visiveis_por_seccao[seccao] = visiveis_por_seccao.get(seccao, False) or permitido
        for seccao, cabecalho in self.cabecalhos_de_seccao.items():
            cabecalho.setHidden(not visiveis_por_seccao.get(seccao, False))

    def _exigir(self, permissao: str) -> bool:
        if self.pode(permissao):
            return True
        self.notificar(SEM_PERMISSAO % (self.perfil or "sem sessao"), "erro")
        return False

    # ---------------------------------------------------------- navegacao

    def ir_para(self, chave: str) -> None:
        """Mostra o painel indicado e selecciona-o na barra lateral."""
        item = self.itens_do_menu.get(chave)
        if item is None or item.isHidden():
            return
        self.menu.setCurrentItem(item)
        self.conteudo.setCurrentWidget(self.paineis[chave])

    def painel_actual(self) -> str:
        for chave, painel in self.paineis.items():
            if painel is self.conteudo.currentWidget():
                return chave
        return ""

    def _menu_mudou(self, actual, _anterior) -> None:
        if actual is None:
            return
        chave = actual.data(Qt.UserRole)
        if not chave:
            return
        self.banner.limpar()  # a mensagem pertence ao painel onde foi mostrada
        self.conteudo.setCurrentWidget(self.paineis[chave])
        if chave == "auditoria" and self.pode(PERMISSION_REPORT):
            self.audit_page.mostrar_eventos(self.audit_log.get_events())
        elif chave == "contas" and self.pode(PERMISSION_MANAGE_USERS):
            self.accounts_page.carregar()
        elif chave == "carving":
            self.carving_page.mostrar_dispositivo(self.dispositivo_actual)

    # ------------------------------------------------------------- mensagens

    def notificar(self, texto: str, tipo: str = "info") -> None:
        """Mostra uma mensagem em linha, no topo do painel."""
        self.banner.mostrar(texto, tipo)
        self.statusBar().showMessage(texto)

    def avisar_privilegios(self) -> None:
        """Indica na barra de estado se ha privilegios de Administrador."""
        if device_reader.is_admin():
            self.etiqueta_privilegios.setObjectName("estadoOk")
            self.etiqueta_privilegios.setText(ESTADO_ADMIN)
        else:
            self.etiqueta_privilegios.setObjectName("avisoPrivilegios")
            self.etiqueta_privilegios.setText(AVISO_ADMIN)
        theme.repolir(self.etiqueta_privilegios)

    def registar_evento(self, **campos) -> None:
        """Regista um evento de auditoria com o perito autenticado."""
        campos.setdefault("app_user", self.user.get("username"))
        self.audit_log.log_event(**campos)

    # ---------------------------------------------------------------- accoes

    def varrer(self, device_path: str) -> None:
        """Varre o dispositivo e mostra as entradas apagadas encontradas."""
        if not self._exigir(PERMISSION_SCAN):
            return
        if not device_path:
            self.notificar("Seleccione um dispositivo.", "aviso")
            return

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            entradas = filesystem_parser.scan_deleted_entries(device_path)
        except Exception as erro:
            self.notificar("Falha ao escanear %s: %s" % (device_path, erro), "erro")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        self.dispositivo_actual = device_path
        self.results_page.mostrar_entradas(entradas, device_path)
        self.registar_evento(device_path=device_path, action=ACTION_SCAN)
        self.ir_para("resultados")
        self.notificar(
            "%d entradas apagadas encontradas em %s." % (len(entradas), device_path),
            "sucesso" if entradas else "info",
        )

    def recuperar(self, entradas: list[dict]) -> None:
        """Reconstroi as entradas seleccionadas numa pasta a escolher."""
        if not self._exigir(PERMISSION_RECOVER):
            return
        if not entradas:
            self.notificar("Seleccione pelo menos uma entrada.", "aviso")
            return

        destino = self.escolher_pasta("Pasta de destino")
        if not destino:
            return

        recuperados, falhados = [], []
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for entrada in entradas:
                try:
                    caminho = recovery.recover_file(
                        self.dispositivo_actual, entrada, destino
                    )
                    self._registar_ficheiro(caminho, ACTION_RECOVER)
                    recuperados.append(caminho)
                except Exception as erro:
                    falhados.append("%s (%s)" % (entrada.get("name", "?"), erro))
        finally:
            QGuiApplication.restoreOverrideCursor()

        if falhados:
            self.notificar(
                "%d ficheiros recuperados para %s. Falhas: %s"
                % (len(recuperados), destino, "; ".join(falhados)),
                "aviso",
            )
        else:
            self.notificar(
                "%d ficheiros recuperados para %s." % (len(recuperados), destino),
                "sucesso",
            )

    def executar_carving(self, tipo: str) -> None:
        """Varre o dispositivo por assinaturas binarias do tipo indicado."""
        if not self._exigir(PERMISSION_RECOVER):
            return
        device_path = self.dispositivo_actual or self.devices_page.dispositivo_selecionado()
        if not device_path:
            self.notificar(
                "Seleccione primeiro um dispositivo no painel Dispositivos.", "aviso"
            )
            return

        destino = self.escolher_pasta("Pasta para os ficheiros extraidos")
        if not destino:
            return

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            caminhos = carving_module.carve_by_signature(device_path, tipo, destino)
        except Exception as erro:
            self.notificar("Falha no carving: %s" % erro, "erro")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        for caminho in caminhos:
            self._registar_ficheiro(caminho, ACTION_CARVING, device_path)
        self.carving_page.mostrar_resultados(caminhos)
        self.notificar(
            "%d ficheiros %s extraidos para %s." % (len(caminhos), tipo.upper(), destino),
            "sucesso" if caminhos else "info",
        )

    def _registar_ficheiro(self, caminho: str, accao: str,
                           device_path: str | None = None) -> None:
        """Calcula o SHA-256, verifica-o e regista os dois eventos."""
        dispositivo = device_path or self.dispositivo_actual
        hash_sha256 = integrity.compute_hash(caminho)
        verificado = integrity.verify_integrity(hash_sha256, caminho)
        self.registar_evento(
            device_path=dispositivo,
            action=accao,
            file_path=caminho,
            file_hash=hash_sha256,
        )
        self.registar_evento(
            device_path=dispositivo,
            action=ACTION_VERIFY_OK if verificado else ACTION_VERIFY_FAILED,
            file_path=caminho,
            file_hash=hash_sha256,
        )

    def gerar_relatorio(self) -> None:
        """Exporta os eventos de auditoria para PDF e abre o ficheiro."""
        if not self._exigir(PERMISSION_REPORT):
            return
        eventos = self.audit_log.get_events()
        if not eventos:
            self.notificar("Ainda nao ha eventos de auditoria para relatar.", "aviso")
            return

        destino = self.escolher_ficheiro_de_destino()
        if not destino:
            return

        try:
            report.generate_report(eventos, destino)
        except Exception as erro:
            self.notificar("Falha ao gerar o relatorio: %s" % erro, "erro")
            return

        self.registar_evento(
            device_path=self.dispositivo_actual,
            action=ACTION_REPORT,
            file_path=destino,
        )
        self.audit_page.mostrar_eventos(self.audit_log.get_events())
        self.notificar("Relatorio gerado em %s." % destino, "sucesso")
        self.abrir_ficheiro(destino)

    # ------------------------------------------------------------- auxiliares

    def escolher_pasta(self, titulo: str) -> str:
        return QFileDialog.getExistingDirectory(self, titulo)

    def escolher_ficheiro_de_destino(self) -> str:
        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar relatorio", "relatorio_frda.pdf", "PDF (*.pdf)"
        )
        return destino

    @staticmethod
    def abrir_ficheiro(caminho: str) -> None:
        """Abre o ficheiro na aplicacao predefinida do sistema."""
        try:
            os.startfile(caminho)  # noqa: S606 (apenas Windows, como a restante app)
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802 (nome imposto pelo Qt)
        self.audit_log.close()
        self.auth_store.close()
        super().closeEvent(event)


def main() -> int:
    aplicacao = QApplication(sys.argv)
    theme.apply_theme(aplicacao)

    auth_store = AuthStore()
    auth_store.ensure_default_accounts()

    janela = MainWindow(auth_store=auth_store)
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
