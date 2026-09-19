"""Painel da cadeia de custodia: eventos de auditoria e exportacao do relatorio."""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
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

from src.audit_log import (
    ACTION_CARVING,
    ACTION_RECOVER,
    ACTION_VERIFY_FAILED,
    ACTION_VERIFY_OK,
    NOMES_DOS_METODOS,
)
from src.gui import theme
from src.gui.widgets import CabecalhoDePainel, PainelDeDetalhes, TituloDeSeccao

TITULO = "Historico e cadeia de custodia"
DESCRICAO = "Operacoes realizadas e registo de todas as accoes, accao a accao."
COLUNAS = ("Data/Hora", "Dispositivo", "Accao", "Ficheiro", "SHA-256", "Perito")
COLUNAS_DAS_OPERACOES = (
    "#", "Data/Hora", "Dispositivo", "Metodo", "Encontrados", "Recuperados",
    "Nao recuperados",
)
ACCAO = "Gerar relatorio da cadeia"
ACCAO_DA_OPERACAO = "Relatorio da operacao"


def _data_legivel(timestamp) -> str:
    """Data/hora sem microsegundos nem fuso, para caber na coluna."""
    if not timestamp:
        return ""
    return str(timestamp)[:19].replace("T", " ")


def _nome_do_ficheiro(caminho) -> str:
    """So o nome do ficheiro; o caminho completo fica no tooltip."""
    return os.path.basename(caminho) if caminho else ""


def _hash_abreviado(hash_sha256) -> str:
    """Primeiros caracteres do SHA-256; o valor completo fica no tooltip."""
    if not hash_sha256:
        return ""
    return hash_sha256[:16] + "..." if len(hash_sha256) > 16 else hash_sha256


class AuditPage(QWidget):
    """Tabela de eventos de auditoria e botao de exportacao do relatorio."""

    relatorio_pedido = Signal()
    relatorio_da_operacao_pedido = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.eventos: list[dict] = []

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.operacoes: list[dict] = []
        self.etiqueta_operacoes = QLabel("0 operacoes")
        self.etiqueta_operacoes.setObjectName(theme.SUBTITULO)
        self.botao_relatorio_da_operacao = QPushButton(ACCAO_DA_OPERACAO)
        self.botao_relatorio_da_operacao.setObjectName(theme.BOTAO_SECUNDARIO)
        self.botao_relatorio_da_operacao.setEnabled(False)

        self.tabela_de_operacoes = QTableWidget(0, len(COLUNAS_DAS_OPERACOES))
        self.tabela_de_operacoes.setHorizontalHeaderLabels(COLUNAS_DAS_OPERACOES)
        self.tabela_de_operacoes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela_de_operacoes.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela_de_operacoes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela_de_operacoes.setAlternatingRowColors(True)
        self.tabela_de_operacoes.verticalHeader().setVisible(False)
        self.tabela_de_operacoes.setMaximumHeight(170)
        cabecalho_operacoes = self.tabela_de_operacoes.horizontalHeader()
        cabecalho_operacoes.setStretchLastSection(False)
        cabecalho_operacoes.setSectionResizeMode(2, QHeaderView.Stretch)
        for coluna in (0, 1, 3, 4, 5, 6):
            cabecalho_operacoes.setSectionResizeMode(
                coluna, QHeaderView.ResizeToContents
            )

        self.etiqueta_contagem = QLabel("0 eventos")
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
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        cabecalho_tabela = self.tabela.horizontalHeader()
        cabecalho_tabela.setStretchLastSection(False)
        cabecalho_tabela.setSectionResizeMode(3, QHeaderView.Stretch)
        for coluna in (0, 1, 2, 5):
            cabecalho_tabela.setSectionResizeMode(coluna, QHeaderView.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(4, QHeaderView.Fixed)
        cabecalho_tabela.resizeSection(4, 170)

        self.painel = PainelDeDetalhes(ACCAO)

        topo_das_operacoes = QHBoxLayout()
        topo_das_operacoes.addWidget(TituloDeSeccao("Operacoes", 0), 1)
        topo_das_operacoes.addWidget(self.etiqueta_operacoes)
        topo_das_operacoes.addWidget(self.botao_relatorio_da_operacao)
        self.titulo_das_operacoes = topo_das_operacoes.itemAt(0).widget()

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addLayout(topo)
        conteudo.addLayout(topo_das_operacoes)
        conteudo.addWidget(self.tabela_de_operacoes)
        conteudo.addWidget(TituloDeSeccao("Eventos", 0))
        conteudo.addWidget(self.tabela, 1)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.painel.botao_accao.clicked.connect(self.relatorio_pedido.emit)
        self.tabela_de_operacoes.itemSelectionChanged.connect(
            self._operacao_seleccionada
        )
        self.botao_relatorio_da_operacao.clicked.connect(self._pedir_relatorio)

    def mostrar_eventos(self, eventos: list[dict]) -> None:
        """Preenche a tabela e o resumo com os eventos registados."""
        self.eventos = list(eventos)
        self.tabela.setRowCount(len(eventos))
        for linha, evento in enumerate(eventos):
            hash_completo = evento.get("file_hash") or ""
            valores = (
                _data_legivel(evento.get("timestamp")),
                evento.get("device_path") or "",
                evento.get("action") or "",
                _nome_do_ficheiro(evento.get("file_path")),
                _hash_abreviado(hash_completo),
                evento.get("app_user") or "",
            )
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor))
                if coluna == 3 and evento.get("file_path"):
                    item.setToolTip(evento["file_path"])
                elif coluna == 4 and hash_completo:
                    item.setToolTip(hash_completo)
                self.tabela.setItem(linha, coluna, item)
        self.etiqueta_contagem.setText("%d eventos" % len(eventos))

        recuperados = self._ficheiros(eventos, ACTION_RECOVER) | self._ficheiros(
            eventos, ACTION_CARVING
        )
        verificados = self._ficheiros(eventos, ACTION_VERIFY_OK)
        falhados = self._ficheiros(eventos, ACTION_VERIFY_FAILED)
        self.painel.mostrar(
            "Resumo da cadeia de custodia",
            "%d eventos registados" % len(eventos),
            [
                ("Ficheiros recuperados:", len(recuperados)),
                ("Verificados com sucesso:", len(verificados)),
                ("Verificacoes falhadas:", len(falhados)),
                ("Peritos:", ", ".join(self._peritos(eventos)) or "-"),
            ],
        )
        self.painel.botao_accao.setEnabled(bool(eventos))

    def mostrar_operacoes(self, operacoes: list[dict]) -> None:
        """Preenche o historico de operacoes guardado na base de dados."""
        self.operacoes = list(operacoes or [])
        self.tabela_de_operacoes.setRowCount(len(self.operacoes))
        for linha, operacao in enumerate(self.operacoes):
            valores = (
                operacao.get("id", ""),
                _data_legivel(operacao.get("inicio")),
                operacao.get("device_path") or "",
                NOMES_DOS_METODOS.get(operacao.get("metodo"), operacao.get("metodo")),
                operacao.get("encontrados", 0),
                operacao.get("recuperados", 0),
                operacao.get("nao_recuperados", 0),
            )
            for coluna, valor in enumerate(valores):
                self.tabela_de_operacoes.setItem(
                    linha, coluna, QTableWidgetItem(str(valor))
                )
        self.etiqueta_operacoes.setText("%d operacoes" % len(self.operacoes))
        self.titulo_das_operacoes.definir_quantidade(len(self.operacoes))
        self.botao_relatorio_da_operacao.setEnabled(False)

    def operacao_seleccionada(self) -> dict | None:
        linhas = self.tabela_de_operacoes.selectionModel().selectedRows()
        if not linhas:
            return None
        return self.operacoes[linhas[0].row()]

    def _operacao_seleccionada(self) -> None:
        self.botao_relatorio_da_operacao.setEnabled(
            self.operacao_seleccionada() is not None
        )

    def _pedir_relatorio(self) -> None:
        operacao = self.operacao_seleccionada()
        if operacao is not None:
            self.relatorio_da_operacao_pedido.emit(int(operacao["id"]))

    @staticmethod
    def _ficheiros(eventos, accao) -> set:
        return {
            evento.get("file_path")
            for evento in eventos
            if evento.get("action") == accao and evento.get("file_path")
        }

    @staticmethod
    def _peritos(eventos) -> list[str]:
        return sorted({e["app_user"] for e in eventos if e.get("app_user")})
