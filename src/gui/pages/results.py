"""Painel de ficheiros apagados encontrados no varrimento."""

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

from src.gui import theme
from src.gui.widgets import CabecalhoDePainel, PainelDeDetalhes, formatar_tamanho

TITULO = "Ficheiros apagados"
DESCRICAO = "Seleccione as entradas a reconstruir e escolha a pasta de destino."
COLUNAS = ("Nome", "Caminho original", "Tamanho", "Data de modificacao")
ACCAO = "Recuperar seleccionados"
SEM_VARRIMENTO = "Ainda nao foi feito nenhum varrimento."


class ResultsPage(QWidget):
    """Tabela das entradas apagadas, com recuperacao dos itens seleccionados."""

    recuperacao_pedida = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entradas: list[dict] = []

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.etiqueta_contagem = QLabel(SEM_VARRIMENTO)
        self.etiqueta_contagem.setObjectName(theme.SUBTITULO)
        self.botao_selecionar_tudo = QPushButton("Seleccionar tudo")
        self.botao_selecionar_tudo.setObjectName(theme.BOTAO_SECUNDARIO)

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.etiqueta_contagem)
        topo.addWidget(self.botao_selecionar_tudo)

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
        cabecalho_tabela.setSectionResizeMode(1, QHeaderView.Stretch)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.painel = PainelDeDetalhes(ACCAO)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addLayout(topo)
        conteudo.addWidget(self.tabela)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.tabela.itemSelectionChanged.connect(self.mostrar_detalhes)
        self.botao_selecionar_tudo.clicked.connect(self.tabela.selectAll)
        self.painel.botao_accao.clicked.connect(self._pedir_recuperacao)

    # ------------------------------------------------------------------ dados

    def mostrar_entradas(self, entradas: list[dict], device_path: str = "") -> None:
        """Preenche a tabela com as entradas devolvidas pelo varrimento."""
        self.entradas = list(entradas)
        self.painel.limpar()
        self.tabela.setRowCount(len(entradas))
        for linha, entrada in enumerate(entradas):
            valores = (
                entrada.get("name", ""),
                entrada.get("path", ""),
                formatar_tamanho(entrada.get("size", 0)),
                entrada.get("mtime_iso") or "-",
            )
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == 0:
                    item.setData(Qt.UserRole, entrada)
                if coluna in (0, 1) and entrada.get("path"):
                    item.setToolTip(entrada["path"])
                self.tabela.setItem(linha, coluna, item)
        self.etiqueta_contagem.setText(
            "%d entradas apagadas%s"
            % (len(entradas), (" em %s" % device_path) if device_path else "")
        )
        self.botao_selecionar_tudo.setEnabled(bool(entradas))

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
            total = sum(entrada.get("size", 0) or 0 for entrada in entradas)
            self.painel.mostrar(
                "%d entradas seleccionadas" % len(entradas),
                "Total • %s" % formatar_tamanho(total),
                [("Entradas:", len(entradas)), ("Tamanho total:", formatar_tamanho(total))],
            )
            return

        entrada = entradas[0]
        clusters = sum(run.get("count", 0) for run in entrada.get("runs") or [])
        self.painel.mostrar(
            entrada.get("name", "?"),
            "Entrada apagada • %s" % formatar_tamanho(entrada.get("size", 0)),
            [
                ("Caminho:", entrada.get("path", "-")),
                ("Tamanho:", formatar_tamanho(entrada.get("size", 0))),
                ("Modificado:", entrada.get("mtime_iso") or "-"),
                ("Criado:", entrada.get("crtime_iso") or "-"),
                ("Sistema de ficheiros:", entrada.get("fs_type", "-")),
                ("Clusters:", clusters or "-"),
                ("Dados residentes:", "sim" if entrada.get("resident") else "nao"),
            ],
        )

    def _pedir_recuperacao(self) -> None:
        entradas = self.entradas_selecionadas()
        if entradas:
            self.recuperacao_pedida.emit(entradas)
