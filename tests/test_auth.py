"""Testes de src/auth.py (contas, perfis e autenticacao)."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import auth
from src.auth import (
    PERMISSION_MANAGE_USERS,
    PERMISSION_RECOVER,
    PERMISSION_REPORT,
    PERMISSION_SCAN,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    AuthStore,
)

# PBKDF2 com 200 000 iteracoes torna a suite lenta; nos testes bastam poucas.
ITERACOES_DE_TESTE = 1000


class PermissoesTest(unittest.TestCase):
    def test_administrador_faz_tudo(self):
        for permissao in (
            PERMISSION_SCAN,
            PERMISSION_RECOVER,
            PERMISSION_REPORT,
            PERMISSION_MANAGE_USERS,
        ):
            self.assertTrue(auth.has_permission(ROLE_ADMIN, permissao))

    def test_operador_so_recupera(self):
        self.assertTrue(auth.has_permission(ROLE_OPERATOR, PERMISSION_SCAN))
        self.assertTrue(auth.has_permission(ROLE_OPERATOR, PERMISSION_RECOVER))
        self.assertFalse(auth.has_permission(ROLE_OPERATOR, PERMISSION_REPORT))
        self.assertFalse(auth.has_permission(ROLE_OPERATOR, PERMISSION_MANAGE_USERS))

    def test_perfil_desconhecido_nao_tem_permissoes(self):
        self.assertFalse(auth.has_permission("visitante", PERMISSION_SCAN))
        self.assertFalse(auth.has_permission(None, PERMISSION_SCAN))


class PasswordTest(unittest.TestCase):
    def test_hash_nao_contem_a_password(self):
        resultado = auth.hash_password("admin123", iterations=ITERACOES_DE_TESTE)
        self.assertNotIn("admin123", resultado)
        self.assertTrue(resultado.startswith("pbkdf2_sha256$1000$"))
        self.assertEqual(len(resultado.split("$")), 4)

    def test_salt_diferente_em_cada_hash(self):
        primeiro = auth.hash_password("admin123", iterations=ITERACOES_DE_TESTE)
        segundo = auth.hash_password("admin123", iterations=ITERACOES_DE_TESTE)
        self.assertNotEqual(primeiro, segundo)

    def test_verify_password(self):
        guardado = auth.hash_password("admin123", iterations=ITERACOES_DE_TESTE)
        self.assertTrue(auth.verify_password("admin123", guardado))
        self.assertFalse(auth.verify_password("admin124", guardado))
        self.assertFalse(auth.verify_password("", guardado))

    def test_verify_password_com_hash_invalido(self):
        self.assertFalse(auth.verify_password("admin123", "lixo"))
        self.assertFalse(auth.verify_password("admin123", "md5$1$aa$bb"))
        self.assertFalse(auth.verify_password("admin123", None))


class AuthStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "frda_audit.db")
        patcher = mock.patch.object(auth, "ITERATIONS", ITERACOES_DE_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = AuthStore(self.db_path)
        self.addCleanup(self.store.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_contas_iniciais(self):
        criadas = self.store.ensure_default_accounts()
        self.assertEqual(criadas, ["admin", "operador"])
        contas = {conta["username"]: conta["role"] for conta in self.store.list_users()}
        self.assertEqual(contas, {"admin": ROLE_ADMIN, "operador": ROLE_OPERATOR})

    def test_contas_iniciais_nao_se_repetem(self):
        self.store.ensure_default_accounts()
        self.assertEqual(self.store.ensure_default_accounts(), [])
        self.assertEqual(len(self.store.list_users()), 2)

    def test_autenticacao_das_contas_iniciais(self):
        self.store.ensure_default_accounts()
        admin = self.store.authenticate("admin", "admin123")
        operador = self.store.authenticate("operador", "operador123")
        self.assertEqual(admin["role"], ROLE_ADMIN)
        self.assertEqual(operador["role"], ROLE_OPERATOR)
        self.assertEqual(admin["username"], "admin")

    def test_password_errada(self):
        self.store.ensure_default_accounts()
        self.assertIsNone(self.store.authenticate("admin", "errada"))

    def test_conta_inexistente(self):
        self.assertIsNone(self.store.authenticate("ninguem", "seja o que for"))

    def test_password_vazia(self):
        self.store.ensure_default_accounts()
        self.assertIsNone(self.store.authenticate("admin", ""))
        self.assertIsNone(self.store.authenticate("admin", None))

    def test_criar_conta_nova(self):
        identificador = self.store.create_user("perito2", "outra-pass", ROLE_OPERATOR)
        self.assertGreater(identificador, 0)
        conta = self.store.authenticate("perito2", "outra-pass")
        self.assertEqual(conta["role"], ROLE_OPERATOR)

    def test_nome_duplicado(self):
        self.store.create_user("perito2", "pass", ROLE_OPERATOR)
        with self.assertRaises(ValueError):
            self.store.create_user("perito2", "outra", ROLE_ADMIN)
        with self.assertRaises(ValueError):  # o nome nao distingue maiusculas
            self.store.create_user("PERITO2", "outra", ROLE_ADMIN)

    def test_campos_obrigatorios(self):
        with self.assertRaises(ValueError):
            self.store.create_user("", "pass", ROLE_ADMIN)
        with self.assertRaises(ValueError):
            self.store.create_user("   ", "pass", ROLE_ADMIN)
        with self.assertRaises(ValueError):
            self.store.create_user("perito3", "", ROLE_ADMIN)

    def test_perfil_invalido(self):
        with self.assertRaises(ValueError):
            self.store.create_user("perito3", "pass", "chefe")

    def test_nome_com_espacos_e_normalizado(self):
        self.store.create_user("  perito4  ", "pass", ROLE_OPERATOR)
        self.assertIsNotNone(self.store.authenticate("perito4", "pass"))

    def test_passwords_nao_ficam_em_claro_na_base_de_dados(self):
        self.store.ensure_default_accounts()
        self.store.close()
        with open(self.db_path, "rb") as ficheiro:
            conteudo = ficheiro.read()
        self.assertNotIn(b"admin123", conteudo)
        self.assertNotIn(b"operador123", conteudo)
        self.store = AuthStore(self.db_path)  # reabre para o cleanup

    def test_persistencia_entre_sessoes(self):
        self.store.ensure_default_accounts()
        self.store.close()
        with AuthStore(self.db_path) as nova_sessao:
            self.assertIsNotNone(nova_sessao.authenticate("admin", "admin123"))
        self.store = AuthStore(self.db_path)

    def test_list_users_nao_expoe_passwords(self):
        self.store.ensure_default_accounts()
        for conta in self.store.list_users():
            self.assertNotIn("password_hash", conta)
            self.assertEqual(
                set(conta), {"id", "username", "role", "created_at"}
            )

    def test_injeccao_sql_no_nome(self):
        self.store.create_user("'; DROP TABLE users; --", "pass", ROLE_ADMIN)
        self.assertEqual(len(self.store.list_users()), 1)


if __name__ == "__main__":
    unittest.main()
