"""Tema visual da aplicacao: claro institucional, no estilo de uma app de desktop.

Barra lateral cinzenta clara, area de conteudo branca, acento azul e painel de
detalhes a direita — o mesmo esquema em todos os paineis, para que a navegacao
nao pareca uma sucessao de janelas diferentes.
"""

from __future__ import annotations

CORES = {
    "fundo": "#f7f8fa",
    "superficie": "#ffffff",
    "lateral": "#f3f4f6",
    "painel": "#fbfcfd",
    "texto": "#1b1f23",
    "texto_suave": "#6b7280",
    "contorno": "#e5e7eb",
    "contorno_forte": "#d3d8de",
    "primaria": "#0f6cbd",
    "primaria_escura": "#0b5aa2",
    "primaria_clara": "#e8f0fa",
    "sucesso": "#1e7a44",
    "sucesso_clara": "#e6f4ea",
    "aviso": "#8a5a00",
    "aviso_clara": "#fdf3e0",
    "erro": "#b3261e",
    "erro_clara": "#fbeae9",
    "seleccao": "#e8f0fa",
}

# Nomes de objecto usados pelos paineis para se ligarem ao tema.
BOTAO_PRIMARIO = "botaoPrimario"
BOTAO_SECUNDARIO = "botaoSecundario"
BARRA_LATERAL = "barraLateral"
MENU_LATERAL = "menuLateral"
SECCAO_LATERAL = "seccaoLateral"
CABECALHO = "cabecalhoJanela"
TITULO_JANELA = "tituloJanela"
SUBTITULO = "subtitulo"
PAINEL_DETALHES = "painelDetalhes"
TITULO_PAINEL = "tituloPainel"
BANNER = "banner"
CARTAO = "cartao"
PAGINA_LOGIN = "paginaLogin"
ROTULO_CAMPO = "rotuloCampo"
VALOR_CAMPO = "valorCampo"

FAMILIA_DE_LETRA = '"Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'

STYLESHEET = """
QWidget {{
    background-color: {superficie};
    color: {texto};
    font-family: {familia};
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {fundo};
}}
QWidget#{pagina_login} {{
    background-color: {fundo};
}}

/* ---------------------------------------------------------- barra lateral */
QWidget#{barra_lateral} {{
    background-color: {lateral};
    border-right: 1px solid {contorno};
}}
QLabel#{seccao_lateral} {{
    background-color: transparent;
    color: {texto_suave};
    font-weight: bold;
    padding: 14px 14px 4px 14px;
}}
QListWidget#{menu_lateral} {{
    background-color: transparent;
    border: 0;
    outline: 0;
    padding: 4px 8px;
}}
QListWidget#{menu_lateral}::item {{
    background-color: transparent;
    border-radius: 6px;
    padding: 7px 10px;
    margin: 1px 0;
    color: {texto};
}}
QListWidget#{menu_lateral}::item:hover {{
    background-color: #e9ebef;
}}
QListWidget#{menu_lateral}::item:selected {{
    background-color: {primaria_clara};
    color: {primaria_escura};
    font-weight: bold;
}}
QListWidget#{menu_lateral}::item:disabled {{
    color: {texto_suave};
    font-weight: bold;
    background-color: transparent;
    padding: 12px 4px 2px 4px;
}}

/* -------------------------------------------------------------- cabecalho */
QFrame#{cabecalho} {{
    background-color: {superficie};
    border-bottom: 1px solid {contorno};
}}
QLabel#{titulo_janela} {{
    font-size: 13pt;
    font-weight: bold;
}}
QLabel#{subtitulo} {{
    color: {texto_suave};
}}
QLabel#{titulo_painel} {{
    font-size: 11pt;
    font-weight: bold;
}}
QLabel#{rotulo_campo} {{
    color: {texto_suave};
}}
QLabel#{valor_campo} {{
    color: {texto};
}}

/* ---------------------------------------------------- painel de detalhes */
QFrame#{painel_detalhes} {{
    background-color: {painel};
    border-left: 1px solid {contorno};
}}
QFrame#{painel_detalhes} QLabel {{
    background-color: transparent;
}}
QFrame#{cartao} {{
    background-color: {superficie};
    border: 1px solid {contorno};
    border-radius: 8px;
}}

/* ----------------------------------------------------------------- avisos */
QLabel#{banner} {{
    border-radius: 6px;
    padding: 8px 12px;
    background-color: {primaria_clara};
    color: {primaria_escura};
}}
QLabel#{banner}[tipo="sucesso"] {{
    background-color: {sucesso_clara};
    color: {sucesso};
}}
QLabel#{banner}[tipo="aviso"] {{
    background-color: {aviso_clara};
    color: {aviso};
}}
QLabel#{banner}[tipo="erro"] {{
    background-color: {erro_clara};
    color: {erro};
}}
QLabel#avisoPrivilegios {{
    color: {erro};
    font-weight: bold;
}}
QLabel#estadoOk {{
    color: {sucesso};
    font-weight: bold;
}}
QLabel#erroFormulario {{
    color: {erro};
}}

/* ---------------------------------------------------------------- campos */
QComboBox, QLineEdit {{
    background-color: {superficie};
    border: 1px solid {contorno_forte};
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 18px;
}}
QComboBox:focus, QLineEdit:focus {{
    border-color: {primaria};
}}
QComboBox::drop-down {{
    border: 0;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {superficie};
    border: 1px solid {contorno_forte};
    selection-background-color: {seleccao};
    selection-color: {texto};
}}

/* --------------------------------------------------------------- botoes */
QPushButton {{
    background-color: {superficie};
    border: 1px solid {contorno_forte};
    border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton:hover {{
    background-color: #f0f2f5;
}}
QPushButton:disabled {{
    background-color: #f3f4f6;
    color: #a5adb8;
    border-color: {contorno};
}}
QPushButton#{botao_primario} {{
    background-color: {primaria};
    color: #ffffff;
    border: 1px solid {primaria_escura};
    font-weight: bold;
}}
QPushButton#{botao_primario}:hover {{
    background-color: {primaria_escura};
}}
QPushButton#{botao_primario}:disabled {{
    background-color: #f3f4f6;
    color: #a5adb8;
    border-color: {contorno};
}}
QPushButton#{botao_secundario} {{
    background-color: {superficie};
    border: 1px solid {contorno_forte};
}}

/* --------------------------------------------------------------- tabelas */
QTreeWidget, QTableWidget {{
    background-color: {superficie};
    alternate-background-color: #fafbfc;
    border: 1px solid {contorno};
    border-radius: 8px;
    gridline-color: {contorno};
    outline: 0;
    selection-background-color: {seleccao};
    selection-color: {texto};
}}
QTreeWidget::item, QTableWidget::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {contorno};
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {seleccao};
    color: {texto};
}}
QHeaderView::section {{
    background-color: {superficie};
    color: {texto_suave};
    padding: 8px 6px;
    border: 0;
    border-bottom: 1px solid {contorno_forte};
    font-weight: bold;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c9ced6;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}

/* ---------------------------------------------------------- barra estado */
QStatusBar {{
    background-color: {lateral};
    border-top: 1px solid {contorno};
    color: {texto_suave};
}}
QStatusBar::item {{
    border: 0;
}}
""".format(
    familia=FAMILIA_DE_LETRA,
    barra_lateral=BARRA_LATERAL,
    menu_lateral=MENU_LATERAL,
    seccao_lateral=SECCAO_LATERAL,
    cabecalho=CABECALHO,
    titulo_janela=TITULO_JANELA,
    subtitulo=SUBTITULO,
    painel_detalhes=PAINEL_DETALHES,
    titulo_painel=TITULO_PAINEL,
    banner=BANNER,
    cartao=CARTAO,
    rotulo_campo=ROTULO_CAMPO,
    valor_campo=VALOR_CAMPO,
    pagina_login=PAGINA_LOGIN,
    botao_primario=BOTAO_PRIMARIO,
    botao_secundario=BOTAO_SECUNDARIO,
    **CORES,
)


def apply_theme(widget) -> None:
    """Aplica o tema a uma aplicacao ou a um widget."""
    widget.setStyleSheet(STYLESHEET)


def repolir(widget) -> None:
    """Reaplica o estilo depois de mudar o objectName ou uma propriedade."""
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)
    widget.update()
