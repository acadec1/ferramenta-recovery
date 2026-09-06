"""Painel de autenticacao, apresentado dentro da janela principal."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui import theme

TITULO = "Iniciar sessao"
DESCRICAO = "Identifique-se para aceder a ferramenta de recuperacao."
ERRO_CREDENCIAIS = "Utilizador ou password incorrectos."


class LoginPage(QWidget):
    """Formulario de entrada; emite ``autenticado`` com a conta validada."""

    autenticado = Signal(dict)

    def __init__(self, auth_store, parent=None):
        super().__init__(parent)
        self.auth_store = auth_store
        self.user: dict | None = None
        self.setObjectName(theme.PAGINA_LOGIN)

        titulo_app = QLabel("FRDA")
        titulo_app.setObjectName(theme.TITULO_JANELA)
        subtitulo_app = QLabel("Ferramenta de Recuperacao de Dados Apagados")
        subtitulo_app.setObjectName(theme.SUBTITULO)

        titulo = QLabel(TITULO)
        titulo.setObjectName(theme.TITULO_PAINEL)
        descricao = QLabel(DESCRICAO)
        descricao.setObjectName(theme.SUBTITULO)
        descricao.setWordWrap(True)

        self.campo_utilizador = QLineEdit()
        self.campo_utilizador.setPlaceholderText("utilizador")
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.Password)
        self.campo_password.setPlaceholderText("password")

        formulario = QFormLayout()
        formulario.setHorizontalSpacing(12)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Utilizador:", self.campo_utilizador)
        formulario.addRow("Password:", self.campo_password)

        self.etiqueta_erro = QLabel("")
        self.etiqueta_erro.setObjectName("erroFormulario")
        self.etiqueta_erro.setWordWrap(True)

        self.botao_entrar = QPushButton("Entrar")
        self.botao_entrar.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_entrar.setDefault(True)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        botoes.addWidget(self.botao_entrar)

        cartao_conteudo = QVBoxLayout()
        cartao_conteudo.setContentsMargins(28, 24, 28, 24)
        cartao_conteudo.setSpacing(12)
        cartao_conteudo.addWidget(titulo_app)
        cartao_conteudo.addWidget(subtitulo_app)
        cartao_conteudo.addSpacing(8)
        cartao_conteudo.addWidget(titulo)
        cartao_conteudo.addWidget(descricao)
        cartao_conteudo.addLayout(formulario)
        cartao_conteudo.addWidget(self.etiqueta_erro)
        cartao_conteudo.addLayout(botoes)

        cartao = QFrame()
        cartao.setObjectName(theme.CARTAO)
        cartao.setFixedWidth(420)
        cartao.setLayout(cartao_conteudo)

        centro = QHBoxLayout()
        centro.addStretch(1)
        centro.addWidget(cartao)
        centro.addStretch(1)

        disposicao = QVBoxLayout(self)
        disposicao.addStretch(1)
        disposicao.addLayout(centro)
        disposicao.addStretch(2)

        self.botao_entrar.clicked.connect(self.autenticar)
        self.campo_utilizador.returnPressed.connect(self.autenticar)
        self.campo_password.returnPressed.connect(self.autenticar)

    def preparar(self) -> None:
        """Limpa o formulario para uma nova sessao."""
        self.user = None
        self.campo_utilizador.clear()
        self.campo_password.clear()
        self.etiqueta_erro.setText("")
        self.campo_utilizador.setFocus(Qt.OtherFocusReason)

    def autenticar(self) -> None:
        """Valida as credenciais e emite ``autenticado`` em caso de sucesso."""
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
        self.campo_password.clear()
        self.autenticado.emit(conta)
