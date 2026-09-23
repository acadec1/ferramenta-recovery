"""Painel de autenticacao, apresentado dentro da janela principal.

Tem dois formularios no mesmo cartao: entrar e repor a palavra-passe. Trocam
entre si sem abrir janela nenhuma, como o resto da aplicacao.

A reposicao usa a pergunta de seguranca da conta (ver src/auth.py): a
ferramenta trabalha fora de linha e nao tem servidor de correio para enviar
ligacoes de recuperacao.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.auth import email_valido
from src.gui import icons, theme

TITULO = "Iniciar sessao"
DESCRICAO = "Identifique-se com o seu email para aceder a ferramenta."
ERRO_CREDENCIAIS = "Email ou palavra-passe incorrectos."

TITULO_REPOR = "Repor a palavra-passe"
DESCRICAO_REPOR = (
    "Indique o email da conta e responda a pergunta de seguranca para definir "
    "uma nova palavra-passe."
)
SEM_PERGUNTA = "Indique o email da conta e carregue em Procurar."
ERRO_SEM_EMAIL = "Indique o email da conta."
ERRO_EMAIL_INVALIDO = "O email indicado nao tem um formato valido."
# Nao se distingue "conta inexistente" de "conta sem pergunta": o ecra de
# entrada nao deve revelar que enderecos estao registados.
ERRO_SEM_CONTA = (
    "Nao ha pergunta de seguranca para esse email. Peca ao administrador para "
    "repor a palavra-passe."
)
ERRO_CONFIRMACAO = "As palavras-passe nao coincidem."
ERRO_NOVA_VAZIA = "Indique a nova palavra-passe."
ERRO_RESPOSTA = "A resposta nao confere."
SUCESSO_REPOSICAO = "Palavra-passe alterada. Ja pode entrar."


class LoginPage(QWidget):
    """Formulario de entrada; emite ``autenticado`` com a conta validada."""

    autenticado = Signal(dict)

    def __init__(self, auth_store, parent=None):
        super().__init__(parent)
        self.auth_store = auth_store
        self.user: dict | None = None
        self.setObjectName(theme.PAGINA_LOGIN)

        self.ilustracao = QLabel()
        self.ilustracao.setAlignment(Qt.AlignCenter)
        self._mostrar_logotipo()

        titulo_app = QLabel("FRDA")
        titulo_app.setObjectName(theme.TITULO_JANELA)
        titulo_app.setAlignment(Qt.AlignCenter)
        subtitulo_app = QLabel("Ferramenta de Recuperacao de Dados Apagados")
        subtitulo_app.setObjectName(theme.SUBTITULO)
        subtitulo_app.setAlignment(Qt.AlignCenter)

        # Os dois formularios estao no cartao e alternam por visibilidade: um
        # painel escondido nao conta para o tamanho, ao contrario do que
        # acontece num QStackedWidget, que reserva sempre o maior dos dois.
        self.painel_de_entrada = self._construir_entrada()
        self.painel_de_reposicao = self._construir_reposicao()
        self.painel_de_reposicao.setVisible(False)
        self._em_reposicao = False

        cartao_conteudo = QVBoxLayout()
        cartao_conteudo.setContentsMargins(36, 26, 36, 28)
        cartao_conteudo.setSpacing(8)
        cartao_conteudo.addWidget(self.ilustracao, 0, Qt.AlignCenter)
        cartao_conteudo.addWidget(titulo_app)
        cartao_conteudo.addWidget(subtitulo_app)
        cartao_conteudo.addSpacing(8)
        cartao_conteudo.addWidget(self.painel_de_entrada)
        cartao_conteudo.addWidget(self.painel_de_reposicao)

        cartao = QFrame()
        cartao.setObjectName(theme.CARTAO)
        cartao.setFixedWidth(460)
        cartao.setLayout(cartao_conteudo)
        # so ate ao tamanho do conteudo: sem isto o cartao esticava-se ate ao
        # fundo da janela e deixava um vazio por baixo do formulario
        cartao.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)

        centro = QHBoxLayout()
        centro.addStretch(1)
        # com alinhamento o cartao fica com a altura do conteudo, em vez de
        # ser esticado ate ocupar toda a altura da disposicao
        centro.addWidget(cartao, 0, Qt.AlignVCenter)
        centro.addStretch(1)

        # partes iguais em cima e em baixo: o cartao fica ao centro da janela
        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.addStretch(1)
        disposicao.addLayout(centro)
        disposicao.addStretch(1)

    # ----------------------------------------------------------- construcao

    def _mostrar_logotipo(self) -> None:
        """Logotipo da instituicao; se faltar, a ilustracao de recuperacao."""
        if icons.ha_logotipo():
            self.ilustracao.setPixmap(icons.logotipo(140))
        else:
            self.ilustracao.setPixmap(icons.ilustracao("recuperacao", 190))

    def _construir_entrada(self) -> QWidget:
        titulo = QLabel(TITULO)
        titulo.setObjectName(theme.TITULO_PAINEL)
        titulo.setAlignment(Qt.AlignCenter)
        descricao = QLabel(DESCRICAO)
        descricao.setObjectName(theme.SUBTITULO)
        descricao.setWordWrap(True)
        descricao.setAlignment(Qt.AlignCenter)

        self.campo_email = QLineEdit()
        self.campo_email.setPlaceholderText("nome@aaee.mz")
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.Password)
        self.campo_password.setPlaceholderText("palavra-passe")

        formulario = QFormLayout()
        formulario.setHorizontalSpacing(12)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Email:", self.campo_email)
        formulario.addRow("Palavra-passe:", self.campo_password)

        self.etiqueta_erro = QLabel("")
        self.etiqueta_erro.setObjectName("erroFormulario")
        self.etiqueta_erro.setWordWrap(True)
        self.etiqueta_erro.setAlignment(Qt.AlignCenter)

        self.botao_entrar = QPushButton("Entrar")
        self.botao_entrar.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_entrar.setDefault(True)
        self.botao_entrar.setMinimumHeight(38)

        self.botao_esqueci = QPushButton("Esqueci-me da palavra-passe")
        self.botao_esqueci.setObjectName(theme.LIGACAO)
        self.botao_esqueci.setCursor(Qt.PointingHandCursor)
        self.botao_esqueci.setFlat(True)

        disposicao = QVBoxLayout()
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(8)
        disposicao.addWidget(titulo)
        disposicao.addWidget(descricao)
        disposicao.addSpacing(4)
        disposicao.addLayout(formulario)
        disposicao.addWidget(self.etiqueta_erro)
        disposicao.addWidget(self.botao_entrar)
        disposicao.addWidget(self.botao_esqueci, 0, Qt.AlignCenter)

        self.botao_entrar.clicked.connect(self.autenticar)
        self.campo_email.returnPressed.connect(self.autenticar)
        self.campo_password.returnPressed.connect(self.autenticar)
        self.botao_esqueci.clicked.connect(self.mostrar_reposicao)

        painel = QWidget()
        painel.setLayout(disposicao)
        return painel

    def _construir_reposicao(self) -> QWidget:
        titulo = QLabel(TITULO_REPOR)
        titulo.setObjectName(theme.TITULO_PAINEL)
        titulo.setAlignment(Qt.AlignCenter)
        descricao = QLabel(DESCRICAO_REPOR)
        descricao.setObjectName(theme.SUBTITULO)
        descricao.setWordWrap(True)
        descricao.setAlignment(Qt.AlignCenter)

        self.campo_email_reposicao = QLineEdit()
        self.campo_email_reposicao.setPlaceholderText("nome@aaee.mz")
        self.botao_procurar = QPushButton("Procurar")
        self.botao_procurar.setObjectName(theme.BOTAO_SECUNDARIO)

        linha_do_email = QHBoxLayout()
        linha_do_email.setSpacing(8)
        linha_do_email.addWidget(self.campo_email_reposicao, 1)
        linha_do_email.addWidget(self.botao_procurar)

        self.etiqueta_pergunta = QLabel(SEM_PERGUNTA)
        self.etiqueta_pergunta.setObjectName(theme.SUBTITULO)
        self.etiqueta_pergunta.setWordWrap(True)

        self.campo_resposta = QLineEdit()
        self.campo_resposta.setEchoMode(QLineEdit.Password)
        self.campo_resposta.setPlaceholderText("resposta")
        self.campo_nova = QLineEdit()
        self.campo_nova.setEchoMode(QLineEdit.Password)
        self.campo_nova.setPlaceholderText("nova palavra-passe")
        self.campo_confirmacao = QLineEdit()
        self.campo_confirmacao.setEchoMode(QLineEdit.Password)
        self.campo_confirmacao.setPlaceholderText("repetir")

        formulario = QFormLayout()
        formulario.setHorizontalSpacing(12)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Email:", linha_do_email)
        formulario.addRow("Pergunta:", self.etiqueta_pergunta)
        formulario.addRow("Resposta:", self.campo_resposta)
        formulario.addRow("Nova:", self.campo_nova)
        formulario.addRow("Confirmar:", self.campo_confirmacao)

        self.etiqueta_erro_reposicao = QLabel("")
        self.etiqueta_erro_reposicao.setObjectName("erroFormulario")
        self.etiqueta_erro_reposicao.setWordWrap(True)
        self.etiqueta_erro_reposicao.setAlignment(Qt.AlignCenter)

        self.botao_definir = QPushButton("Definir nova palavra-passe")
        self.botao_definir.setObjectName(theme.BOTAO_PRIMARIO)
        self.botao_definir.setMinimumHeight(38)
        self.botao_voltar = QPushButton("Voltar ao inicio de sessao")
        self.botao_voltar.setObjectName(theme.LIGACAO)
        self.botao_voltar.setCursor(Qt.PointingHandCursor)
        self.botao_voltar.setFlat(True)

        disposicao = QVBoxLayout()
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(8)
        disposicao.addWidget(titulo)
        disposicao.addWidget(descricao)
        disposicao.addSpacing(4)
        disposicao.addLayout(formulario)
        disposicao.addWidget(self.etiqueta_erro_reposicao)
        disposicao.addWidget(self.botao_definir)
        disposicao.addWidget(self.botao_voltar, 0, Qt.AlignCenter)

        self.botao_procurar.clicked.connect(self.procurar_pergunta)
        self.campo_email_reposicao.returnPressed.connect(self.procurar_pergunta)
        self.botao_definir.clicked.connect(self.repor_password)
        self.campo_confirmacao.returnPressed.connect(self.repor_password)
        self.botao_voltar.clicked.connect(self.mostrar_entrada)

        painel = QWidget()
        painel.setLayout(disposicao)
        return painel

    # --------------------------------------------------------------- estado

    def preparar(self) -> None:
        """Limpa os formularios para uma nova sessao."""
        self.user = None
        self.campo_email.clear()
        self.campo_password.clear()
        self._mensagem("")
        self.mostrar_entrada()
        self.campo_email.setFocus(Qt.OtherFocusReason)

    def mostrar_entrada(self) -> None:
        """Volta ao formulario de entrada, limpando o de reposicao."""
        self.campo_email_reposicao.clear()
        self.campo_resposta.clear()
        self.campo_nova.clear()
        self.campo_confirmacao.clear()
        self.etiqueta_pergunta.setText(SEM_PERGUNTA)
        self.etiqueta_erro_reposicao.setText("")
        self._trocar_formulario(reposicao=False)
        self.campo_email.setFocus(Qt.OtherFocusReason)

    def mostrar_reposicao(self) -> None:
        """Abre o formulario de reposicao, ja com o email escrito."""
        self.campo_email_reposicao.setText(self.campo_email.text())
        self._mensagem("")
        self._trocar_formulario(reposicao=True)
        self.campo_email_reposicao.setFocus(Qt.OtherFocusReason)
        if self.campo_email_reposicao.text().strip():
            self.procurar_pergunta()

    def _trocar_formulario(self, reposicao: bool) -> None:
        self._em_reposicao = reposicao
        self.painel_de_entrada.setVisible(not reposicao)
        self.painel_de_reposicao.setVisible(reposicao)

    def em_reposicao(self) -> bool:
        """Estado guardado, e nao isVisible(): a pagina pode estar escondida."""
        return self._em_reposicao

    # ------------------------------------------------------------- accoes

    def autenticar(self) -> None:
        """Valida as credenciais e emite ``autenticado`` em caso de sucesso."""
        conta = self.auth_store.authenticate(
            self.campo_email.text(), self.campo_password.text()
        )
        if conta is None:
            self.user = None
            self._mensagem(ERRO_CREDENCIAIS)
            self.campo_password.clear()
            self.campo_password.setFocus(Qt.OtherFocusReason)
            return
        self.user = conta
        self._mensagem("")
        self.campo_password.clear()
        self.autenticado.emit(conta)

    def procurar_pergunta(self) -> None:
        """Mostra a pergunta de seguranca da conta indicada."""
        email = self.campo_email_reposicao.text().strip()
        self.etiqueta_erro_reposicao.setText("")
        if not email:
            self.etiqueta_pergunta.setText(SEM_PERGUNTA)
            self.etiqueta_erro_reposicao.setText(ERRO_SEM_EMAIL)
            return
        if not email_valido(email):
            self.etiqueta_pergunta.setText(SEM_PERGUNTA)
            self.etiqueta_erro_reposicao.setText(ERRO_EMAIL_INVALIDO)
            return
        pergunta = self.auth_store.security_question(email)
        if not pergunta:
            self.etiqueta_pergunta.setText(SEM_PERGUNTA)
            self.etiqueta_erro_reposicao.setText(ERRO_SEM_CONTA)
            return
        self.etiqueta_pergunta.setText(pergunta)
        self.campo_resposta.setFocus(Qt.OtherFocusReason)

    def repor_password(self) -> None:
        """Valida a resposta de seguranca e grava a nova palavra-passe."""
        nova = self.campo_nova.text()
        if self.etiqueta_pergunta.text() == SEM_PERGUNTA:
            self.procurar_pergunta()
            return
        if not nova:
            self.etiqueta_erro_reposicao.setText(ERRO_NOVA_VAZIA)
            return
        if nova != self.campo_confirmacao.text():
            self.etiqueta_erro_reposicao.setText(ERRO_CONFIRMACAO)
            self.campo_confirmacao.clear()
            self.campo_confirmacao.setFocus(Qt.OtherFocusReason)
            return
        if not self.auth_store.reset_password(
            self.campo_email_reposicao.text(), self.campo_resposta.text(), nova
        ):
            self.etiqueta_erro_reposicao.setText(ERRO_RESPOSTA)
            self.campo_resposta.clear()
            self.campo_resposta.setFocus(Qt.OtherFocusReason)
            return

        email = self.campo_email_reposicao.text().strip()
        self.mostrar_entrada()
        self.campo_email.setText(email)
        self._mensagem(SUCESSO_REPOSICAO, "sucesso")
        self.campo_password.setFocus(Qt.OtherFocusReason)

    def _mensagem(self, texto: str, tipo: str = "erro") -> None:
        """Mesma etiqueta para erros e confirmacoes, com cores diferentes."""
        self.etiqueta_erro.setProperty("tipo", tipo)
        self.etiqueta_erro.setText(texto)
        theme.repolir(self.etiqueta_erro)
