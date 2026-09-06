"""Tema visual da aplicacao: claro institucional com acentos azul-escuro."""

from __future__ import annotations

CORES = {
    "fundo": "#f4f6f8",
    "superficie": "#ffffff",
    "texto": "#1c2530",
    "texto_suave": "#5b6a7a",
    "contorno": "#b9c6d4",
    "contorno_suave": "#cfd8e2",
    "primaria": "#1b4f8a",
    "primaria_escura": "#17416f",
    "primaria_clara": "#c9dcf0",
    "sucesso": "#1e6f3c",
    "sucesso_escura": "#185c31",
    "neutra": "#4a5a6a",
    "neutra_escura": "#3c4a58",
    "aviso": "#b3261e",
    "cabecalho_tabela": "#dde4ec",
    "linha_alternada": "#eef2f6",
    "barra_estado": "#e8edf2",
}

# Nomes de objecto usados para colorir os botoes por funcao.
BOTAO_PRIMARIO = "botaoPrimario"
BOTAO_SUCESSO = "botaoSucesso"
BOTAO_NEUTRO = "botaoNeutro"

STYLESHEET = """
QWidget {{
    background-color: {fundo};
    color: {texto};
    font-size: 10pt;
}}
QFrame#cabecalho {{
    background-color: {primaria};
    border: 0;
}}
QLabel#tituloApp {{
    color: #ffffff;
    font-size: 14pt;
    font-weight: bold;
}}
QLabel#subtituloApp {{
    color: {primaria_clara};
}}
QLabel#utilizadorSessao {{
    color: #ffffff;
    font-weight: bold;
}}
QLabel#avisoPrivilegios {{
    color: {aviso};
    font-weight: bold;
}}
QLabel#estadoOk {{
    color: {sucesso};
    font-weight: bold;
}}
QLabel#erroFormulario {{
    color: {aviso};
    font-weight: bold;
}}
QComboBox, QLineEdit {{
    background-color: {superficie};
    border: 1px solid {contorno};
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox:focus, QLineEdit:focus {{
    border-color: {primaria};
}}
QComboBox:disabled, QLineEdit:disabled {{
    background-color: #eceff3;
    color: {texto_suave};
}}
QPushButton {{
    background-color: #e3e9f0;
    border: 1px solid {contorno};
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #d5dee8;
}}
QPushButton:disabled {{
    background-color: #eceff3;
    color: #93a1b0;
    border-color: {contorno_suave};
}}
QPushButton#{botao_primario} {{
    background-color: {primaria};
    color: #ffffff;
    border-color: {primaria_escura};
}}
QPushButton#{botao_primario}:hover {{
    background-color: {primaria_escura};
}}
QPushButton#{botao_sucesso} {{
    background-color: {sucesso};
    color: #ffffff;
    border-color: {sucesso_escura};
}}
QPushButton#{botao_sucesso}:hover {{
    background-color: {sucesso_escura};
}}
QPushButton#{botao_neutro} {{
    background-color: {neutra};
    color: #ffffff;
    border-color: {neutra_escura};
}}
QPushButton#{botao_neutro}:hover {{
    background-color: {neutra_escura};
}}
QPushButton#{botao_primario}:disabled,
QPushButton#{botao_sucesso}:disabled,
QPushButton#{botao_neutro}:disabled {{
    background-color: #eceff3;
    color: #93a1b0;
    border-color: {contorno_suave};
}}
QTableWidget {{
    background-color: {superficie};
    alternate-background-color: {linha_alternada};
    gridline-color: {contorno_suave};
    border: 1px solid {contorno_suave};
    selection-background-color: {primaria};
    selection-color: #ffffff;
}}
QHeaderView::section {{
    background-color: {cabecalho_tabela};
    color: {texto};
    padding: 6px;
    border: 0;
    border-right: 1px solid {contorno_suave};
    font-weight: bold;
}}
QTableWidget::item {{
    padding: 4px;
}}
QStatusBar {{
    background-color: {barra_estado};
    border-top: 1px solid {contorno_suave};
}}
QStatusBar::item {{
    border: 0;
}}
""".format(
    botao_primario=BOTAO_PRIMARIO,
    botao_sucesso=BOTAO_SUCESSO,
    botao_neutro=BOTAO_NEUTRO,
    **CORES,
)


def apply_theme(widget) -> None:
    """Aplica o tema a uma aplicacao ou a um widget."""
    widget.setStyleSheet(STYLESHEET)
