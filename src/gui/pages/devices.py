"""Painel de dispositivos: discos fisicos com os respectivos volumes logicos."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import device_reader
from src.gui import theme
from src.gui.widgets import CabecalhoDePainel, PainelDeDetalhes, formatar_tamanho

TITULO = "Dispositivos de armazenamento"
DESCRICAO = "Escolha o disco ou o volume a analisar."
COLUNAS = ("Dispositivo/Disco", "Tipo", "Ligacao/SF", "Capacidade")
ACCAO = "Procurar dados apagados"


class DevicesPage(QWidget):
    """Arvore de discos e volumes, com painel de detalhes e accao de varrimento."""

    varrimento_pedido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.etiqueta_contagem = QLabel("")
        self.etiqueta_contagem.setObjectName(theme.SUBTITULO)
        self.botao_atualizar = QPushButton("Actualizar")
        self.botao_atualizar.setObjectName(theme.BOTAO_SECUNDARIO)

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.etiqueta_contagem)
        topo.addWidget(self.botao_atualizar)

        self.arvore = QTreeWidget()
        self.arvore.setColumnCount(len(COLUNAS))
        self.arvore.setHeaderLabels(COLUNAS)
        self.arvore.setRootIsDecorated(True)
        self.arvore.setAlternatingRowColors(False)
        self.arvore.setSelectionMode(QAbstractItemView.SingleSelection)
        self.arvore.setUniformRowHeights(True)
        self.arvore.header().setStretchLastSection(False)
        self.arvore.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for coluna in range(1, len(COLUNAS)):
            self.arvore.header().setSectionResizeMode(coluna, QHeaderView.Fixed)
            self.arvore.header().resizeSection(coluna, 130)

        self.painel = PainelDeDetalhes(ACCAO)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addLayout(topo)
        conteudo.addWidget(self.arvore)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.arvore.itemSelectionChanged.connect(self.mostrar_detalhes)
        self.botao_atualizar.clicked.connect(self.carregar)
        self.painel.botao_accao.clicked.connect(self._pedir_varrimento)

    # ------------------------------------------------------------------ dados

    def carregar(self) -> None:
        """Le os discos e volumes e reconstroi a arvore."""
        self.arvore.clear()
        self.painel.limpar()
        discos = device_reader.list_physical_drives()
        volumes = device_reader.list_logical_volumes()

        elementos = 0
        nos_por_disco = {}
        for disco in discos:
            no = QTreeWidgetItem(
                [
                    "Disco fisico %d" % disco["index"],
                    "Disco",
                    "Acesso bruto",
                    formatar_tamanho(disco["size_bytes"]),
                ]
            )
            no.setData(0, Qt.UserRole, {"tipo": "disco", "dados": disco})
            self.arvore.addTopLevelItem(no)
            nos_por_disco[disco["index"]] = no
            elementos += 1

        for volume in volumes:
            etiqueta = volume["label"] or "Volume local"
            no = QTreeWidgetItem(
                [
                    "%s (%s:)" % (etiqueta, volume["letter"]),
                    "Volume logico",
                    volume["filesystem"],
                    formatar_tamanho(volume["size_bytes"]),
                ]
            )
            no.setData(0, Qt.UserRole, {"tipo": "volume", "dados": volume})
            pai = nos_por_disco.get(volume["disk_index"])
            if pai is None:
                self.arvore.addTopLevelItem(no)
            else:
                pai.addChild(no)
            elementos += 1

        self.arvore.expandAll()
        self.etiqueta_contagem.setText("%d elementos" % elementos)

    def seleccao(self) -> dict | None:
        itens = self.arvore.selectedItems()
        if not itens:
            return None
        return itens[0].data(0, Qt.UserRole)

    def dispositivo_selecionado(self) -> str | None:
        """Caminho do dispositivo seleccionado, para os modulos de analise."""
        seleccao = self.seleccao()
        if seleccao is None:
            return None
        return seleccao["dados"]["path"]

    # --------------------------------------------------------------- detalhes

    def mostrar_detalhes(self) -> None:
        seleccao = self.seleccao()
        if seleccao is None:
            self.painel.limpar()
            return
        dados = seleccao["dados"]
        if seleccao["tipo"] == "disco":
            self.painel.mostrar(
                "Disco fisico %d" % dados["index"],
                "Dispositivo • %s" % formatar_tamanho(dados["size_bytes"]),
                [
                    ("Tipo:", "Disco fisico"),
                    ("Caminho:", dados["path"]),
                    ("Capacidade:", formatar_tamanho(dados["size_bytes"])),
                    ("Numero fisico:", dados["index"]),
                ],
            )
        else:
            self.painel.mostrar(
                "%s (%s:)" % (dados["label"] or "Volume local", dados["letter"]),
                "Volume logico • %s" % formatar_tamanho(dados["size_bytes"]),
                [
                    ("Tipo:", "Volume logico"),
                    ("Sistema de ficheiros:", dados["filesystem"]),
                    ("Ligacao:", dados["drive_type"]),
                    ("Caminho:", dados["path"]),
                    ("Capacidade:", formatar_tamanho(dados["size_bytes"])),
                    ("Disponivel:", formatar_tamanho(dados["free_bytes"])),
                    (
                        "Disco fisico:",
                        "-" if dados["disk_index"] is None else dados["disk_index"],
                    ),
                ],
            )

    def _pedir_varrimento(self) -> None:
        device_path = self.dispositivo_selecionado()
        if device_path:
            self.varrimento_pedido.emit(device_path)
