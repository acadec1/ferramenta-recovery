"""Historico das operacoes de recuperacao, em SQLite.

Guarda, por operacao, o dispositivo analisado, o metodo usado, os totais e a
lista de ficheiros processados com o respectivo estado e resumo SHA-256. Serve
dois fins: manter o registo do que ja foi feito e alimentar o relatorio em PDF.

Os ficheiros recuperados nao sao guardados na base de dados: ficam na pasta de
destino escolhida pelo utilizador.
"""

from __future__ import annotations

import datetime
import getpass
import sqlite3

DEFAULT_DB_PATH = "frda_historico.db"

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


CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_operacoes_dispositivo ON operacoes (device_path)"


class Historico:
    """Historico das operacoes de recuperacao."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_OPERATIONS)
            self.connection.execute(CREATE_OPERATION_FILES)
            self.connection.execute(CREATE_INDEX)

    def __enter__(self) -> "Historico":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

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
