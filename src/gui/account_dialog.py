"""Criacao de contas de acesso (accao reservada ao perfil administrador)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.auth import ROLES
from src.gui import theme

TITULO = "FRDA — Nova conta"
ERRO_CONFIRMACAO = "As passwords nao coincidem."


class NovaContaDialog(QDialog):
    """Formulario de criacao de conta; delega a validacao em src/auth.py."""

    def __init__(self, auth_store, parent=None):
        super().__init__(parent)
        self.auth_store = auth_store
        self.criada: str | None = None

        self.setWindowTitle(TITULO)
        self.setMinimumWidth(360)

        self.campo_utilizador = QLineEdit()
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.Password)
        self.campo_confirmacao = QLineEdit()
        self.campo_confirmacao.setEchoMode(QLineEdit.Password)
        self.combo_perfil = QComboBox()
        for perfil in ROLES:
            self.combo_perfil.addItem(perfil, perfil)

        formulario = QFormLayout()
        formulario.addRow("Utilizador:", self.campo_utilizador)
        formulario.addRow("Password:", self.campo_password)
        formulario.addRow("Confirmar:", self.campo_confirmacao)
        formulario.addRow("Perfil:", self.combo_perfil)

        self.etiqueta_erro = QLabel("")
        self.etiqueta_erro.setObjectName("erroFormulario")
        self.etiqueta_erro.setWordWrap(True)

        self.botao_criar = QPushButton("Criar conta")
        self.botao_criar.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_criar.setDefault(True)
        self.botao_cancelar = QPushButton("Cancelar")

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        botoes.addWidget(self.botao_cancelar)
        botoes.addWidget(self.botao_criar)

        conteudo = QVBoxLayout()
        conteudo.addLayout(formulario)
        conteudo.addWidget(self.etiqueta_erro)
        conteudo.addLayout(botoes)
        self.setLayout(conteudo)

        self.botao_criar.clicked.connect(self.criar_conta)
        self.botao_cancelar.clicked.connect(self.reject)

    def criar_conta(self) -> None:
        """Cria a conta e fecha o dialogo; mostra o erro em caso de falha."""
        if self.campo_password.text() != self.campo_confirmacao.text():
            self.etiqueta_erro.setText(ERRO_CONFIRMACAO)
            return
        try:
            self.auth_store.create_user(
                self.campo_utilizador.text(),
                self.campo_password.text(),
                self.combo_perfil.currentData(),
            )
        except ValueError as erro:
            self.etiqueta_erro.setText(str(erro))
            return
        self.criada = self.campo_utilizador.text().strip()
        self.etiqueta_erro.setText("")
        self.accept()
