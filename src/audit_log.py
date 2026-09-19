"""Registo de auditoria e historico de operacoes, em SQLite.

Guarda duas coisas complementares no mesmo ficheiro:

- ``events``: a cadeia de custodia, accao a accao (varrimento, recuperacao,
  carving, verificacao de integridade, relatorio), com data/hora, dispositivo,
  ficheiro, hash SHA-256, utilizador do sistema operativo e perito;
- ``operacoes`` e ``operacao_ficheiros``: o historico de cada operacao completa
  de recuperacao, com os totais e a lista de ficheiros processados, que serve
  de base ao relatorio PDF.

Os ficheiros recuperados nao sao guardados na base de dados: ficam na pasta de
destino escolhida pelo utilizador.
"""

from __future__ import annotations

import datetime
import getpass
import sqlite3

DEFAULT_DB_PATH = "frda_audit.db"

# Accoes registadas, partilhadas pela GUI e pelo relatorio.
ACTION_SCAN = "scan"
ACTION_RECOVER = "recover"
ACTION_CARVING = "carving"
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

# Metodos de recuperacao, partilhados pela interface e pelos relatorios.
METODO_METADADOS = "metadados"
METODO_CARVING = "carving"
METODOS = (METODO_METADADOS, METODO_CARVING)

NOMES_DOS_METODOS = {
    METODO_METADADOS: "Recuperacao baseada em metadados",
    METODO_CARVING: "Recuperacao por assinaturas (File Carving)",
}

# Estado de cada ficheiro processado numa operacao.
ESTADO_RECUPERADO = "recuperado"
ESTADO_FALHADO = "nao recuperado"

CAMPOS_DA_OPERACAO = (
    "inicio",
    "fim",
    "device_path",
    "device_type",
    "device_size",
    "filesystem",
    "metodo",
    "encontrados",
    "seleccionados",
    "recuperados",
    "nao_recuperados",
    "pasta_destino",
    "observacoes",
    "os_user",
    "app_user",
)

CAMPOS_DO_FICHEIRO = (
    "operacao_id",
    "nome",
    "tipo",
    "tamanho",
    "estado",
    "caminho",
    "file_hash",
    "erro",
)

CREATE_OPERATIONS = """
CREATE TABLE IF NOT EXISTS operacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL,
    fim TEXT,
    device_path TEXT,
    device_type TEXT,
    device_size INTEGER,
    filesystem TEXT,
    metodo TEXT NOT NULL,
    encontrados INTEGER DEFAULT 0,
    seleccionados INTEGER DEFAULT 0,
    recuperados INTEGER DEFAULT 0,
    nao_recuperados INTEGER DEFAULT 0,
    pasta_destino TEXT,
    observacoes TEXT,
    os_user TEXT,
    app_user TEXT
)
"""

CREATE_OPERATION_FILES = """
CREATE TABLE IF NOT EXISTS operacao_ficheiros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    nome TEXT,
    tipo TEXT,
    tamanho INTEGER,
    estado TEXT,
    caminho TEXT,
    file_hash TEXT,
    erro TEXT,
    FOREIGN KEY (operacao_id) REFERENCES operacoes (id)
)
"""


class AuditLog:
    """Livro de registos da cadeia de custodia."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_TABLE)
            self.connection.execute(CREATE_INDEX)
            self.connection.execute(CREATE_OPERATIONS)
            self.connection.execute(CREATE_OPERATION_FILES)
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

    # ------------------------------------------------- historico de operacoes

    def log_operation(self, ficheiros: list[dict] | None = None, **campos) -> int:
        """Guarda uma operacao completa e os ficheiros processados.

        Devolve o identificador da operacao. Os totais que nao forem indicados
        sao calculados a partir da lista de ficheiros.
        """
        desconhecidos = set(campos) - set(CAMPOS_DA_OPERACAO)
        if desconhecidos:
            raise ValueError(
                "campos desconhecidos na operacao: %s" % ", ".join(sorted(desconhecidos))
            )
        if campos.get("metodo") not in METODOS:
            raise ValueError(
                "metodo desconhecido: %r (metodos: %s)"
                % (campos.get("metodo"), ", ".join(METODOS))
            )

        ficheiros = list(ficheiros or [])
        operacao = {campo: campos.get(campo) for campo in CAMPOS_DA_OPERACAO}
        agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        operacao["inicio"] = operacao["inicio"] or agora
        operacao["fim"] = operacao["fim"] or agora
        operacao["os_user"] = operacao["os_user"] or self._current_user()
        if operacao["recuperados"] is None:
            operacao["recuperados"] = sum(
                1 for f in ficheiros if f.get("estado") == ESTADO_RECUPERADO
            )
        if operacao["nao_recuperados"] is None:
            operacao["nao_recuperados"] = sum(
                1 for f in ficheiros if f.get("estado") != ESTADO_RECUPERADO
            )
        if operacao["seleccionados"] is None:
            operacao["seleccionados"] = len(ficheiros)

        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO operacoes (%s) VALUES (%s)"
                % (", ".join(CAMPOS_DA_OPERACAO),
                   ", ".join("?" * len(CAMPOS_DA_OPERACAO))),
                [operacao[campo] for campo in CAMPOS_DA_OPERACAO],
            )
            operacao_id = int(cursor.lastrowid)
            for ficheiro in ficheiros:
                valores = {campo: ficheiro.get(campo) for campo in CAMPOS_DO_FICHEIRO}
                valores["operacao_id"] = operacao_id
                self.connection.execute(
                    "INSERT INTO operacao_ficheiros (%s) VALUES (%s)"
                    % (", ".join(CAMPOS_DO_FICHEIRO),
                       ", ".join("?" * len(CAMPOS_DO_FICHEIRO))),
                    [valores[campo] for campo in CAMPOS_DO_FICHEIRO],
                )
        return operacao_id

    def get_operations(self, operacao_id: int | None = None) -> list[dict]:
        """Operacoes registadas, da mais recente para a mais antiga."""
        consulta = "SELECT id, %s FROM operacoes" % ", ".join(CAMPOS_DA_OPERACAO)
        parametros: list = []
        if operacao_id is not None:
            consulta += " WHERE id = ?"
            parametros.append(operacao_id)
        consulta += " ORDER BY id DESC"
        return [dict(linha) for linha in self.connection.execute(consulta, parametros)]

    def get_operation_files(self, operacao_id: int) -> list[dict]:
        """Ficheiros processados numa operacao, pela ordem em que foram tratados."""
        return [
            dict(linha)
            for linha in self.connection.execute(
                "SELECT id, %s FROM operacao_ficheiros WHERE operacao_id = ? ORDER BY id"
                % ", ".join(CAMPOS_DO_FICHEIRO),
                (operacao_id,),
            )
        ]

    @staticmethod
    def _current_user() -> str:
        try:
            return getpass.getuser()
        except Exception:  # pragma: no cover - depende do ambiente
            return "desconhecido"
