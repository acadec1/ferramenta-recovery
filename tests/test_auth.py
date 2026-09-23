"""Testes de src/auth.py (contas, perfis e autenticacao)."""

import os
import shutil
import sqlite3
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

ADMIN = "admin@aaee.mz"
OPERADOR = "operador@aaee.mz"
PERGUNTA = "Qual e a sigla da instituicao?"
RESPOSTA = "AAEE"

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
        self.assertEqual(criadas, [ADMIN, OPERADOR])
        contas = {conta["email"]: conta["role"] for conta in self.store.list_users()}
        self.assertEqual(contas, {ADMIN: ROLE_ADMIN, OPERADOR: ROLE_OPERATOR})

    def test_contas_iniciais_nao_se_repetem(self):
        self.store.ensure_default_accounts()
        self.assertEqual(self.store.ensure_default_accounts(), [])
        self.assertEqual(len(self.store.list_users()), 2)

    def test_autenticacao_das_contas_iniciais(self):
        self.store.ensure_default_accounts()
        admin = self.store.authenticate(ADMIN, "admin123")
        operador = self.store.authenticate(OPERADOR, "operador123")
        self.assertEqual(admin["role"], ROLE_ADMIN)
        self.assertEqual(operador["role"], ROLE_OPERATOR)
        self.assertEqual(admin["email"], ADMIN)
        self.assertEqual(admin["username"], "admin")

    def test_password_errada(self):
        self.store.ensure_default_accounts()
        self.assertIsNone(self.store.authenticate(ADMIN, "errada"))

    def test_conta_inexistente(self):
        self.assertIsNone(self.store.authenticate("ninguem@aaee.mz", "o que for"))

    def test_password_vazia(self):
        self.store.ensure_default_accounts()
        self.assertIsNone(self.store.authenticate(ADMIN, ""))
        self.assertIsNone(self.store.authenticate(ADMIN, None))

    def test_criar_conta_nova(self):
        identificador = self.store.create_user(
            "perito2@aaee.mz", "perito2", "outra-pass", ROLE_OPERATOR
        )
        self.assertGreater(identificador, 0)
        conta = self.store.authenticate("perito2@aaee.mz", "outra-pass")
        self.assertEqual(conta["role"], ROLE_OPERATOR)
        self.assertEqual(conta["username"], "perito2")

    def test_email_duplicado(self):
        self.store.create_user("perito2@aaee.mz", "perito2", "pass", ROLE_OPERATOR)
        with self.assertRaises(ValueError):
            self.store.create_user("perito2@aaee.mz", "outro", "outra", ROLE_ADMIN)
        with self.assertRaises(ValueError):  # o email nao distingue maiusculas
            self.store.create_user("PERITO2@AAEE.MZ", "outro", "outra", ROLE_ADMIN)

    def test_nome_duplicado(self):
        self.store.create_user("perito2@aaee.mz", "perito2", "pass", ROLE_OPERATOR)
        with self.assertRaises(ValueError):
            self.store.create_user("outro@aaee.mz", "perito2", "outra", ROLE_ADMIN)

    def test_campos_obrigatorios(self):
        with self.assertRaises(ValueError):
            self.store.create_user("", "perito3", "pass", ROLE_ADMIN)
        with self.assertRaises(ValueError):
            self.store.create_user("perito3@aaee.mz", "   ", "pass", ROLE_ADMIN)
        with self.assertRaises(ValueError):
            self.store.create_user("perito3@aaee.mz", "perito3", "", ROLE_ADMIN)

    def test_email_invalido(self):
        for invalido in ("perito3", "perito3@", "@aaee.mz", "perito3@aaee",
                         "com espaco@aaee.mz"):
            with self.assertRaises(ValueError, msg=invalido):
                self.store.create_user(invalido, "perito3", "pass", ROLE_ADMIN)

    def test_perfil_invalido(self):
        with self.assertRaises(ValueError):
            self.store.create_user("perito3@aaee.mz", "perito3", "pass", "chefe")

    def test_email_e_normalizado(self):
        self.store.create_user("  Perito4@AAEE.mz  ", "perito4", "pass", ROLE_OPERATOR)
        self.assertIsNotNone(self.store.authenticate("perito4@aaee.mz", "pass"))
        self.assertEqual(self.store.list_users()[0]["email"], "perito4@aaee.mz")

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
            self.assertIsNotNone(nova_sessao.authenticate(ADMIN, "admin123"))
        self.store = AuthStore(self.db_path)

    def test_list_users_nao_expoe_passwords(self):
        self.store.ensure_default_accounts()
        for conta in self.store.list_users():
            self.assertNotIn("password_hash", conta)
            self.assertEqual(
                set(conta),
                {"id", "email", "username", "role", "created_at",
                 "security_question"},
            )

    def test_injeccao_sql_no_nome(self):
        self.store.create_user("perito5@aaee.mz", "'; DROP TABLE users; --",
                               "pass", ROLE_ADMIN)
        self.assertEqual(len(self.store.list_users()), 1)


class ReposicaoDaPasswordTest(unittest.TestCase):
    """Reposicao pela pergunta de seguranca: a ferramenta nao tem correio."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.object(auth, "ITERATIONS", ITERACOES_DE_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = AuthStore(os.path.join(self.tmp, "frda_audit.db"))
        self.addCleanup(self.store.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store.ensure_default_accounts()

    def test_contas_iniciais_tem_pergunta(self):
        self.assertEqual(self.store.security_question(ADMIN), PERGUNTA)

    def test_pergunta_de_conta_inexistente(self):
        self.assertIsNone(self.store.security_question("ninguem@aaee.mz"))

    def test_repoe_com_a_resposta_certa(self):
        self.assertTrue(self.store.reset_password(ADMIN, RESPOSTA, "nova-pass"))

        self.assertIsNone(self.store.authenticate(ADMIN, "admin123"))
        self.assertIsNotNone(self.store.authenticate(ADMIN, "nova-pass"))

    def test_resposta_nao_distingue_maiusculas_nem_espacos(self):
        self.assertTrue(
            self.store.reset_password(ADMIN, "  aaee  ", "nova-pass")
        )
        self.assertIsNotNone(self.store.authenticate(ADMIN, "nova-pass"))

    def test_resposta_errada_nao_altera_nada(self):
        self.assertFalse(self.store.reset_password(ADMIN, "errada", "nova-pass"))
        self.assertIsNotNone(self.store.authenticate(ADMIN, "admin123"))

    def test_conta_inexistente_devolve_falso(self):
        self.assertFalse(
            self.store.reset_password("ninguem@aaee.mz", RESPOSTA, "nova-pass")
        )

    def test_conta_sem_pergunta_nao_se_repoe(self):
        self.store.create_user("sem@aaee.mz", "sem", "pass", ROLE_OPERATOR)
        self.assertIsNone(self.store.security_question("sem@aaee.mz"))
        self.assertFalse(self.store.reset_password("sem@aaee.mz", "", "nova"))

    def test_nova_password_vazia_e_recusada(self):
        with self.assertRaises(ValueError):
            self.store.reset_password(ADMIN, RESPOSTA, "")

    def test_resposta_nao_fica_em_claro_na_base_de_dados(self):
        caminho = self.store.db_path
        self.store.close()
        with open(caminho, "rb") as ficheiro:
            conteudo = ficheiro.read()
        self.assertNotIn(b"AAEE\x00", conteudo)
        self.assertNotIn(b"aaee$", conteudo)
        self.store = AuthStore(caminho)

    def test_pergunta_obriga_a_resposta(self):
        with self.assertRaises(ValueError):
            self.store.create_user("novo@aaee.mz", "novo", "pass", ROLE_OPERATOR,
                                   PERGUNTA, "   ")


class MigracaoTest(unittest.TestCase):
    """Uma base de dados sem as colunas do email continua a abrir."""

    def test_contas_antigas_ganham_email(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        caminho = os.path.join(tmp, "antigo.db")
        patcher = mock.patch.object(auth, "ITERATIONS", ITERACOES_DE_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)

        antiga = sqlite3.connect(caminho)
        with antiga:
            antiga.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
                " password_hash TEXT NOT NULL, role TEXT NOT NULL,"
                " created_at TEXT NOT NULL)"
            )
            antiga.execute(
                "INSERT INTO users (username, password_hash, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("admin", auth.hash_password("admin123", iterations=ITERACOES_DE_TESTE),
                 ROLE_ADMIN, "2026-01-01T00:00:00+00:00"),
            )
        antiga.close()

        with AuthStore(caminho) as store:
            contas = store.list_users()
            self.assertEqual(len(contas), 1)
            self.assertEqual(contas[0]["email"], ADMIN)
            # e continua a poder entrar, agora pelo email
            self.assertIsNotNone(store.authenticate(ADMIN, "admin123"))
            # a conta inicial ganha a pergunta por omissao, senao ficava sem
            # forma de repor a palavra-passe
            self.assertEqual(store.security_question(ADMIN), PERGUNTA)
            self.assertTrue(store.reset_password(ADMIN, RESPOSTA, "nova-pass"))

    def test_conta_antiga_que_nao_e_inicial_fica_sem_pergunta(self):
        """So as contas iniciais levam a pergunta por omissao."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        caminho = os.path.join(tmp, "antigo.db")
        patcher = mock.patch.object(auth, "ITERATIONS", ITERACOES_DE_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)

        antiga = sqlite3.connect(caminho)
        with antiga:
            antiga.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
                " password_hash TEXT NOT NULL, role TEXT NOT NULL,"
                " created_at TEXT NOT NULL)"
            )
            antiga.execute(
                "INSERT INTO users (username, password_hash, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("perito9", auth.hash_password("pass", iterations=ITERACOES_DE_TESTE),
                 ROLE_OPERATOR, "2026-01-01T00:00:00+00:00"),
            )
        antiga.close()

        with AuthStore(caminho) as store:
            self.assertIsNone(store.security_question("perito9@aaee.mz"))


if __name__ == "__main__":
    unittest.main()
