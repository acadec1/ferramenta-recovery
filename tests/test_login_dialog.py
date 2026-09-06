"""Testes do ecra de login, do dialogo de contas e do tema (Qt offscreen)."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QWidget

    from src.gui import theme
    from src.gui.account_dialog import ERRO_CONFIRMACAO, NovaContaDialog
    from src.gui.login_dialog import ERRO_CREDENCIAIS, LoginDialog
except ImportError:  # pragma: no cover - depende do ambiente
    LoginDialog = None

from src import auth
from src.auth import ROLE_ADMIN, ROLE_OPERATOR, AuthStore


@unittest.skipIf(LoginDialog is None, "PySide6 nao esta instalado")
class DialogoBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patcher = mock.patch.object(auth, "ITERATIONS", 1000)  # PBKDF2 mais rapido
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = AuthStore(":memory:")
        self.store.ensure_default_accounts()
        self.addCleanup(self.store.close)


class LoginDialogTest(DialogoBase):
    def _dialogo(self):
        dialogo = LoginDialog(self.store)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_credenciais_do_administrador(self):
        dialogo = self._dialogo()
        dialogo.campo_utilizador.setText("admin")
        dialogo.campo_password.setText("admin123")

        dialogo.botao_entrar.click()

        self.assertEqual(dialogo.user["username"], "admin")
        self.assertEqual(dialogo.user["role"], ROLE_ADMIN)
        self.assertEqual(dialogo.result(), QDialog.Accepted)

    def test_credenciais_do_operador(self):
        dialogo = self._dialogo()
        dialogo.campo_utilizador.setText("operador")
        dialogo.campo_password.setText("operador123")

        dialogo.botao_entrar.click()

        self.assertEqual(dialogo.user["role"], ROLE_OPERATOR)

    def test_password_errada(self):
        dialogo = self._dialogo()
        dialogo.campo_utilizador.setText("admin")
        dialogo.campo_password.setText("errada")

        dialogo.botao_entrar.click()

        self.assertIsNone(dialogo.user)
        self.assertEqual(dialogo.etiqueta_erro.text(), ERRO_CREDENCIAIS)
        self.assertEqual(dialogo.campo_password.text(), "")  # campo limpo
        self.assertTrue(dialogo.isVisible() or dialogo.result() != QDialog.Accepted)

    def test_utilizador_inexistente(self):
        dialogo = self._dialogo()
        dialogo.campo_utilizador.setText("ninguem")
        dialogo.campo_password.setText("seja o que for")

        dialogo.botao_entrar.click()

        self.assertIsNone(dialogo.user)
        self.assertEqual(dialogo.etiqueta_erro.text(), ERRO_CREDENCIAIS)

    def test_campos_vazios(self):
        dialogo = self._dialogo()
        dialogo.botao_entrar.click()
        self.assertIsNone(dialogo.user)
        self.assertEqual(dialogo.etiqueta_erro.text(), ERRO_CREDENCIAIS)

    def test_enter_no_campo_da_password_autentica(self):
        dialogo = self._dialogo()
        dialogo.campo_utilizador.setText("admin")
        dialogo.campo_password.setText("admin123")

        dialogo.campo_password.returnPressed.emit()

        self.assertEqual(dialogo.result(), QDialog.Accepted)

    def test_cancelar(self):
        dialogo = self._dialogo()
        dialogo.botao_cancelar.click()
        self.assertIsNone(dialogo.user)
        self.assertEqual(dialogo.result(), QDialog.Rejected)

    def test_password_escondida_e_botao_com_tema(self):
        dialogo = self._dialogo()
        self.assertEqual(dialogo.campo_password.echoMode(), QLineEdit.Password)
        self.assertEqual(dialogo.botao_entrar.objectName(), theme.BOTAO_PRIMARIO)


class NovaContaDialogTest(DialogoBase):
    def _dialogo(self):
        dialogo = NovaContaDialog(self.store)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _preencher(self, dialogo, utilizador, password, confirmacao=None, perfil=None):
        dialogo.campo_utilizador.setText(utilizador)
        dialogo.campo_password.setText(password)
        dialogo.campo_confirmacao.setText(
            password if confirmacao is None else confirmacao
        )
        if perfil is not None:
            dialogo.combo_perfil.setCurrentText(perfil)

    def test_cria_conta(self):
        dialogo = self._dialogo()
        self._preencher(dialogo, "perito3", "pass-forte", perfil=ROLE_OPERATOR)

        dialogo.botao_criar.click()

        self.assertEqual(dialogo.criada, "perito3")
        self.assertEqual(dialogo.result(), QDialog.Accepted)
        conta = self.store.authenticate("perito3", "pass-forte")
        self.assertEqual(conta["role"], ROLE_OPERATOR)

    def test_perfis_disponiveis(self):
        dialogo = self._dialogo()
        perfis = [
            dialogo.combo_perfil.itemData(i) for i in range(dialogo.combo_perfil.count())
        ]
        self.assertEqual(perfis, [ROLE_ADMIN, ROLE_OPERATOR])

    def test_passwords_diferentes(self):
        dialogo = self._dialogo()
        self._preencher(dialogo, "perito4", "uma", confirmacao="outra")

        dialogo.botao_criar.click()

        self.assertIsNone(dialogo.criada)
        self.assertEqual(dialogo.etiqueta_erro.text(), ERRO_CONFIRMACAO)
        self.assertIsNone(self.store.authenticate("perito4", "uma"))

    def test_nome_duplicado(self):
        dialogo = self._dialogo()
        self._preencher(dialogo, "admin", "outra-pass")

        dialogo.botao_criar.click()

        self.assertIsNone(dialogo.criada)
        self.assertIn("admin", dialogo.etiqueta_erro.text())
        self.assertIsNotNone(self.store.authenticate("admin", "admin123"))

    def test_campos_obrigatorios(self):
        dialogo = self._dialogo()
        self._preencher(dialogo, "", "")

        dialogo.botao_criar.click()

        self.assertIsNone(dialogo.criada)
        self.assertNotEqual(dialogo.etiqueta_erro.text(), "")

    def test_cancelar(self):
        dialogo = self._dialogo()
        dialogo.botao_cancelar.click()
        self.assertIsNone(dialogo.criada)
        self.assertEqual(dialogo.result(), QDialog.Rejected)


@unittest.skipIf(LoginDialog is None, "PySide6 nao esta instalado")
class TemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_stylesheet_usa_a_paleta(self):
        self.assertIn(theme.CORES["primaria"], theme.STYLESHEET)
        self.assertIn(theme.CORES["cabecalho_tabela"], theme.STYLESHEET)
        self.assertIn("QPushButton#" + theme.BOTAO_PRIMARIO, theme.STYLESHEET)
        self.assertIn("QPushButton#" + theme.BOTAO_SUCESSO, theme.STYLESHEET)
        self.assertIn("QLabel#avisoPrivilegios", theme.STYLESHEET)

    def test_stylesheet_sem_marcadores_por_substituir(self):
        for chave in theme.CORES:
            self.assertNotIn("{%s}" % chave, theme.STYLESHEET)
        self.assertNotIn("{botao_primario}", theme.STYLESHEET)
        self.assertNotIn("}}", theme.STYLESHEET)  # chavetas duplicadas do format

    def test_apply_theme(self):
        widget = QWidget()
        self.addCleanup(widget.deleteLater)
        theme.apply_theme(widget)
        self.assertEqual(widget.styleSheet(), theme.STYLESHEET)


if __name__ == "__main__":
    unittest.main()
