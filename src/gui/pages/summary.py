"""Painel de resultados: cartoes de estatisticas e tabela dos ficheiros tratados."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.historico import ESTADO_RECUPERADO, NOMES_DOS_METODOS
from src.gui import theme
from src.gui.widgets import (
    CabecalhoDePainel,
    CartaoDeEstatistica,
    PainelDeDetalhes,
    formatar_tamanho,
)

TITULO = "Resultados da operacao"
DESCRICAO = "Resumo do que foi encontrado, seleccionado e recuperado."
COLUNAS = ("Nome", "Tipo", "Tamanho", "Estado", "Observacao")
ACCAO = "Gerar relatorio PDF"
SEM_OPERACAO = "Ainda nao foi concluida nenhuma operacao."

# Cartoes de estatisticas: chave no resumo, legenda e cor.
ESTATISTICAS = (
    ("encontrados", "Ficheiros encontrados", "azul"),
    ("seleccionados", "Seleccionados", "laranja"),
    ("recuperados", "Recuperados", "verde"),
    ("nao_recuperados", "Nao recuperados", "vermelho"),
)


class SummaryPage(QWidget):
    """Resultado final da operacao, com os totais em destaque."""

    relatorio_pedido = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.operacao: dict = {}
        self.ficheiros: list[dict] = []

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.etiqueta_estado = QLabel(SEM_OPERACAO)
        self.etiqueta_estado.setObjectName(theme.SUBTITULO)

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.etiqueta_estado)

        self.cartoes: dict[str, CartaoDeEstatistica] = {}
        cartoes = QHBoxLayout()
        cartoes.setContentsMargins(0, 0, 0, 0)
        cartoes.setSpacing(12)
        for chave, legenda, cor in ESTATISTICAS:
            cartao = CartaoDeEstatistica(legenda, cor)
            self.cartoes[chave] = cartao
            cartoes.addWidget(cartao, 1)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        cabecalho_tabela = self.tabela.horizontalHeader()
        cabecalho_tabela.setStretchLastSection(False)
        cabecalho_tabela.setSectionResizeMode(0, QHeaderView.Stretch)
        cabecalho_tabela.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(4, QHeaderView.Stretch)

        self.painel = PainelDeDetalhes(ACCAO)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(14)
        conteudo.addLayout(topo)
        conteudo.addLayout(cartoes)
        conteudo.addWidget(self.tabela, 1)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.painel.botao_accao.clicked.connect(self.relatorio_pedido.emit)

    def mostrar_operacao(self, operacao: dict, ficheiros: list[dict]) -> None:
        """Preenche os cartoes, a tabela e o painel com o resultado final."""
        self.operacao = dict(operacao or {})
        self.ficheiros = list(ficheiros or [])

        for chave, _legenda, _cor in ESTATISTICAS:
            self.cartoes[chave].definir_valor(self.operacao.get(chave, 0) or 0)

        self.tabela.setRowCount(len(self.ficheiros))
        for linha, ficheiro in enumerate(self.ficheiros):
            valores = (
                ficheiro.get("nome", ""),
                ficheiro.get("tipo") or "?",
                formatar_tamanho(ficheiro.get("tamanho")),
                ficheiro.get("estado", ""),
                ficheiro.get("erro") or ficheiro.get("caminho") or "",
            )
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor))
                if coluna == 4 and valor:
                    item.setToolTip(str(valor))
                self.tabela.setItem(linha, coluna, item)

        recuperados = self.operacao.get("recuperados", 0) or 0
        self.etiqueta_estado.setText(
            "%d de %d ficheiros recuperados"
            % (recuperados, self.operacao.get("seleccionados", 0) or 0)
        )
        metodo = self.operacao.get("metodo")
        self.painel.mostrar(
            "Operacao #%s" % (self.operacao.get("id") or "-"),
            NOMES_DOS_METODOS.get(metodo, metodo or "-"),
            [
                ("Dispositivo:", self.operacao.get("device_path") or "-"),
                ("Sistema de ficheiros:",
                 self.operacao.get("filesystem") or "nao identificado"),
                ("Pasta de destino:", self.operacao.get("pasta_destino") or "-"),
                ("Inicio:", (self.operacao.get("inicio") or "-")[:19]),
                ("Fim:", (self.operacao.get("fim") or "-")[:19]),
                ("Perito:", self.operacao.get("app_user") or "-"),
            ],
        )

    def limpar(self) -> None:
        """Volta ao estado inicial, sem operacao apresentada."""
        self.operacao = {}
        self.ficheiros = []
        for cartao in self.cartoes.values():
            cartao.definir_valor(0)
        self.tabela.setRowCount(0)
        self.etiqueta_estado.setText(SEM_OPERACAO)
        self.painel.limpar()

    def ficheiros_recuperados(self) -> list[dict]:
        return [f for f in self.ficheiros if f.get("estado") == ESTADO_RECUPERADO]
