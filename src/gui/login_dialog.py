"""Ecra de autenticacao do perito.

O dialogo so valida credenciais atraves de src/auth.py; nao contem logica de
negocio propria.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.gui import theme

TITULO = "FRDA — Autenticacao"
SUBTITULO = "Ferramenta de Recuperacao de Dados Apagados"
ERRO_CREDENCIAIS = "Utilizador ou password incorrectos."


class LoginDialog(QDialog):
    """Pede as credenciais e expoe a conta autenticada em ``self.user``."""

    def __init__(self, auth_store, parent=None):
        super().__init__(parent)
        self.auth_store = auth_store
        self.user: dict | None = None

        self.setWindowTitle(TITULO)
        self.setMinimumWidth(380)

        titulo = QLabel("FRDA")
        titulo.setObjectName("tituloApp")
        subtitulo = QLabel(SUBTITULO)
        subtitulo.setObjectName("subtituloApp")
        cabecalho_conteudo = QVBoxLayout()
        cabecalho_conteudo.addWidget(titulo)
        cabecalho_conteudo.addWidget(subtitulo)
        cabecalho = QFrame()
        cabecalho.setObjectName("cabecalho")
        cabecalho.setLayout(cabecalho_conteudo)

        self.campo_utilizador = QLineEdit()
        self.campo_utilizador.setPlaceholderText("utilizador")
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.Password)
        self.campo_password.setPlaceholderText("password")

        formulario = QFormLayout()
        formulario.addRow("Utilizador:", self.campo_utilizador)
        formulario.addRow("Password:", self.campo_password)

        self.etiqueta_erro = QLabel("")
        self.etiqueta_erro.setObjectName("erroFormulario")
        self.etiqueta_erro.setWordWrap(True)

        self.botao_entrar = QPushButton("Entrar")
        self.botao_entrar.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_entrar.setDefault(True)
        self.botao_cancelar = QPushButton("Cancelar")

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        botoes.addWidget(self.botao_cancelar)
        botoes.addWidget(self.botao_entrar)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(0, 0, 0, 0)
        conteudo.addWidget(cabecalho)
        corpo = QVBoxLayout()
        corpo.setContentsMargins(16, 16, 16, 16)
        corpo.addLayout(formulario)
        corpo.addWidget(self.etiqueta_erro)
        corpo.addLayout(botoes)
        conteudo.addLayout(corpo)
        self.setLayout(conteudo)

        self.botao_entrar.clicked.connect(self.autenticar)
        self.botao_cancelar.clicked.connect(self.reject)
        self.campo_password.returnPressed.connect(self.autenticar)
        self.campo_utilizador.returnPressed.connect(self.autenticar)
        self.campo_utilizador.setFocus(Qt.OtherFocusReason)

    def autenticar(self) -> None:
        """Valida as credenciais e fecha o dialogo em caso de sucesso."""
        conta = self.auth_store.authenticate(
            self.campo_utilizador.text(), self.campo_password.text()
        )
        if conta is None:
            self.user = None
            self.etiqueta_erro.setText(ERRO_CREDENCIAIS)
            self.campo_password.clear()
            self.campo_password.setFocus(Qt.OtherFocusReason)
            return
        self.user = conta
        self.etiqueta_erro.setText("")
        self.accept()
