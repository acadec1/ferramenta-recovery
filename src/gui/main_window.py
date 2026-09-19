"""Janela principal da ferramenta (PySide6).

Toda a aplicacao vive numa unica janela: a autenticacao, a escolha do
dispositivo e do metodo, os ficheiros encontrados, os resultados, o historico e
as contas sao paineis empilhados que se substituem no mesmo espaco, sem abrir
janelas novas. A janela limita-se a orquestrar os modulos de src/ — nao contem
logica de negocio propria.

O acesso a cada painel depende do perfil da conta autenticada (ver src/auth.py):
o administrador faz tudo, o operador so escaneia e recupera.
"""

from __future__ import annotations

import datetime
import os
import sys

from PySide6.QtCore import QSize, Qt
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

from src import device_reader, operacao, report
from src.historico import METODO_CARVING, METODO_METADADOS, Historico
from src.auth import (
    PERMISSION_MANAGE_USERS,
    PERMISSION_RECOVER,
    PERMISSION_REPORT,
    PERMISSION_SCAN,
    AuthStore,
    has_permission,
)
from src.gui import icons, theme
from src.gui.pages.accounts import AccountsPage
from src.gui.pages.devices import DevicesPage
from src.gui.pages.history import HistoryPage
from src.gui.pages.login import LoginPage
from src.gui.pages.results import ResultsPage
from src.gui.pages.summary import SummaryPage
from src.gui.widgets import Banner
from src.gui.workers import TrabalhoDeAnalise, TrabalhoDeRecuperacao

TITULO_JANELA = "FRDA — Ferramenta de Recuperacao de Dados Apagados"
AVISO_ADMIN = (
    "Sem privilegios de Administrador: o acesso a disco bruto vai falhar. "
    "Reinicie a partir de uma consola elevada."
)
ESTADO_ADMIN = "A correr como Administrador."
SEM_PERMISSAO = "O perfil %s nao tem permissao para esta accao."

# Paineis da barra lateral: chave, rotulo, seccao e permissao necessaria.
# O fluxo segue a ordem da barra lateral: dispositivo e metodo, ficheiros
# encontrados, resultados. A analise nao e um passo separado: comeca sozinha
# assim que o metodo e escolhido.
MENU = (
    ("dispositivos", "1. Dispositivo e metodo", "Recuperacao de dados",
     PERMISSION_SCAN, "disco"),
    ("resultados", "2. Ficheiros encontrados", "Recuperacao de dados",
     PERMISSION_RECOVER, "ficheiro"),
    ("resumo", "3. Resultados", "Recuperacao de dados", PERMISSION_RECOVER,
     "carving"),
    ("historico", "Historico de operacoes", "Ferramentas", PERMISSION_REPORT,
     "auditoria"),
    ("contas", "Contas de acesso", "Ferramentas", PERMISSION_MANAGE_USERS, "contas"),
)

FILTRO_DE_IMAGENS = "Imagens de disco (*.dd *.img *.raw *.bin);;Todos os ficheiros (*)"
ARGUMENTO_SEM_ELEVACAO = "--sem-elevacao"
ELEVACAO_RECUSADA = (
    "A elevacao foi recusada. Sem privilegios de Administrador o Windows nao "
    "deixa ler o disco em bruto."
)


def _agora() -> str:
    """Instante actual em UTC, no formato usado pelo registo."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class MainWindow(QMainWindow):
    """Janela unica com barra lateral e paineis empilhados."""

    def __init__(self, user: dict | None = None, historico: Historico | None = None,
                 auth_store: AuthStore | None = None):
        super().__init__()
        self.historico = historico if historico is not None else Historico()
        self.auth_store = auth_store if auth_store is not None else AuthStore()
        self.user: dict = {}
        self.dispositivo_actual: str | None = None
        self.metodo_actual: str = METODO_METADADOS
        self.entradas_encontradas: list[dict] = []
        self.inicio_da_operacao: str | None = None
        self.dados_do_dispositivo: dict = {}
        self.trabalho = None  # analise ou recuperacao a decorrer

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
        marca = QLabel()
        marca.setPixmap(icons.chip("logotipo", "azul", 38))
        marca.setFixedSize(38, 38)

        titulo = QLabel("FRDA")
        titulo.setObjectName(theme.MARCA)
        subtitulo = QLabel("Recuperacao forense de dados apagados")
        subtitulo.setObjectName(theme.SUBTITULO)
        identificacao = QVBoxLayout()
        identificacao.setSpacing(0)
        identificacao.addWidget(titulo)
        identificacao.addWidget(subtitulo)

        self.etiqueta_sessao = QLabel("")
        self.etiqueta_sessao.setObjectName(theme.SUBTITULO)
        self.botao_elevar = QPushButton("  Reiniciar como Administrador")
        self.botao_elevar.setObjectName(theme.BOTAO_SECUNDARIO)
        self.botao_elevar.setIcon(icons.icone("administrador", 16, theme.CORES["erro"]))
        self.botao_terminar_sessao = QPushButton("Terminar sessao")
        self.botao_terminar_sessao.setObjectName(theme.BOTAO_SECUNDARIO)

        conteudo = QHBoxLayout()
        conteudo.setContentsMargins(20, 12, 20, 12)
        conteudo.setSpacing(12)
        conteudo.addWidget(marca)
        conteudo.addLayout(identificacao)
        conteudo.addStretch(1)
        conteudo.addWidget(self.etiqueta_sessao)
        conteudo.addWidget(self.botao_elevar)
        conteudo.addWidget(self.botao_terminar_sessao)

        cabecalho = QFrame()
        cabecalho.setObjectName(theme.CABECALHO)
        cabecalho.setLayout(conteudo)
        return cabecalho

    def _construir_barra_lateral(self) -> QWidget:
        self.menu = QListWidget()
        self.menu.setObjectName(theme.MENU_LATERAL)
        self.menu.setIconSize(QSize(18, 18))
        self.itens_do_menu: dict[str, QListWidgetItem] = {}
        self.cabecalhos_de_seccao: dict[str, QListWidgetItem] = {}

        seccao_actual = None
        for chave, rotulo, seccao, _permissao, nome_do_icone in MENU:
            if seccao != seccao_actual:
                cabecalho = QListWidgetItem(seccao)
                cabecalho.setFlags(Qt.NoItemFlags)
                self.menu.addItem(cabecalho)
                self.cabecalhos_de_seccao[seccao] = cabecalho
                seccao_actual = seccao
            item = QListWidgetItem(rotulo)
            item.setIcon(icons.icone(nome_do_icone, 18, theme.CORES["texto_suave"]))
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
        self.summary_page = SummaryPage()
        self.history_page = HistoryPage()
        self.accounts_page = AccountsPage(self.auth_store)

        self.paineis = {
            "dispositivos": self.devices_page,
            "resultados": self.results_page,
            "resumo": self.summary_page,
            "historico": self.history_page,
            "contas": self.accounts_page,
        }

        self.conteudo = QStackedWidget()
        for chave, _rotulo, _seccao, _permissao, _icone in MENU:
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
        self.devices_page.imagem_pedida.connect(self.escolher_imagem)
        self.botao_elevar.clicked.connect(self.reiniciar_como_administrador)
        self.results_page.recuperacao_pedida.connect(self.recuperar)
        self.results_page.paragem_pedida.connect(self.parar_operacao)
        self.summary_page.relatorio_pedido.connect(self.gerar_relatorio_da_operacao)
        self.history_page.relatorio_pedido.connect(
            self.gerar_relatorio_de_operacao_antiga
        )
        self.history_page.ficheiros_pedidos.connect(self._mostrar_ficheiros_do_historico)
        self.history_page.botao_atualizar.clicked.connect(self._carregar_historico)
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
        self.summary_page.limpar()
        if self.pode(PERMISSION_MANAGE_USERS):
            self.accounts_page.carregar()
        self.ir_para("dispositivos")

    def terminar_sessao(self) -> None:
        """Volta ao painel de autenticacao, sem fechar a janela."""
        self.results_page.mostrar_entradas([])
        self.summary_page.limpar()
        self.dispositivo_actual = None
        self.entradas_encontradas = []
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
        for chave, _rotulo, seccao, permissao, _icone in MENU:
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
        if chave == "historico" and self.pode(PERMISSION_REPORT):
            self._carregar_historico()
        elif chave == "contas" and self.pode(PERMISSION_MANAGE_USERS):
            self.accounts_page.carregar()


    # ------------------------------------------------------------- mensagens

    def notificar(self, texto: str, tipo: str = "info") -> None:
        """Mostra uma mensagem em linha, no topo do painel."""
        self.banner.mostrar(texto, tipo)
        self.statusBar().showMessage(texto)

    def avisar_privilegios(self) -> None:
        """Indica na barra de estado se ha privilegios de Administrador."""
        self.botao_elevar.setVisible(not device_reader.is_admin())
        if device_reader.is_admin():
            self.etiqueta_privilegios.setObjectName("estadoOk")
            self.etiqueta_privilegios.setText(ESTADO_ADMIN)
        else:
            self.etiqueta_privilegios.setObjectName("avisoPrivilegios")
            self.etiqueta_privilegios.setText(AVISO_ADMIN)
        theme.repolir(self.etiqueta_privilegios)

    def _carregar_historico(self) -> None:
        """Actualiza o painel com as operacoes guardadas."""
        self.history_page.mostrar_operacoes(self.historico.get_operations())

    def _mostrar_ficheiros_do_historico(self, identificador: int) -> None:
        self.history_page.mostrar_ficheiros(
            self.historico.get_operation_files(identificador)
        )

    # ---------------------------------------------------------------- accoes

    def varrer(self, device_path: str, metodo: str = METODO_METADADOS) -> None:
        """Inicia a analise do dispositivo pelo metodo escolhido.

        A analise corre noutra linha de execucao: a janela continua a responder
        e o estado e a barra de progresso vao sendo actualizados.
        """
        if not self._exigir(PERMISSION_SCAN):
            return
        if not device_path:
            self.notificar("Seleccione um dispositivo.", "aviso")
            return
        if self.trabalho is not None and self.trabalho.isRunning():
            self.notificar("Ja ha uma operacao a decorrer.", "aviso")
            return

        self.dispositivo_actual = device_path
        self.metodo_actual = metodo
        self.inicio_da_operacao = _agora()
        # fixado agora: o utilizador pode mudar de cartao antes de recuperar
        self.dados_do_dispositivo = self.devices_page.informacao_do_dispositivo()
        self.summary_page.limpar()
        self.banner.limpar()
        self._bloquear_accoes(True)

        # A analise decorre no painel dos ficheiros: abre-se primeiro, para a
        # lista se ir preenchendo a vista do utilizador.
        self.ir_para("resultados")
        self.results_page.iniciar_analise(device_path, metodo)

        self.trabalho = TrabalhoDeAnalise(device_path, metodo, self)
        self.trabalho.progresso.connect(self.results_page.definir_progresso)
        self.trabalho.encontrados.connect(self.results_page.acrescentar_entradas)
        self.trabalho.concluido.connect(self._analise_concluida)
        self.trabalho.interrompido.connect(self._analise_interrompida)
        self.trabalho.falhou.connect(self._analise_falhada)
        self.trabalho.start()

    def parar_operacao(self) -> None:
        """Pede ao trabalho em curso que pare, guardando o que ja fez."""
        if self.trabalho is None:
            return
        self.trabalho.parar()
        self.notificar("A parar a operacao...", "aviso")

    def _analise_concluida(self, entradas: list, diagnostico: dict) -> None:
        self._bloquear_accoes(False)
        self.entradas_encontradas = list(entradas)
        self.results_page.terminar_analise(self.dispositivo_actual)
        self.notificar(
            *self._resumo_do_varrimento(
                self.dispositivo_actual, entradas, diagnostico
            )
        )

    def _analise_interrompida(self, entradas: list, _diagnostico: dict) -> None:
        """A analise parou a pedido: o que ja foi encontrado continua utilizavel."""
        self._bloquear_accoes(False)
        self.entradas_encontradas = list(entradas)
        self.results_page.interromper()
        self.notificar(
            "Analise interrompida: %d ficheiros encontrados ate ao momento."
            % len(entradas),
            "aviso",
        )

    def _analise_falhada(self, erro: str) -> None:
        self._bloquear_accoes(False)
        self.results_page.falhar(erro)
        self.notificar(erro, "erro")
        if "Acesso negado" in erro or "Administrador" in erro:
            self.botao_elevar.setVisible(True)

    @staticmethod
    def _resumo_do_varrimento(device_path: str, entradas: list,
                              diagnostico: dict) -> tuple:
        """Mensagem do varrimento: o que foi encontrado e o que foi analisado."""
        if entradas:
            return (
                "%d ficheiros encontrados em %s." % (len(entradas), device_path),
                "sucesso",
            )
        if diagnostico.get("metodo") == METODO_CARVING:
            return (
                "Nenhuma assinatura encontrada em %s (tipos procurados: %s)."
                % (device_path, ", ".join(diagnostico.get("tipos") or ["-"])),
                "info",
            )
        if not diagnostico.get("sistemas_de_ficheiros"):
            return (
                "Nenhum sistema de ficheiros reconhecido em %s (%d particoes). "
                "O disco pode estar encriptado ou usar um formato nao suportado."
                % (device_path, diagnostico.get("particoes", 0)),
                "aviso",
            )
        return (
            "Nenhum ficheiro apagado em %s: %d sistemas de ficheiros analisados "
            "(%s), %d registos examinados." % (
                device_path,
                diagnostico["sistemas_de_ficheiros"],
                ", ".join(diagnostico.get("tipos") or ["?"]),
                diagnostico.get("registos_examinados", 0),
            ),
            "info",
        )

    def recuperar(self, entradas: list[dict]) -> None:
        """Recupera os ficheiros seleccionados para uma pasta a escolher."""
        if not self._exigir(PERMISSION_RECOVER):
            return
        if not entradas:
            self.notificar("Seleccione pelo menos um ficheiro.", "aviso")
            return
        if self.trabalho is not None and self.trabalho.isRunning():
            self.notificar("Ja ha uma operacao a decorrer.", "aviso")
            return

        destino = self.escolher_pasta("Pasta de destino dos ficheiros recuperados")
        if not destino:
            return
        try:
            operacao.validar_destino(self.dispositivo_actual, destino)
        except ValueError as erro:
            self.results_page.falhar(str(erro))
            self.notificar(str(erro), "erro")
            return

        self.destino_actual = destino
        self.results_page.iniciar_recuperacao(len(entradas), destino)
        self.banner.limpar()
        self._bloquear_accoes(True)

        self.trabalho = TrabalhoDeRecuperacao(
            self.dispositivo_actual, entradas, destino, self
        )
        self.trabalho.progresso.connect(self.results_page.definir_progresso)
        self.trabalho.concluido.connect(self._recuperacao_concluida)
        self.trabalho.interrompido.connect(self._recuperacao_interrompida)
        self.trabalho.falhou.connect(self._recuperacao_falhada)
        self.trabalho.start()

    def _recuperacao_interrompida(self, resultados: list) -> None:
        """A recuperacao parou a pedido: guarda-se o que ja foi recuperado."""
        self.results_page.interromper(
            "%d ficheiros recuperados antes de parar" % len(resultados)
        )
        self._recuperacao_concluida(resultados, interrompida=True)

    def _recuperacao_concluida(self, resultados: list,
                               interrompida: bool = False) -> None:
        self._bloquear_accoes(False)
        self.results_page.terminar_recuperacao()
        totais = operacao.resumo(len(self.entradas_encontradas), resultados)
        identificador = self.historico.log_operation(
            ficheiros=resultados,
            inicio=self.inicio_da_operacao,
            fim=_agora(),
            device_path=self.dispositivo_actual,
            metodo=self.metodo_actual,
            pasta_destino=self.destino_actual,
            app_user=self.user.get("username"),
            observacoes=self._observacoes(resultados, interrompida),
            **totais,
            **self.dados_do_dispositivo,
        )
        operacao_registada = self.historico.get_operations(identificador)[0]
        self.summary_page.mostrar_operacao(operacao_registada, resultados)
        self.ir_para("resumo")
        if interrompida:
            self.notificar(
                "Recuperacao interrompida: %d ficheiros recuperados para %s."
                % (totais["recuperados"], self.destino_actual),
                "aviso",
            )
            return
        self.notificar(
            "%d de %d ficheiros recuperados para %s."
            % (totais["recuperados"], totais["seleccionados"], self.destino_actual),
            "sucesso" if totais["recuperados"] else "aviso",
        )

    def _recuperacao_falhada(self, erro: str) -> None:
        self._bloquear_accoes(False)
        self.results_page.falhar(erro)
        self.notificar("Falha na recuperacao: %s" % erro, "erro")

    @staticmethod
    def _observacoes(resultados: list[dict], interrompida: bool = False) -> str:
        """Erros encontrados e paragens, para ficarem registados no relatorio."""
        notas = []
        if interrompida:
            notas.append("operacao interrompida pelo utilizador")
        notas += [
            "%s: %s" % (r.get("nome"), r.get("erro"))
            for r in resultados if r.get("erro")
        ]
        return "; ".join(notas)

    def _bloquear_accoes(self, bloqueado: bool) -> None:
        """Impede iniciar outra operacao enquanto uma esta a decorrer."""
        for painel in (self.devices_page, self.results_page):
            painel.painel.botao_accao.setEnabled(
                not bloqueado and painel.painel.etiqueta_titulo.text() != ""
            )

    def gerar_relatorio_de_operacao_antiga(self, identificador: int) -> None:
        """Volta a gerar o relatorio de uma operacao guardada no historico."""
        if not self._exigir(PERMISSION_REPORT):
            return
        operacoes = self.historico.get_operations(identificador)
        if not operacoes:
            self.notificar("Operacao #%s nao encontrada." % identificador, "aviso")
            return
        self._exportar_relatorio(
            operacoes[0], self.historico.get_operation_files(identificador)
        )

    def gerar_relatorio_da_operacao(self) -> None:
        """Exporta o relatorio PDF da operacao apresentada nos resultados."""
        if not self._exigir(PERMISSION_RECOVER):
            return
        if not self.summary_page.operacao:
            self.notificar("Ainda nao ha nenhuma operacao concluida.", "aviso")
            return

        self._exportar_relatorio(
            self.summary_page.operacao, self.summary_page.ficheiros
        )

    def _exportar_relatorio(self, operacao_registada: dict,
                            ficheiros: list[dict]) -> None:
        """Pergunta onde guardar, gera o PDF da operacao e abre-o."""
        destino = self.escolher_ficheiro_de_destino(
            "relatorio_operacao_%s.pdf" % (operacao_registada.get("id") or "1")
        )
        if not destino:
            return
        try:
            report.generate_operation_report(operacao_registada, ficheiros, destino)
        except Exception as erro:
            self.notificar("Falha ao gerar o relatorio: %s" % erro, "erro")
            return

        self.notificar("Relatorio gerado em %s." % destino, "sucesso")
        self.abrir_ficheiro(destino)

    def escolher_imagem(self) -> None:
        """Escolhe uma imagem de disco (.dd/.img) para analisar."""
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir imagem de disco", "", FILTRO_DE_IMAGENS
        )
        if caminho:
            self.devices_page.definir_imagem(caminho)
            self.notificar("Imagem seleccionada: %s" % caminho, "info")

    def reiniciar_como_administrador(self) -> None:
        """Relanca a aplicacao com elevacao e fecha esta instancia."""
        if device_reader.relaunch_as_admin():
            QApplication.quit()
            return
        self.notificar(ELEVACAO_RECUSADA, "aviso")

    def escolher_pasta(self, titulo: str) -> str:
        return QFileDialog.getExistingDirectory(self, titulo)

    def escolher_ficheiro_de_destino(self, nome: str = "relatorio_frda.pdf") -> str:
        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar relatorio", nome, "PDF (*.pdf)"
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
        self.historico.close()
        self.auth_store.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    """Arranca a aplicacao, pedindo elevacao antes de mostrar qualquer janela.

    O Windows nao permite elevar um processo ja em execucao: o UAC so concede
    privilegios a um processo novo. Por isso o pedido e feito logo no arranque,
    antes de existir interface — se o utilizador aceitar, quem continua e o
    processo elevado e este termina de imediato, sem que se veja um reinicio.
    Se recusar, a aplicacao abre na mesma, em modo limitado e com o aviso na
    barra de estado. ``--sem-elevacao`` salta o pedido.
    """
    argumentos = list(sys.argv[1:] if argv is None else argv)
    if ARGUMENTO_SEM_ELEVACAO not in argumentos:
        if device_reader.relaunch_as_admin():
            return 0

    aplicacao = QApplication(sys.argv)
    theme.apply_theme(aplicacao)

    auth_store = AuthStore()
    auth_store.ensure_default_accounts()

    janela = MainWindow(auth_store=auth_store)
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
