"""Painel de contas de acesso (reservado ao perfil administrador)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.auth import PERMISSIONS, ROLES
from src.gui import theme
from src.gui.widgets import CabecalhoDePainel

TITULO = "Contas e perfis de acesso"
DESCRICAO = "O administrador faz tudo; o operador so escaneia e recupera."
COLUNAS = ("Utilizador", "Perfil", "Criada em")
ERRO_CONFIRMACAO = "As passwords nao coincidem."


class AccountsPage(QWidget):
    """Lista as contas existentes e permite criar novas."""

    conta_criada = Signal(str)

    def __init__(self, auth_store, parent=None):
        super().__init__(parent)
        self.auth_store = auth_store

        self.cabecalho = CabecalhoDePainel(TITULO, DESCRICAO)

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
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.campo_utilizador = QLineEdit()
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.Password)
        self.campo_confirmacao = QLineEdit()
        self.campo_confirmacao.setEchoMode(QLineEdit.Password)
        self.combo_perfil = QComboBox()
        for perfil in ROLES:
            self.combo_perfil.addItem(perfil, perfil)

        formulario = QFormLayout()
        formulario.setHorizontalSpacing(12)
        formulario.setVerticalSpacing(8)
        formulario.addRow("Utilizador:", self.campo_utilizador)
        formulario.addRow("Password:", self.campo_password)
        formulario.addRow("Confirmar:", self.campo_confirmacao)
        formulario.addRow("Perfil:", self.combo_perfil)

        self.etiqueta_erro = QLabel("")
        self.etiqueta_erro.setObjectName("erroFormulario")
        self.etiqueta_erro.setWordWrap(True)

        self.botao_criar = QPushButton("Criar conta")
        self.botao_criar.setObjectName(theme.BOTAO_PRIMARIO)

        titulo_formulario = QLabel("Nova conta")
        titulo_formulario.setObjectName(theme.TITULO_PAINEL)
        permissoes = QLabel(self._descricao_das_permissoes())
        permissoes.setObjectName(theme.SUBTITULO)
        permissoes.setWordWrap(True)

        cartao_conteudo = QVBoxLayout()
        cartao_conteudo.setContentsMargins(16, 16, 16, 16)
        cartao_conteudo.setSpacing(10)
        cartao_conteudo.addWidget(titulo_formulario)
        cartao_conteudo.addLayout(formulario)
        cartao_conteudo.addWidget(self.etiqueta_erro)
        cartao_conteudo.addWidget(self.botao_criar)
        cartao_conteudo.addWidget(permissoes)
        cartao_conteudo.addStretch(1)

        cartao = QFrame()
        cartao.setObjectName(theme.PAINEL_DETALHES)
        cartao.setFixedWidth(300)
        cartao.setLayout(cartao_conteudo)

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(20, 18, 16, 18)
        conteudo.setSpacing(12)
        conteudo.addWidget(self.cabecalho)
        conteudo.addWidget(self.tabela)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(0)
        disposicao.addLayout(conteudo, 1)
        disposicao.addWidget(cartao)

        self.botao_criar.clicked.connect(self.criar_conta)

    @staticmethod
    def _descricao_das_permissoes() -> str:
        return "\n".join(
            "%s: %s" % (perfil, ", ".join(permissoes))
            for perfil, permissoes in PERMISSIONS.items()
        )

    def carregar(self) -> None:
        """Actualiza a lista de contas existentes."""
        contas = self.auth_store.list_users()
        self.tabela.setRowCount(len(contas))
        for linha, conta in enumerate(contas):
            valores = (conta["username"], conta["role"], conta["created_at"][:19])
            for coluna, valor in enumerate(valores):
                self.tabela.setItem(linha, coluna, QTableWidgetItem(str(valor)))

    def criar_conta(self) -> None:
        """Cria a conta com os dados do formulario."""
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

        criada = self.campo_utilizador.text().strip()
        self.etiqueta_erro.setText("")
        self.campo_utilizador.clear()
        self.campo_password.clear()
        self.campo_confirmacao.clear()
        self.carregar()
        self.conta_criada.emit(criada)
