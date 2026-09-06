"""Componentes visuais reutilizados pelos paineis da aplicacao."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui import icons, theme


class Banner(QLabel):
    """Mensagem em linha, no topo do painel, em vez de uma janela de aviso."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName(theme.BANNER)
        self.setWordWrap(True)
        self.setVisible(False)

    def mostrar(self, texto: str, tipo: str = "info") -> None:
        self.setProperty("tipo", tipo)
        self.setText(texto)
        theme.repolir(self)
        self.setVisible(bool(texto))

    def limpar(self) -> None:
        self.setText("")
        self.setVisible(False)


class CabecalhoDePainel(QWidget):
    """Titulo e descricao no topo de cada painel."""

    def __init__(self, titulo: str, descricao: str = "", parent=None):
        super().__init__(parent)
        self.etiqueta_titulo = QLabel(titulo)
        self.etiqueta_titulo.setObjectName(theme.TITULO_PAINEL)
        self.etiqueta_descricao = QLabel(descricao)
        self.etiqueta_descricao.setObjectName(theme.SUBTITULO)
        self.etiqueta_descricao.setWordWrap(True)
        self.etiqueta_descricao.setVisible(bool(descricao))

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(2)
        disposicao.addWidget(self.etiqueta_titulo)
        disposicao.addWidget(self.etiqueta_descricao)

    def definir_descricao(self, descricao: str) -> None:
        self.etiqueta_descricao.setText(descricao)
        self.etiqueta_descricao.setVisible(bool(descricao))


class PainelDeDetalhes(QFrame):
    """Painel lateral direito com os detalhes do elemento seleccionado."""

    def __init__(self, texto_da_accao: str, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.PAINEL_DETALHES)
        self.setFixedWidth(288)

        self.etiqueta_titulo = QLabel("")
        self.etiqueta_titulo.setObjectName(theme.TITULO_PAINEL)
        self.etiqueta_titulo.setWordWrap(True)
        self.etiqueta_subtitulo = QLabel("")
        self.etiqueta_subtitulo.setObjectName(theme.SUBTITULO)
        self.etiqueta_subtitulo.setWordWrap(True)

        self.botao_accao = QPushButton(texto_da_accao)
        self.botao_accao.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_accao.setMinimumHeight(34)
        self.botao_accao.setEnabled(False)

        self.etiqueta_geral = QLabel("Geral")
        self.etiqueta_geral.setObjectName(theme.ROTULO_CAMPO)
        self.etiqueta_geral.setVisible(False)

        self.campos = QFormLayout()
        self.campos.setLabelAlignment(Qt.AlignLeft)
        self.campos.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.campos.setHorizontalSpacing(10)
        self.campos.setVerticalSpacing(6)

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(16, 16, 16, 16)
        disposicao.setSpacing(10)
        disposicao.addWidget(self.etiqueta_titulo)
        disposicao.addWidget(self.etiqueta_subtitulo)
        disposicao.addWidget(self.botao_accao)
        disposicao.addWidget(self.etiqueta_geral)
        disposicao.addLayout(self.campos)
        disposicao.addStretch(1)

    def limpar(self) -> None:
        self.etiqueta_titulo.setText("")
        self.etiqueta_subtitulo.setText("")
        self.etiqueta_geral.setVisible(False)
        self.botao_accao.setEnabled(False)
        while self.campos.count():
            item = self.campos.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def mostrar(self, titulo: str, subtitulo: str, campos: list[tuple]) -> None:
        """Preenche o painel com o titulo, o subtitulo e os pares campo/valor."""
        self.limpar()
        self.etiqueta_titulo.setText(titulo)
        self.etiqueta_subtitulo.setText(subtitulo)
        self.etiqueta_geral.setVisible(bool(campos))
        for rotulo, valor in campos:
            etiqueta = QLabel(str(rotulo))
            etiqueta.setObjectName(theme.ROTULO_CAMPO)
            conteudo = QLabel(str(valor))
            conteudo.setObjectName(theme.VALOR_CAMPO)
            conteudo.setWordWrap(True)
            self.campos.addRow(etiqueta, conteudo)
        self.botao_accao.setEnabled(True)

    def valores(self) -> dict:
        """Campos actualmente apresentados (usado nos testes)."""
        resultado = {}
        for linha in range(self.campos.rowCount()):
            rotulo = self.campos.itemAt(linha, QFormLayout.LabelRole)
            valor = self.campos.itemAt(linha, QFormLayout.FieldRole)
            if rotulo is not None and valor is not None:
                resultado[rotulo.widget().text()] = valor.widget().text()
        return resultado


class CartaoDeDispositivo(QFrame):
    """Cartao clicavel com icone, nome, ocupacao e capacidade do dispositivo."""

    escolhido = Signal(object)
    activado = Signal(object)

    def __init__(self, dados: dict, titulo: str, subtitulo: str, nome_do_icone: str,
                 cor: str = "azul", usado: int | None = None,
                 total: int | None = None, parent=None):
        super().__init__(parent)
        self.dados = dados
        self.setObjectName(theme.CARTAO_DISPOSITIVO)
        self.setProperty("seleccionado", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(84)

        self.etiqueta_icone = QLabel()
        self.etiqueta_icone.setPixmap(icons.chip(nome_do_icone, cor))
        self.etiqueta_icone.setFixedSize(44, 44)

        self.etiqueta_nome = QLabel(titulo)
        self.etiqueta_nome.setObjectName(theme.NOME_DO_CARTAO)
        self.etiqueta_detalhe = QLabel(subtitulo)
        self.etiqueta_detalhe.setObjectName(theme.DETALHE_DO_CARTAO)

        self.barra = QProgressBar()
        self.barra.setObjectName(theme.BARRA_CAPACIDADE)
        self.barra.setTextVisible(False)
        self.etiqueta_capacidade = QLabel("")
        self.etiqueta_capacidade.setObjectName(theme.DETALHE_DO_CARTAO)
        self._mostrar_ocupacao(usado, total)

        texto = QVBoxLayout()
        texto.setContentsMargins(0, 0, 0, 0)
        texto.setSpacing(3)
        texto.addWidget(self.etiqueta_nome)
        texto.addWidget(self.etiqueta_detalhe)
        texto.addWidget(self.barra)
        texto.addWidget(self.etiqueta_capacidade)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(14, 12, 14, 12)
        disposicao.setSpacing(12)
        disposicao.addWidget(self.etiqueta_icone, 0, Qt.AlignTop)
        disposicao.addLayout(texto, 1)

    def _mostrar_ocupacao(self, usado, total) -> None:
        if not total or usado is None:
            self.barra.setVisible(False)
            self.etiqueta_capacidade.setVisible(False)
            return
        percentagem = max(0, min(100, round(usado * 100 / total)))
        self.barra.setValue(percentagem)
        self.barra.setProperty("nivel", "alto" if percentagem >= 90 else "normal")
        theme.repolir(self.barra)
        self.etiqueta_capacidade.setText(
            "%s livres de %s" % (formatar_tamanho(total - usado), formatar_tamanho(total))
        )

    def definir_seleccionado(self, seleccionado: bool) -> None:
        self.setProperty("seleccionado", bool(seleccionado))
        theme.repolir(self)

    def esta_seleccionado(self) -> bool:
        return bool(self.property("seleccionado"))

    def mousePressEvent(self, evento):  # noqa: N802 (nome imposto pelo Qt)
        self.escolhido.emit(self.dados)
        super().mousePressEvent(evento)

    def mouseDoubleClickEvent(self, evento):  # noqa: N802 (nome imposto pelo Qt)
        self.activado.emit(self.dados)
        super().mouseDoubleClickEvent(evento)


class TituloDeSeccao(QLabel):
    """Rotulo de seccao com a contagem de elementos, como 'Discos fisicos (2)'."""

    def __init__(self, texto: str, quantidade: int = 0, parent=None):
        super().__init__("", parent)
        self.setObjectName(theme.TITULO_SECCAO)
        self.texto = texto
        self.definir_quantidade(quantidade)

    def definir_quantidade(self, quantidade: int) -> None:
        self.quantidade = quantidade
        self.setText("%s (%d)" % (self.texto, quantidade))


def barra_de_accoes(*widgets) -> QHBoxLayout:
    """Linha horizontal de botoes alinhados a esquerda."""
    disposicao = QHBoxLayout()
    disposicao.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        disposicao.addWidget(widget)
    disposicao.addStretch(1)
    return disposicao


def formatar_tamanho(tamanho_bytes) -> str:
    """Tamanho legivel (B, KB, MB, GB, TB)."""
    if tamanho_bytes is None:
        return "-"
    unidades = ("B", "KB", "MB", "GB", "TB")
    valor = float(tamanho_bytes)
    for unidade in unidades:
        if valor < 1024 or unidade == unidades[-1]:
            return "%.1f %s" % (valor, unidade)
        valor /= 1024
    return "%.1f %s" % (valor, unidades[-1])
