"""Contas, perfis de acesso e autenticacao dos peritos.

As contas ficam numa tabela ``users`` da mesma base de dados SQLite da auditoria.
As passwords nunca sao guardadas em claro: usa-se PBKDF2-HMAC-SHA256 com salt
aleatorio por conta.

Perfis:
- administrador: escanear, recuperar, gerar relatorio e gerir contas;
- operador: apenas o fluxo de recuperacao (escanear e recuperar).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import secrets
import sqlite3

DEFAULT_DB_PATH = "frda_audit.db"  # partilha o ficheiro com o registo de auditoria

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

# Contas criadas no primeiro arranque, se a tabela estiver vazia.
DEFAULT_ACCOUNTS = (
    ("admin", "admin123", ROLE_ADMIN),
    ("operador", "operador123", ROLE_OPERATOR),
)

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


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


class AuthStore:
    """Repositorio de contas de acesso."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_TABLE)

    def __enter__(self) -> "AuthStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def create_user(self, username: str, password: str, role: str) -> int:
        """Cria uma conta e devolve o identificador."""
        username = (username or "").strip()
        if not username:
            raise ValueError("o nome de utilizador e obrigatorio")
        if not password:
            raise ValueError("a password e obrigatoria")
        if role not in ROLES:
            raise ValueError(
                "perfil desconhecido: %r (perfis: %s)" % (role, ", ".join(ROLES))
            )
        try:
            with self.connection:
                cursor = self.connection.execute(
                    "INSERT INTO users (username, password_hash, role, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        username,
                        hash_password(password),
                        role,
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            raise ValueError("ja existe uma conta com o nome %r" % username) from None
        return int(cursor.lastrowid)

    def ensure_default_accounts(self) -> list[str]:
        """Cria as contas iniciais se ainda nao houver nenhuma conta.

        Devolve os nomes criados (lista vazia se ja existiam contas).
        """
        if self.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return []
        criadas = []
        for username, password, role in DEFAULT_ACCOUNTS:
            self.create_user(username, password, role)
            criadas.append(username)
        return criadas

    def authenticate(self, username: str, password: str) -> dict | None:
        """Valida as credenciais e devolve a conta, ou None se falharem."""
        linha = self.connection.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
        if linha is None:
            return None
        if not verify_password(password or "", linha["password_hash"]):
            return None
        return {"id": linha["id"], "username": linha["username"], "role": linha["role"]}

    def list_users(self) -> list[dict]:
        """Lista as contas existentes, sem as passwords."""
        return [
            dict(linha)
            for linha in self.connection.execute(
                "SELECT id, username, role, created_at FROM users ORDER BY username"
            )
        ]
