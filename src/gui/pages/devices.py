"""Painel de dispositivos: cartoes dos discos, volumes e imagens de disco."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src import device_reader
from src.audit_log import METODO_CARVING, METODO_METADADOS, NOMES_DOS_METODOS
from src.gui import icons, theme
from src.gui.widgets import (
    CabecalhoDePainel,
    CartaoDeDispositivo,
    CartaoDeMetodo,
    PainelDeDetalhes,
    TituloDeSeccao,
    formatar_tamanho,
)

TITULO = "Escolha um local para iniciar a recuperacao"
DESCRICAO = "Seleccione o disco, o volume ou a imagem a analisar."
ACCAO = "Iniciar analise"
SECCAO_METODO = "Metodo de recuperacao"

METODOS = (
    (METODO_METADADOS, "Recuperacao baseada em metadados",
     "Usa as estruturas e os metadados do sistema de ficheiros para localizar "
     "o que foi apagado. Recupera nomes e caminhos originais.",
     "auditoria", "azul"),
    (METODO_CARVING, "Recuperacao por assinaturas (File Carving)",
     "Procura assinaturas de JPEG, PDF e DOCX nos dados em bruto. Funciona "
     "mesmo sem sistema de ficheiros, mas perde os nomes originais.",
     "carving", "roxo"),
)
COLUNAS_DA_GRELHA = 2

SECCAO_DISCOS = "Discos fisicos"
SECCAO_VOLUMES = "Volumes locais"
SECCAO_EXTERNOS = "Unidades externas"
SECCAO_RAPIDO = "Acesso rapido"

TIPOS_EXTERNOS = ("Removivel", "CD-ROM")


class DevicesPage(QWidget):
    """Cartoes de discos e volumes, com painel de detalhes e accao de varrimento."""

    varrimento_pedido = Signal(str, str)  # dispositivo, metodo
    imagem_pedida = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cartoes: list[CartaoDeDispositivo] = []
        self.seleccionado: dict | None = None
        self.imagem: str | None = None
        self.metodo = METODO_METADADOS

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)
        self.botao_atualizar = QPushButton("  Actualizar")
        self.botao_atualizar.setObjectName(theme.BOTAO_SECUNDARIO)
        self.botao_atualizar.setIcon(icons.icone("actualizar", 16,
                                                 theme.CORES["texto_suave"]))

        topo = QHBoxLayout()
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.botao_atualizar)

        self.seccoes = QVBoxLayout()
        self.seccoes.setContentsMargins(0, 0, 8, 0)
        self.seccoes.setSpacing(10)

        interior = QWidget()
        interior.setLayout(self.seccoes)
        self.area = QScrollArea()
        self.area.setWidget(interior)
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)

        self.painel = PainelDeDetalhes(ACCAO)

        self.cartoes_de_metodo: list[CartaoDeMetodo] = []
        metodos = QHBoxLayout()
        metodos.setContentsMargins(0, 0, 8, 0)
        metodos.setSpacing(12)
        for metodo, titulo, descricao, nome_do_icone, cor in METODOS:
            cartao = CartaoDeMetodo(metodo, titulo, descricao, nome_do_icone, cor)
            cartao.escolhido.connect(self.definir_metodo)
            self.cartoes_de_metodo.append(cartao)
            metodos.addWidget(cartao, 1)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 12, 18)
        conteudo.setSpacing(14)
        conteudo.addLayout(topo)
        conteudo.addWidget(self.area, 1)
        conteudo.addWidget(TituloDeSeccao(SECCAO_METODO, len(METODOS)))
        conteudo.addLayout(metodos)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(self.painel)

        self.botao_atualizar.clicked.connect(self.carregar)
        self.painel.botao_accao.clicked.connect(self._pedir_varrimento)
        self.definir_metodo(METODO_METADADOS)

    # ------------------------------------------------------------------ dados

    def carregar(self) -> None:
        """Le os discos e volumes do sistema e reconstroi os cartoes."""
        self._limpar_seccoes()
        self.cartoes = []
        self.seleccionado = None
        self.painel.limpar()

        discos = device_reader.list_physical_drives()
        volumes = device_reader.list_logical_volumes()
        externos = [v for v in volumes if v["drive_type"] in TIPOS_EXTERNOS]
        internos = [v for v in volumes if v["drive_type"] not in TIPOS_EXTERNOS]

        self._adicionar_seccao(SECCAO_DISCOS, [self._cartao_de_disco(d) for d in discos])
        self._adicionar_seccao(
            SECCAO_VOLUMES, [self._cartao_de_volume(v) for v in internos]
        )
        self._adicionar_seccao(
            SECCAO_EXTERNOS, [self._cartao_de_volume(v, "laranja") for v in externos]
        )
        self._adicionar_seccao(SECCAO_RAPIDO, [self._cartao_de_imagem()])
        self.seccoes.addStretch(1)

    def _limpar_seccoes(self) -> None:
        while self.seccoes.count():
            item = self.seccoes.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._limpar_layout(item.layout())

    def _limpar_layout(self, disposicao) -> None:
        while disposicao.count():
            item = disposicao.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _adicionar_seccao(self, titulo: str, cartoes: list) -> None:
        self.seccoes.addWidget(TituloDeSeccao(titulo, len(cartoes)))
        grelha = QGridLayout()
        grelha.setContentsMargins(0, 0, 0, 0)
        grelha.setHorizontalSpacing(12)
        grelha.setVerticalSpacing(12)
        for posicao, cartao in enumerate(cartoes):
            grelha.addWidget(cartao, posicao // COLUNAS_DA_GRELHA,
                             posicao % COLUNAS_DA_GRELHA)
            self._ligar_cartao(cartao)
        for coluna in range(COLUNAS_DA_GRELHA):
            grelha.setColumnStretch(coluna, 1)
        suporte = QWidget()
        suporte.setLayout(grelha)
        self.seccoes.addWidget(suporte)

    def _ligar_cartao(self, cartao: CartaoDeDispositivo) -> None:
        self.cartoes.append(cartao)
        cartao.escolhido.connect(self._seleccionar)
        cartao.activado.connect(self._activar)

    def _cartao_de_disco(self, disco: dict) -> CartaoDeDispositivo:
        return CartaoDeDispositivo(
            {"tipo": "disco", "dados": disco},
            "Disco fisico %d" % disco["index"],
            "Acesso bruto • %s" % formatar_tamanho(disco["size_bytes"]),
            "disco",
            cor="azul",
        )

    def _cartao_de_volume(self, volume: dict, cor: str = "verde") -> CartaoDeDispositivo:
        usado = None
        if volume["size_bytes"] and volume["free_bytes"] is not None:
            usado = volume["size_bytes"] - volume["free_bytes"]
        icone = "removivel" if volume["drive_type"] in TIPOS_EXTERNOS else "volume"
        return CartaoDeDispositivo(
            {"tipo": "volume", "dados": volume},
            "%s (%s:)" % (volume["label"] or "Volume local", volume["letter"]),
            "%s • %s" % (volume["filesystem"], volume["drive_type"]),
            icone,
            cor=cor,
            usado=usado,
            total=volume["size_bytes"],
        )

    def _cartao_de_imagem(self) -> CartaoDeDispositivo:
        return CartaoDeDispositivo(
            {"tipo": "imagem", "dados": {"path": self.imagem}},
            "Imagem de disco",
            self.imagem or "Abrir um ficheiro .dd, .img ou .raw",
            "imagem",
            cor="roxo",
        )

    # ------------------------------------------------------------- seleccao

    def _seleccionar(self, dados: dict) -> None:
        if dados["tipo"] == "imagem" and not dados["dados"].get("path"):
            self.imagem_pedida.emit()
            return
        self.seleccionado = dados
        for cartao in self.cartoes:
            cartao.definir_seleccionado(cartao.dados is dados)
        self.mostrar_detalhes()

    def _activar(self, dados: dict) -> None:
        self._seleccionar(dados)
        self._pedir_varrimento()

    def definir_imagem(self, caminho: str) -> None:
        """Regista a imagem escolhida e selecciona-a."""
        self.imagem = caminho
        self.carregar()
        for cartao in self.cartoes:
            if cartao.dados["tipo"] == "imagem":
                self._seleccionar(cartao.dados)
                break

    def informacao_do_dispositivo(self) -> dict:
        """Tipo, capacidade e sistema de ficheiros do que esta seleccionado."""
        if self.seleccionado is None:
            return {}
        tipo = self.seleccionado["tipo"]
        dados = self.seleccionado["dados"]
        if tipo == "disco":
            return {"device_type": "Disco fisico",
                    "device_size": dados.get("size_bytes"),
                    "filesystem": None}
        if tipo == "volume":
            return {"device_type": dados.get("drive_type"),
                    "device_size": dados.get("size_bytes"),
                    "filesystem": dados.get("filesystem")}
        return {"device_type": "Imagem de disco", "device_size": None,
                "filesystem": None}

    def seleccao(self) -> dict | None:
        return self.seleccionado

    def dispositivo_selecionado(self) -> str | None:
        """Caminho do dispositivo seleccionado, para os modulos de analise."""
        if self.seleccionado is None:
            return None
        return self.seleccionado["dados"].get("path")

    # --------------------------------------------------------------- detalhes

    def mostrar_detalhes(self) -> None:
        if self.seleccionado is None:
            self.painel.limpar()
            return
        tipo = self.seleccionado["tipo"]
        dados = self.seleccionado["dados"]
        if tipo == "disco":
            self.painel.mostrar(
                "Disco fisico %d" % dados["index"],
                "Dispositivo • %s" % formatar_tamanho(dados["size_bytes"]),
                [
                    ("Metodo:", NOMES_DOS_METODOS[self.metodo]),
                    ("Tipo:", "Disco fisico"),
                    ("Caminho:", dados["path"]),
                    ("Capacidade:", formatar_tamanho(dados["size_bytes"])),
                    ("Numero fisico:", dados["index"]),
                ],
            )
        elif tipo == "volume":
            self.painel.mostrar(
                "%s (%s:)" % (dados["label"] or "Volume local", dados["letter"]),
                "Volume logico • %s" % formatar_tamanho(dados["size_bytes"]),
                [
                    ("Metodo:", NOMES_DOS_METODOS[self.metodo]),
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
        else:
            self.painel.mostrar(
                "Imagem de disco",
                "Ficheiro de imagem",
                [
                    ("Metodo:", NOMES_DOS_METODOS[self.metodo]),
                    ("Tipo:", "Imagem de disco"),
                    ("Caminho:", dados.get("path") or "-"),
                ],
            )

    def definir_metodo(self, metodo: str) -> None:
        """Escolhe o metodo com que a analise vai ser feita."""
        self.metodo = metodo
        for cartao in self.cartoes_de_metodo:
            cartao.definir_seleccionado(cartao.metodo == metodo)
        self.mostrar_detalhes()

    def _pedir_varrimento(self) -> None:
        device_path = self.dispositivo_selecionado()
        if device_path:
            self.varrimento_pedido.emit(device_path, self.metodo)
