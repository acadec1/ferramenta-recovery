"""Registo de auditoria / cadeia de custodia em SQLite.

Cada accao relevante (varrimento, recuperacao, carving, verificacao de
integridade, exportacao de relatorio) fica registada com data/hora, dispositivo,
ficheiro, hash SHA-256 e utilizador do sistema operativo.
"""

from __future__ import annotations

import datetime
import getpass
import sqlite3

DEFAULT_DB_PATH = "frda_audit.db"

# Accoes registadas, partilhadas pela GUI e pelo relatorio.
ACTION_SCAN = "scan"
ACTION_RECOVER = "recover"
ACTION_VERIFY_OK = "verify_ok"
ACTION_VERIFY_FAILED = "verify_falhou"
ACTION_REPORT = "report"

FIELDS = (
    "timestamp",
    "device_path",
    "action",
    "file_path",
    "file_hash",
    "os_user",
    "app_user",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    device_path TEXT,
    action TEXT NOT NULL,
    file_path TEXT,
    file_hash TEXT,
    os_user TEXT,
    app_user TEXT
)
"""

CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_events_device ON events (device_path)"


class AuditLog:
    """Livro de registos da cadeia de custodia."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_TABLE)
            self.connection.execute(CREATE_INDEX)
        self._migrar_colunas_em_falta()

    def _migrar_colunas_em_falta(self) -> None:
        """Acrescenta colunas novas a bases de dados criadas por versoes anteriores."""
        existentes = {
            linha["name"]
            for linha in self.connection.execute("PRAGMA table_info(events)")
        }
        with self.connection:
            for campo in FIELDS:
                if campo not in existentes:
                    self.connection.execute(
                        "ALTER TABLE events ADD COLUMN %s TEXT" % campo
                    )

    def __enter__(self) -> "AuditLog":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def log_event(self, **kwargs) -> int:
        """Regista um evento e devolve o respectivo identificador.

        Campos aceites: ``timestamp`` (por omissao, o instante actual em UTC),
        ``device_path``, ``action`` (obrigatorio), ``file_path``, ``file_hash``,
        ``os_user`` (por omissao, o utilizador do sistema operativo) e
        ``app_user`` (o perito autenticado na aplicacao).
        """
        desconhecidos = set(kwargs) - set(FIELDS)
        if desconhecidos:
            raise ValueError(
                "campos desconhecidos no evento: %s" % ", ".join(sorted(desconhecidos))
            )
        if not kwargs.get("action"):
            raise ValueError("o campo 'action' e obrigatorio")

        event = {field: kwargs.get(field) for field in FIELDS}
        if not event["timestamp"]:
            event["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not event["os_user"]:
            event["os_user"] = self._current_user()

        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO events (%s) VALUES (%s)"
                % (", ".join(FIELDS), ", ".join("?" * len(FIELDS))),
                [event[field] for field in FIELDS],
            )
        return int(cursor.lastrowid)

    def get_events(self, device_path: str | None = None) -> list[dict]:
        """Devolve os eventos por ordem cronologica de registo."""
        query = "SELECT id, %s FROM events" % ", ".join(FIELDS)
        parameters: list = []
        if device_path is not None:
            query += " WHERE device_path = ?"
            parameters.append(device_path)
        query += " ORDER BY id"
        return [dict(row) for row in self.connection.execute(query, parameters)]

    @staticmethod
    def _current_user() -> str:
        try:
            return getpass.getuser()
        except Exception:  # pragma: no cover - depende do ambiente
            return "desconhecido"
