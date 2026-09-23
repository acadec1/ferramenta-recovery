"""Contas, perfis de acesso e autenticacao dos peritos.

As contas ficam numa tabela ``users`` da mesma base de dados SQLite da auditoria.
O acesso e feito pelo endereco de correio electronico. As passwords nunca sao
guardadas em claro: usa-se PBKDF2-HMAC-SHA256 com salt aleatorio por conta.

Cada conta tem uma pergunta de seguranca com a respectiva resposta, guardada
com o mesmo algoritmo da password. E o que permite repor a palavra-passe sem
servidor de correio: a ferramenta funciona fora de linha.

Perfis:
- administrador: escanear, recuperar, gerar relatorio e gerir contas;
- operador: apenas o fluxo de recuperacao (escanear e recuperar).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import re
import secrets
import sqlite3

# Na pasta da aplicacao e nao na de trabalho do processo: senao as contas
# mudavam conforme a ferramenta fosse aberta pelo explorador, pela linha de
# comandos ou elevada pelo UAC.
PASTA_DA_APLICACAO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(PASTA_DA_APLICACAO, "frda_audit.db")

ROLE_ADMIN = "administrador"
ROLE_OPERATOR = "operador"
ROLES = (ROLE_ADMIN, ROLE_OPERATOR)

PERMISSION_SCAN = "escanear"
PERMISSION_RECOVER = "recuperar"
PERMISSION_REPORT = "relatorio"
PERMISSION_MANAGE_USERS = "contas"

PERMISSIONS: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: (
        PERMISSION_SCAN,
        PERMISSION_RECOVER,
        PERMISSION_REPORT,
        PERMISSION_MANAGE_USERS,
    ),
    ROLE_OPERATOR: (PERMISSION_SCAN, PERMISSION_RECOVER),
}

# Dominio da instituicao, usado nas contas iniciais e como sugestao no formulario.
DOMINIO = "aaee.mz"

# Pergunta de seguranca das contas iniciais. Como a password inicial, deve ser
# mudada na primeira utilizacao real.
DEFAULT_QUESTION = "Qual e a sigla da instituicao?"
DEFAULT_ANSWER = "AAEE"

# Contas criadas no primeiro arranque, se a tabela estiver vazia.
DEFAULT_ACCOUNTS = (
    ("admin@" + DOMINIO, "admin", "admin123", ROLE_ADMIN),
    ("operador@" + DOMINIO, "operador", "operador123", ROLE_OPERATOR),
)

# Perguntas propostas no formulario de criacao de contas.
SECURITY_QUESTIONS = (
    DEFAULT_QUESTION,
    "Qual e o nome do seu primeiro professor?",
    "Em que cidade nasceu?",
    "Qual e o nome da sua primeira escola?",
)

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16

# Verificacao simples: um nome, arroba, um dominio com pelo menos um ponto.
PADRAO_DE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    security_question TEXT,
    security_answer_hash TEXT
)
"""

# Colunas acrescentadas depois da primeira versao, para bases de dados ja
# existentes continuarem a abrir.
COLUNAS_ACRESCENTADAS = ("email", "security_question", "security_answer_hash")
CREATE_EMAIL_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email COLLATE NOCASE)"
)


def has_permission(role: str, permission: str) -> bool:
    """Indica se o perfil indicado tem a permissao pedida."""
    return permission in PERMISSIONS.get(role, ())


def hash_password(password: str, salt: str | None = None,
                  iterations: int | None = None) -> str:
    """Devolve ``algoritmo$iteracoes$salt$hash`` para a password indicada."""
    if iterations is None:
        iterations = ITERATIONS
    if salt is None:
        salt = secrets.token_hex(SALT_BYTES)
    derivada = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return "%s$%d$%s$%s" % (ALGORITHM, iterations, salt, derivada.hex())


def verify_password(password: str, password_hash: str) -> bool:
    """Compara a password com o hash guardado, em tempo constante."""
    try:
        algoritmo, iteracoes, salt, _ = password_hash.split("$")
        if algoritmo != ALGORITHM:
            return False
        candidato = hash_password(password, salt=salt, iterations=int(iteracoes))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(candidato, password_hash)


def normalizar_email(email: str) -> str:
    """Email sem espacos e em minusculas, para o acesso nao depender disso."""
    return (email or "").strip().lower()


def email_valido(email: str) -> bool:
    """Verificacao de forma do endereco, nao da sua existencia."""
    return bool(PADRAO_DE_EMAIL.match(normalizar_email(email)))


def normalizar_resposta(resposta: str) -> str:
    """A resposta de seguranca nao distingue maiusculas nem espacos a mais."""
    return " ".join((resposta or "").split()).lower()


class AuthStore:
    """Repositorio de contas de acesso."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_TABLE)
        self._actualizar_esquema()

    def _actualizar_esquema(self) -> None:
        """Acrescenta as colunas do acesso por email a bases de dados antigas.

        As contas que ja existiam ficam com um endereco derivado do nome de
        utilizador, para continuarem a poder entrar.
        """
        existentes = {
            linha["name"]
            for linha in self.connection.execute("PRAGMA table_info(users)")
        }
        em_falta = [c for c in COLUNAS_ACRESCENTADAS if c not in existentes]
        if em_falta:
            with self.connection:
                for coluna in em_falta:
                    self.connection.execute(
                        "ALTER TABLE users ADD COLUMN %s TEXT" % coluna
                    )
                if "email" in em_falta:
                    self.connection.execute(
                        "UPDATE users SET email = lower(username) || ? "
                        "WHERE email IS NULL OR email = ''",
                        ("@" + DOMINIO,),
                    )
        with self.connection:
            self.connection.execute(CREATE_EMAIL_INDEX)
        self._pergunta_das_contas_iniciais()

    def _pergunta_das_contas_iniciais(self) -> None:
        """Da a pergunta por omissao as contas iniciais que ainda nao a tenham.

        Sem isto, uma instalacao anterior a este campo ficava com as contas
        admin e operador sem forma de reporem a palavra-passe. So se aplica a
        essas duas contas, cuja palavra-passe inicial ja e publica; as contas
        criadas pelo administrador definem a sua propria pergunta.
        """
        iniciais = [email for email, _, _, _ in DEFAULT_ACCOUNTS]
        with self.connection:
            self.connection.execute(
                "UPDATE users SET security_question = ?, security_answer_hash = ?"
                " WHERE email IN (%s) AND (security_question IS NULL"
                " OR security_question = '')" % ", ".join("?" * len(iniciais)),
                [DEFAULT_QUESTION,
                 hash_password(normalizar_resposta(DEFAULT_ANSWER))] + iniciais,
            )

    def __enter__(self) -> "AuthStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def create_user(self, email: str, username: str, password: str, role: str,
                    pergunta: str = "", resposta: str = "") -> int:
        """Cria uma conta e devolve o identificador."""
        email = normalizar_email(email)
        username = (username or "").strip()
        if not email:
            raise ValueError("o email e obrigatorio")
        if not email_valido(email):
            raise ValueError("email invalido: %r" % email)
        if not username:
            raise ValueError("o nome de utilizador e obrigatorio")
        if not password:
            raise ValueError("a password e obrigatoria")
        if role not in ROLES:
            raise ValueError(
                "perfil desconhecido: %r (perfis: %s)" % (role, ", ".join(ROLES))
            )
        pergunta = (pergunta or "").strip()
        if pergunta and not normalizar_resposta(resposta):
            raise ValueError("a resposta a pergunta de seguranca e obrigatoria")

        try:
            with self.connection:
                cursor = self.connection.execute(
                    "INSERT INTO users (email, username, password_hash, role,"
                    " created_at, security_question, security_answer_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        email,
                        username,
                        hash_password(password),
                        role,
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        pergunta or None,
                        hash_password(normalizar_resposta(resposta))
                        if pergunta else None,
                    ),
                )
        except sqlite3.IntegrityError:
            raise ValueError(
                "ja existe uma conta com o email %r ou o nome %r" % (email, username)
            ) from None
        return int(cursor.lastrowid)

    def ensure_default_accounts(self) -> list[str]:
        """Cria as contas iniciais se ainda nao houver nenhuma conta.

        Devolve os enderecos criados (lista vazia se ja existiam contas).
        """
        if self.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return []
        criadas = []
        for email, username, password, role in DEFAULT_ACCOUNTS:
            self.create_user(email, username, password, role,
                             DEFAULT_QUESTION, DEFAULT_ANSWER)
            criadas.append(email)
        return criadas

    def _conta(self, email: str):
        return self.connection.execute(
            "SELECT id, email, username, password_hash, role, security_question,"
            " security_answer_hash FROM users WHERE email = ?",
            (normalizar_email(email),),
        ).fetchone()

    def authenticate(self, email: str, password: str) -> dict | None:
        """Valida as credenciais e devolve a conta, ou None se falharem."""
        linha = self._conta(email)
        if linha is None:
            return None
        if not verify_password(password or "", linha["password_hash"]):
            return None
        return {"id": linha["id"], "email": linha["email"],
                "username": linha["username"], "role": linha["role"]}

    def security_question(self, email: str) -> str | None:
        """Pergunta de seguranca da conta, ou None se nao houver conta."""
        linha = self._conta(email)
        if linha is None:
            return None
        return linha["security_question"]

    def reset_password(self, email: str, resposta: str, nova_password: str) -> bool:
        """Repoe a palavra-passe se a resposta de seguranca estiver certa.

        Devolve False quando a conta nao existe, nao tem pergunta definida ou
        a resposta nao confere — sem distinguir os casos para quem chama, para
        o ecra de entrada nao revelar que enderecos estao registados.
        """
        if not nova_password:
            raise ValueError("a nova palavra-passe e obrigatoria")
        linha = self._conta(email)
        if linha is None or not linha["security_answer_hash"]:
            return False
        if not verify_password(normalizar_resposta(resposta),
                               linha["security_answer_hash"]):
            return False
        with self.connection:
            self.connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(nova_password), linha["id"]),
            )
        return True

    def list_users(self) -> list[dict]:
        """Lista as contas existentes, sem as passwords."""
        return [
            dict(linha)
            for linha in self.connection.execute(
                "SELECT id, email, username, role, created_at, security_question"
                " FROM users ORDER BY email"
            )
        ]
