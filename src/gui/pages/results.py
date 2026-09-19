"""Painel dos ficheiros encontrados.

E aqui que a analise decorre: ao iniciar, a pagina abre logo, mostra a barra de
progresso e vai acrescentando os ficheiros a medida que sao encontrados, em vez
de esperar pelo fim do varrimento. A mesma barra acompanha depois a recuperacao
dos ficheiros seleccionados.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.historico import METODO_CARVING, NOMES_DOS_METODOS
from src.operacao import tipo_do_ficheiro
from src.gui import theme
from src.gui.widgets import (
    CONCLUIDO,
    EM_ANALISE,
    EM_RECUPERACAO,
    ERRO,
    CabecalhoDePainel,
    EstadoDaOperacao,
    PainelDeDetalhes,
    formatar_tamanho,
)

TITULO = "Ficheiros encontrados"
DESCRICAO = (
    "Seleccione os ficheiros a recuperar. A pasta de destino e pedida a seguir "
    "e tem de ser diferente do dispositivo analisado."
)
COLUNAS = ("Nome", "Tipo", "Tamanho", "Caminho original", "Data de modificacao")
ACCAO = "Recuperar seleccionados"
SEM_ANALISE = "Ainda nao foi feita nenhuma analise."


class ResultsPage(QWidget):
    """Lista dos ficheiros recuperaveis, preenchida durante a analise."""

    recuperacao_pedida = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entradas: list[dict] = []

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.etiqueta_contagem = QLabel(SEM_ANALISE)
        self.etiqueta_contagem.setObjectName(theme.SUBTITULO)
        self.botao_selecionar_tudo = QPushButton("Seleccionar tudo")
        self.botao_selecionar_tudo.setObjectName(theme.BOTAO_SECUNDARIO)
        self.botao_selecionar_tudo.setEnabled(False)

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.etiqueta_contagem)
        topo.addWidget(self.botao_selecionar_tudo)

        # So aparece quando ha uma operacao a decorrer ou acabada de terminar.
        self.estado = EstadoDaOperacao()
        self.estado.setVisible(False)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        cabecalho_tabela = self.tabela.horizontalHeader()
        cabecalho_tabela.setStretchLastSection(False)
        cabecalho_tabela.setSectionResizeMode(0, QHeaderView.Stretch)
        cabecalho_tabela.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(3, QHeaderView.Stretch)
        cabecalho_tabela.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.painel = PainelDeDetalhes(ACCAO)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addLayout(topo)
        conteudo.addWidget(self.estado)
        conteudo.addWidget(self.tabela)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.tabela.itemSelectionChanged.connect(self.mostrar_detalhes)
        self.botao_selecionar_tudo.clicked.connect(self.tabela.selectAll)
        self.painel.botao_accao.clicked.connect(self._pedir_recuperacao)

    # ------------------------------------------------------ analise em curso

    def iniciar_analise(self, device_path: str, metodo: str) -> None:
        """Limpa a lista e mostra a barra de progresso da analise."""
        self.entradas = []
        self.tabela.setRowCount(0)
        self.painel.limpar()
        self.botao_selecionar_tudo.setEnabled(False)
        self.etiqueta_contagem.setText("0 ficheiros encontrados")
        self.estado.setVisible(True)
        self.estado.definir_estado(
            EM_ANALISE,
            "%s • %s" % (device_path, NOMES_DOS_METODOS.get(metodo, metodo)),
        )
        self.estado.definir_progresso(0, 0)

    def acrescentar_entradas(self, entradas: list[dict]) -> None:
        """Junta a lista as entradas encontradas ate agora."""
        for entrada in entradas:
            self._acrescentar_linha(entrada)
        self.etiqueta_contagem.setText(
            "%d ficheiros encontrados" % len(self.entradas)
        )
        self.botao_selecionar_tudo.setEnabled(bool(self.entradas))

    def terminar_analise(self, device_path: str = "") -> None:
        """Fecha a fase de analise, mantendo o resultado a vista."""
        self.estado.definir_estado(
            CONCLUIDO, "%d ficheiros encontrados" % len(self.entradas)
        )
        self.etiqueta_contagem.setText(
            "%d ficheiros encontrados%s"
            % (len(self.entradas), (" em %s" % device_path) if device_path else "")
        )

    def falhar(self, erro: str) -> None:
        """Mostra o estado de erro na propria pagina da analise."""
        self.estado.setVisible(True)
        self.estado.definir_estado(ERRO, erro)

    def iniciar_recuperacao(self, quantidade: int, destino: str) -> None:
        self.estado.setVisible(True)
        self.estado.definir_estado(
            EM_RECUPERACAO, "%d ficheiros para %s" % (quantidade, destino)
        )
        self.estado.definir_progresso(0, quantidade)

    def definir_progresso(self, feitos: int, total: int) -> None:
        self.estado.definir_progresso(feitos, total)

    # ------------------------------------------------------------------ dados

    def mostrar_entradas(self, entradas: list[dict], device_path: str = "") -> None:
        """Substitui o conteudo da lista (usado ao repor o painel)."""
        self.entradas = []
        self.tabela.setRowCount(0)
        self.painel.limpar()
        self.acrescentar_entradas(list(entradas))
        if not entradas:
            self.etiqueta_contagem.setText(SEM_ANALISE)
            self.estado.setVisible(False)
        elif device_path:
            self.etiqueta_contagem.setText(
                "%d ficheiros encontrados em %s" % (len(entradas), device_path)
            )

    def _acrescentar_linha(self, entrada: dict) -> None:
        nome = entrada.get("nome") or entrada.get("name", "")
        valores = (
            nome,
            entrada.get("tipo") or tipo_do_ficheiro(nome),
            formatar_tamanho(entrada.get("tamanho") or entrada.get("size", 0)),
            entrada.get("path") or "-",
            entrada.get("mtime_iso") or "-",
        )
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        for coluna, valor in enumerate(valores):
            item = QTableWidgetItem(valor)
            if coluna == 0:
                item.setData(Qt.UserRole, entrada)
            if coluna in (0, 3) and entrada.get("path"):
                item.setToolTip(entrada["path"])
            self.tabela.setItem(linha, coluna, item)
        self.entradas.append(entrada)

    def entradas_selecionadas(self) -> list[dict]:
        entradas = []
        for indice in self.tabela.selectionModel().selectedRows():
            item = self.tabela.item(indice.row(), 0)
            if item is not None:
                entradas.append(item.data(Qt.UserRole))
        return entradas

    # --------------------------------------------------------------- detalhes

    def mostrar_detalhes(self) -> None:
        entradas = self.entradas_selecionadas()
        if not entradas:
            self.painel.limpar()
            return
        if len(entradas) > 1:
            total = sum(
                (entrada.get("tamanho") or entrada.get("size", 0) or 0)
                for entrada in entradas
            )
            self.painel.mostrar(
                "%d ficheiros seleccionados" % len(entradas),
                "Total • %s" % formatar_tamanho(total),
                [("Ficheiros:", len(entradas)),
                 ("Tamanho total:", formatar_tamanho(total))],
            )
            return

        entrada = entradas[0]
        nome = entrada.get("nome") or entrada.get("name", "?")
        tamanho = entrada.get("tamanho") or entrada.get("size", 0)
        clusters = sum(run.get("count", 0) for run in entrada.get("runs") or [])
        campos = [
            ("Tipo:", entrada.get("tipo") or tipo_do_ficheiro(nome)),
            ("Tamanho:", formatar_tamanho(tamanho)),
            ("Caminho:", entrada.get("path") or "-"),
            ("Modificado:", entrada.get("mtime_iso") or "-"),
        ]
        if entrada.get("metodo") == METODO_CARVING:
            campos += [
                ("Encontrado por:", "assinatura binaria"),
                ("Posicao no disco:", entrada.get("offset", "-")),
            ]
        else:
            campos += [
                ("Encontrado por:", "metadados"),
                ("Sistema de ficheiros:", entrada.get("fs_type", "-")),
                ("Clusters:", clusters or "-"),
                ("Dados residentes:", "sim" if entrada.get("resident") else "nao"),
            ]
        self.painel.mostrar(
            nome, "Ficheiro encontrado • %s" % formatar_tamanho(tamanho), campos
        )

    def _pedir_recuperacao(self) -> None:
        entradas = self.entradas_selecionadas()
        if entradas:
            self.recuperacao_pedida.emit(entradas)
