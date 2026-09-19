"""Painel do historico: operacoes ja realizadas e reemissao dos relatorios."""

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

from src.historico import (
    NOMES_CURTOS_DOS_METODOS,
    NOMES_DOS_ESTADOS,
    NOMES_DOS_METODOS,
)
from src.gui import theme
from src.gui.widgets import CabecalhoDePainel, PainelDeDetalhes, formatar_tamanho

TITULO = "Historico de operacoes"
DESCRICAO = "Operacoes de recuperacao ja realizadas, da mais recente para a mais antiga."
COLUNAS = ("#", "Data/Hora", "Dispositivo", "Metodo", "Estado", "Ficheiros")
# Larguras fixas: deixadas ao conteudo, as colunas de numeros ficavam maiores
# que a do dispositivo e nao cabiam todas na largura util do painel. Os totais
# por estado estao no painel de detalhes, a direita.
LARGURAS = {0: 38, 1: 132, 3: 118, 4: 128, 5: 92}
COLUNA_ELASTICA = 2  # o dispositivo fica com o espaco que sobrar
COLUNAS_DOS_FICHEIROS = ("Nome", "Tipo", "Tamanho", "Estado")
ACCAO = "Gerar relatorio PDF"
SEM_OPERACOES = "Ainda nao ha operacoes registadas."


def _data_legivel(timestamp) -> str:
    """Data/hora sem microsegundos nem fuso, para caber na coluna."""
    if not timestamp:
        return ""
    return str(timestamp)[:19].replace("T", " ")


def _data_em_duas_linhas(timestamp) -> str:
    """A hora por baixo da data: numa so linha a coluna ficava larga demais
    e sobrava pouco espaco para o caminho do dispositivo."""
    legivel = _data_legivel(timestamp)
    return legivel.replace(" ", "\n", 1) if legivel else ""


class HistoryPage(QWidget):
    """Lista as operacoes guardadas e permite reemitir o respectivo relatorio."""

    relatorio_pedido = Signal(int)
    ficheiros_pedidos = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.operacoes: list[dict] = []

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.etiqueta_contagem = QLabel(SEM_OPERACOES)
        self.etiqueta_contagem.setObjectName(theme.SUBTITULO)
        self.botao_atualizar = QPushButton("Actualizar")
        self.botao_atualizar.setObjectName(theme.BOTAO_SECUNDARIO)

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.etiqueta_contagem)
        topo.addWidget(self.botao_atualizar)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        # as linhas crescem para a data caber em duas linhas
        self.tabela.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecalho_tabela = self.tabela.horizontalHeader()
        cabecalho_tabela.setStretchLastSection(False)
        cabecalho_tabela.setSectionResizeMode(COLUNA_ELASTICA, QHeaderView.Stretch)
        for coluna, largura in LARGURAS.items():
            cabecalho_tabela.setSectionResizeMode(coluna, QHeaderView.Fixed)
            self.tabela.setColumnWidth(coluna, largura)

        self.tabela_de_ficheiros = QTableWidget(0, len(COLUNAS_DOS_FICHEIROS))
        self.tabela_de_ficheiros.setHorizontalHeaderLabels(COLUNAS_DOS_FICHEIROS)
        self.tabela_de_ficheiros.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela_de_ficheiros.setAlternatingRowColors(True)
        self.tabela_de_ficheiros.verticalHeader().setVisible(False)
        cabecalho_dos_ficheiros = self.tabela_de_ficheiros.horizontalHeader()
        cabecalho_dos_ficheiros.setStretchLastSection(False)
        cabecalho_dos_ficheiros.setSectionResizeMode(0, QHeaderView.Stretch)
        for coluna in (1, 2, 3):
            cabecalho_dos_ficheiros.setSectionResizeMode(
                coluna, QHeaderView.ResizeToContents
            )

        self.etiqueta_ficheiros = QLabel("Ficheiros da operacao seleccionada")
        self.etiqueta_ficheiros.setObjectName(theme.TITULO_SECCAO)

        # Onde o historico esta guardado: o JSON pode ser aberto e arquivado
        # fora da ferramenta, por isso vale a pena ter o caminho a vista.
        self.etiqueta_caminhos = QLabel("")
        self.etiqueta_caminhos.setObjectName(theme.SUBTITULO)
        self.etiqueta_caminhos.setWordWrap(True)
        self.etiqueta_caminhos.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.painel = PainelDeDetalhes(ACCAO)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addLayout(topo)
        conteudo.addWidget(self.tabela, 3)
        conteudo.addWidget(self.etiqueta_ficheiros)
        conteudo.addWidget(self.tabela_de_ficheiros, 2)
        conteudo.addWidget(self.etiqueta_caminhos)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.tabela.itemSelectionChanged.connect(self._mudou_a_seleccao)
        self.painel.botao_accao.clicked.connect(self._pedir_relatorio)

    def mostrar_operacoes(self, operacoes: list[dict]) -> None:
        """Preenche o historico guardado na base de dados."""
        self.operacoes = list(operacoes or [])
        self.tabela.setRowCount(len(self.operacoes))
        for linha, operacao in enumerate(self.operacoes):
            metodo = operacao.get("metodo")
            estado = operacao.get("estado")
            recuperados = operacao.get("recuperados", 0)
            encontrados = operacao.get("encontrados", 0)
            valores = (
                operacao.get("id", ""),
                _data_em_duas_linhas(operacao.get("inicio")),
                operacao.get("device_path") or "",
                NOMES_CURTOS_DOS_METODOS.get(metodo, metodo),
                NOMES_DOS_ESTADOS.get(estado, estado or "-"),
                "%s / %s" % (recuperados, encontrados),
            )
            for coluna, valor in enumerate(valores):
                celula = QTableWidgetItem(str(valor))
                if coluna == 2:  # o caminho pode nao caber na coluna
                    celula.setToolTip(str(valor))
                self.tabela.setItem(linha, coluna, celula)
            self.tabela.item(linha, 1).setToolTip(
                _data_legivel(operacao.get("inicio"))
            )
            self.tabela.item(linha, 5).setToolTip(
                "%s recuperados de %s encontrados" % (recuperados, encontrados)
            )
        self.etiqueta_contagem.setText(
            SEM_OPERACOES if not self.operacoes
            else "%d operacoes" % len(self.operacoes)
        )
        self.tabela_de_ficheiros.setRowCount(0)
        self.painel.limpar()

    def mostrar_caminhos(self, historico) -> None:
        """Mostra onde estao guardados o JSON e a base de dados."""
        linhas = ["Base de dados: %s" % historico.db_path]
        if historico.json_path:
            linhas.insert(0, "Historico em JSON: %s" % historico.json_path)
        if historico.erro_do_json:
            linhas.append("Nao foi possivel escrever o JSON: %s"
                          % historico.erro_do_json)
        self.etiqueta_caminhos.setText("   |   ".join(linhas))

    def mostrar_ficheiros(self, ficheiros: list[dict]) -> None:
        """Lista os ficheiros processados na operacao seleccionada."""
        self.tabela_de_ficheiros.setRowCount(len(ficheiros))
        for linha, ficheiro in enumerate(ficheiros):
            valores = (
                ficheiro.get("nome", ""),
                ficheiro.get("tipo") or "?",
                formatar_tamanho(ficheiro.get("tamanho")),
                ficheiro.get("estado", ""),
            )
            for coluna, valor in enumerate(valores):
                self.tabela_de_ficheiros.setItem(
                    linha, coluna, QTableWidgetItem(str(valor))
                )

    def operacao_seleccionada(self) -> dict | None:
        linhas = self.tabela.selectionModel().selectedRows()
        if not linhas:
            return None
        return self.operacoes[linhas[0].row()]

    def _mudou_a_seleccao(self) -> None:
        operacao = self.operacao_seleccionada()
        if operacao is None:
            self.painel.limpar()
            self.tabela_de_ficheiros.setRowCount(0)
            return
        metodo = operacao.get("metodo")
        self.painel.mostrar(
            "Operacao #%s" % operacao.get("id"),
            NOMES_DOS_METODOS.get(metodo, metodo or "-"),
            [
                ("Estado:", NOMES_DOS_ESTADOS.get(operacao.get("estado"),
                                                  operacao.get("estado") or "-")),
                ("Dispositivo:", operacao.get("device_path") or "-"),
                ("Sistema de ficheiros:",
                 operacao.get("filesystem") or "nao identificado"),
                ("Encontrados:", operacao.get("encontrados", 0)),
                ("Recuperados:", operacao.get("recuperados", 0)),
                ("Nao recuperados:", operacao.get("nao_recuperados", 0)),
                ("Pasta de destino:", operacao.get("pasta_destino") or "-"),
                ("Inicio:", _data_legivel(operacao.get("inicio")) or "-"),
                ("Utilizador:", operacao.get("app_user") or "-"),
            ],
        )
        self.ficheiros_pedidos.emit(int(operacao["id"]))

    def _pedir_relatorio(self) -> None:
        operacao = self.operacao_seleccionada()
        if operacao is not None:
            self.relatorio_pedido.emit(int(operacao["id"]))
