"""Painel de carving por assinatura (JPEG, PDF, DOCX)."""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import carving
from src.gui import theme
from src.gui.widgets import CabecalhoDePainel, PainelDeDetalhes, formatar_tamanho

TITULO = "Carving por assinatura"
DESCRICAO = (
    "Varre o dispositivo a procura de cabecalhos e rodapes conhecidos, sem depender "
    "do sistema de ficheiros. Recupera ficheiros que ja nao tem entrada de directorio."
)
COLUNAS = ("Ficheiro extraido", "Tamanho")
ACCAO = "Procurar assinaturas"
SEM_RESULTADOS = "Sem varrimentos nesta sessao."


class CarvingPage(QWidget):
    """Escolha do tipo de ficheiro e lista dos ficheiros extraidos."""

    carving_pedido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.cabecalho.etiqueta_descricao.setWordWrap(True)

        self.combo_tipo = QComboBox()
        for tipo in carving.supported_types():
            self.combo_tipo.addItem(tipo.upper(), tipo)
        self.etiqueta_contagem = QLabel(SEM_RESULTADOS)
        self.etiqueta_contagem.setObjectName(theme.SUBTITULO)

        escolha = QHBoxLayout()
        escolha.addWidget(QLabel("Tipo de ficheiro:"))
        escolha.addWidget(self.combo_tipo)
        escolha.addStretch(1)
        escolha.addWidget(self.etiqueta_contagem)

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

        self.painel = PainelDeDetalhes(ACCAO)
        self.painel.botao_accao.setEnabled(True)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addWidget(self.cabecalho)
        conteudo.addLayout(escolha)
        conteudo.addWidget(self.tabela)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.painel.botao_accao.clicked.connect(self._pedir_carving)

    def mostrar_dispositivo(self, device_path: str | None) -> None:
        """Actualiza o painel com o dispositivo que vai ser varrido."""
        self.painel.mostrar(
            "Carving por assinatura",
            device_path or "Nenhum dispositivo seleccionado",
            [
                ("Dispositivo:", device_path or "-"),
                ("Tipos suportados:", ", ".join(carving.supported_types())),
            ],
        )
        self.painel.botao_accao.setEnabled(bool(device_path))

    def mostrar_resultados(self, caminhos: list[str]) -> None:
        """Lista os ficheiros extraidos pelo carving."""
        self.tabela.setRowCount(len(caminhos))
        for linha, caminho in enumerate(caminhos):
            try:
                tamanho = formatar_tamanho(os.path.getsize(caminho))
            except OSError:
                tamanho = "-"
            self.tabela.setItem(linha, 0, QTableWidgetItem(caminho))
            self.tabela.setItem(linha, 1, QTableWidgetItem(tamanho))
        self.etiqueta_contagem.setText("%d ficheiros extraidos" % len(caminhos))

    def tipo_selecionado(self) -> str:
        return self.combo_tipo.currentData()

    def _pedir_carving(self) -> None:
        self.carving_pedido.emit(self.tipo_selecionado())
