"""Historico das operacoes de recuperacao, em SQLite e em JSON.

Guarda, por operacao, o dispositivo analisado, o metodo usado, os totais e a
lista de ficheiros processados com o respectivo estado e resumo SHA-256. Serve
dois fins: manter o registo do que ja foi feito e alimentar o relatorio em PDF.

A base de dados SQLite e o armazenamento de trabalho. A cada operacao gravada
ou actualizada, o historico completo e tambem escrito num ficheiro JSON, que
pode ser lido e arquivado sem a ferramenta.

Ambos os ficheiros ficam na pasta da aplicacao e nao na pasta de trabalho do
processo: assim o historico e o mesmo quer a ferramenta seja aberta a partir
do explorador, da linha de comandos ou de um processo elevado pelo UAC.

Os ficheiros recuperados nao sao guardados no historico: ficam na pasta de
destino escolhida pelo utilizador.
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import sqlite3

# Raiz da aplicacao (a pasta que contem "src"), para o historico nao depender
# da pasta de trabalho do processo.
PASTA_DA_APLICACAO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DB_PATH = os.path.join(PASTA_DA_APLICACAO, "frda_historico.db")
DEFAULT_JSON_PATH = os.path.join(PASTA_DA_APLICACAO, "frda_historico.json")

# Bases de dados em memoria nao tem ficheiro JSON associado.
BASE_EM_MEMORIA = ":memory:"
VERSAO_DO_JSON = 1

# Metodos de recuperacao, partilhados pela interface e pelos relatorios.
METODO_METADADOS = "metadados"
METODO_CARVING = "carving"
METODOS = (METODO_METADADOS, METODO_CARVING)

NOMES_DOS_METODOS = {
    METODO_METADADOS: "Recuperacao baseada em metadados",
    METODO_CARVING: "Recuperacao por assinaturas (File Carving)",
}

# Nome curto, para as colunas das tabelas, onde o nome completo nao cabe.
NOMES_CURTOS_DOS_METODOS = {
    METODO_METADADOS: "Metadados",
    METODO_CARVING: "Carving",
}

# Estado de cada ficheiro processado numa operacao.
ESTADO_RECUPERADO = "recuperado"
ESTADO_FALHADO = "nao recuperado"

# Estado da operacao. Uma analise fica registada mal termina, mesmo que o
# utilizador nao recupere nada: e isso que faz o historico reflectir tudo o
# que foi feito na ferramenta.
OPERACAO_ANALISADA = "analisada"
OPERACAO_RECUPERADA = "recuperada"
OPERACAO_INTERROMPIDA = "interrompida"
OPERACAO_FALHADA = "falhada"

NOMES_DOS_ESTADOS = {
    OPERACAO_ANALISADA: "So analise",
    OPERACAO_RECUPERADA: "Recuperacao",
    OPERACAO_INTERROMPIDA: "Interrompida",
    OPERACAO_FALHADA: "Falhada",
}

CAMPOS_DA_OPERACAO = (
    "inicio",
    "fim",
    "device_path",
    "device_type",
    "device_size",
    "filesystem",
    "metodo",
    "estado",
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
    estado TEXT,
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

# Distingue "nao foi indicado" de "indicado como None" (JSON desligado).
_POR_OMISSAO = object()


class Historico:
    """Historico das operacoes de recuperacao."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH, json_path=_POR_OMISSAO):
        self.db_path = db_path
        self.json_path: str | None = self._escolher_json(db_path, json_path)
        self.erro_do_json: str | None = None
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute(CREATE_OPERATIONS)
            self.connection.execute(CREATE_OPERATION_FILES)
        # antes do indice: uma base antiga pode nao ter a coluna que o indice usa
        self._acrescentar_colunas_em_falta()
        with self.connection:
            self.connection.execute(CREATE_INDEX)

    @staticmethod
    def _escolher_json(db_path: str, json_path) -> str | None:
        """Ficheiro JSON a usar: ao lado da base de dados, salvo indicacao."""
        if json_path is not _POR_OMISSAO:
            return json_path
        if db_path == BASE_EM_MEMORIA:
            return None
        if db_path == DEFAULT_DB_PATH:
            return DEFAULT_JSON_PATH
        raiz = os.path.splitext(db_path)[0]
        return raiz + ".json"

    def _acrescentar_colunas_em_falta(self) -> None:
        """Actualiza bases de dados criadas por versoes anteriores.

        Sem isto, um historico ja existente ficaria ilegivel depois de se
        acrescentar um campo novo a tabela das operacoes.
        """
        existentes = {
            linha["name"]
            for linha in self.connection.execute("PRAGMA table_info(operacoes)")
        }
        em_falta = [campo for campo in CAMPOS_DA_OPERACAO if campo not in existentes]
        if not em_falta:
            return
        with self.connection:
            for campo in em_falta:
                self.connection.execute(
                    "ALTER TABLE operacoes ADD COLUMN %s TEXT" % campo
                )

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
        operacao["estado"] = operacao["estado"] or (
            OPERACAO_RECUPERADA if ficheiros else OPERACAO_ANALISADA
        )
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
        self._guardar_json()
        return operacao_id

    def update_operation(self, operacao_id: int, ficheiros: list[dict] | None = None,
                         **campos) -> None:
        """Completa uma operacao ja registada.

        Serve o caso normal da ferramenta: a analise fica guardada assim que
        termina e, se o utilizador recuperar ficheiros a seguir, e a mesma
        operacao que passa a ter destino, totais e lista de ficheiros — em vez
        de aparecerem duas entradas no historico para o mesmo trabalho.

        Os ficheiros indicados substituem os que estiverem guardados.
        """
        desconhecidos = set(campos) - set(CAMPOS_DA_OPERACAO)
        if desconhecidos:
            raise ValueError(
                "campos desconhecidos na operacao: %s" % ", ".join(sorted(desconhecidos))
            )
        if not self.get_operations(operacao_id):
            raise ValueError("operacao inexistente: %r" % operacao_id)
        if "metodo" in campos and campos["metodo"] not in METODOS:
            raise ValueError("metodo desconhecido: %r" % campos["metodo"])

        with self.connection:
            if campos:
                self.connection.execute(
                    "UPDATE operacoes SET %s WHERE id = ?"
                    % ", ".join("%s = ?" % campo for campo in campos),
                    list(campos.values()) + [operacao_id],
                )
            if ficheiros is not None:
                self.connection.execute(
                    "DELETE FROM operacao_ficheiros WHERE operacao_id = ?",
                    (operacao_id,),
                )
                for ficheiro in ficheiros:
                    valores = {campo: ficheiro.get(campo) for campo in CAMPOS_DO_FICHEIRO}
                    valores["operacao_id"] = operacao_id
                    self.connection.execute(
                        "INSERT INTO operacao_ficheiros (%s) VALUES (%s)"
                        % (", ".join(CAMPOS_DO_FICHEIRO),
                           ", ".join("?" * len(CAMPOS_DO_FICHEIRO))),
                        [valores[campo] for campo in CAMPOS_DO_FICHEIRO],
                    )
        self._guardar_json()

    # ------------------------------------------------------------------ JSON

    def como_dicionario(self) -> dict:
        """Historico completo: cada operacao com os seus ficheiros."""
        operacoes = []
        for operacao in self.get_operations():
            registo = dict(operacao)
            registo["metodo_nome"] = NOMES_DOS_METODOS.get(operacao.get("metodo"))
            registo["estado_nome"] = NOMES_DOS_ESTADOS.get(operacao.get("estado"))
            registo["ficheiros"] = self.get_operation_files(int(operacao["id"]))
            operacoes.append(registo)
        return {
            "ferramenta": "FRDA",
            "versao": VERSAO_DO_JSON,
            "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_de_operacoes": len(operacoes),
            "operacoes": operacoes,
        }

    def exportar_json(self, caminho: str | None = None) -> str | None:
        """Escreve o historico completo em JSON e devolve o caminho usado.

        Escreve primeiro num ficheiro temporario e so depois o move para o
        lugar: se a ferramenta for fechada a meio da escrita, o historico
        anterior nao fica truncado. Devolve None se nao houver ficheiro JSON.
        """
        destino = caminho or self.json_path
        if not destino:
            return None
        temporario = destino + ".tmp"
        with open(temporario, "w", encoding="utf-8") as ficheiro:
            json.dump(self.como_dicionario(), ficheiro,
                      ensure_ascii=False, indent=2)
        os.replace(temporario, destino)
        return destino

    def _guardar_json(self) -> None:
        """Escreve o JSON sem deixar perder a operacao ja gravada em SQLite.

        Se a pasta da aplicacao nao for gravavel, a operacao continua
        registada na base de dados e o erro fica guardado para o painel do
        historico o poder mostrar.
        """
        try:
            self.exportar_json()
        except OSError as erro:
            self.erro_do_json = str(erro)
            return
        self.erro_do_json = None

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
