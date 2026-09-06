"""Varrimento de entradas apagadas (nao alocadas) em NTFS / FAT32 / exFAT.

Percorre o dispositivo com pytsk3: identifica as particoes, abre cada sistema de
ficheiros e recolhe as entradas cujo nome ou metadados estao marcados como nao
alocados, incluindo a lista de clusters/sectores ocupados para posterior
reconstrucao em src/recovery.py.
"""

from __future__ import annotations

import datetime

try:  # pytsk3 e opcional em ambiente de testes (substituido por mock)
    import pytsk3
except ImportError:  # pragma: no cover - depende do ambiente
    pytsk3 = None

MAX_DEPTH = 32
DEFAULT_SECTOR_SIZE = 512

# Numero maximo de registos de metadados (MFT no NTFS, entradas de directorio no
# FAT) percorridos por particao. Limita o tempo do varrimento em discos grandes.
MAX_REGISTOS = 500_000

CAMINHO_DOS_ORFAOS = "/$OrphanFiles"
SEM_CAMINHO = "(sem entrada de directorio)"

ORIGEM_DIRECTORIO = "directorio"
ORIGEM_REGISTO = "registo"

ERRO_SEM_PRIVILEGIOS = (
    "Acesso negado a %s. A leitura de disco em bruto exige privilegios de "
    "Administrador: reinicie a aplicacao como Administrador."
)
ERRO_INACESSIVEL = "Nao foi possivel abrir %s: %s"

# Constantes do Sleuth Kit. Os valores sao lidos do pytsk3 instalado; os que
# estao aqui sao os valores dos cabecalhos do TSK e servem de alternativa
# quando uma versao do pytsk3 nao exporta o nome (e o caso de TSK_FS_ATTR_RES).
CONSTANTES_TSK = {
    "TSK_VS_PART_FLAG_ALLOC": 1,
    "TSK_FS_NAME_FLAG_UNALLOC": 2,
    "TSK_FS_META_FLAG_UNALLOC": 2,
    "TSK_FS_META_TYPE_DIR": 2,
    "TSK_FS_ATTR_TYPE_DEFAULT": 1,
    "TSK_FS_ATTR_TYPE_NTFS_DATA": 128,
    "TSK_FS_ATTR_RES": 4,
    "TSK_FS_ATTR_RUN_FLAG_FILLER": 1,
    "TSK_FS_ATTR_RUN_FLAG_SPARSE": 2,
}


def _constante(nome: str) -> int:
    """Valor de uma constante do TSK, com alternativa documentada."""
    return int(getattr(_require_pytsk3(), nome, CONSTANTES_TSK[nome]))


def _abrir_imagem(device_path: str):
    """Abre o dispositivo ou imagem, traduzindo os erros do Sleuth Kit.

    Levanta ``PermissionError`` quando falta elevacao (o caso mais comum no
    Windows) e ``OSError`` quando o caminho nao existe ou nao e legivel.
    """
    tsk = _require_pytsk3()
    try:
        return tsk.Img_Info(device_path)
    except Exception as erro:
        mensagem = str(erro).lower()
        if "access denied" in mensagem or "permission" in mensagem:
            raise PermissionError(ERRO_SEM_PRIVILEGIOS % device_path) from erro
        raise OSError(ERRO_INACESSIVEL % (device_path, erro)) from erro


def _require_pytsk3():
    if pytsk3 is None:
        raise RuntimeError(
            "pytsk3 nao esta instalado; instalar com 'pip install -r requirements.txt'"
        )
    return pytsk3


def _decode_name(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _to_iso(timestamp) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            int(timestamp), datetime.timezone.utc
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _partitions(img) -> list[dict]:
    """Deslocamentos (em bytes) das particoes do dispositivo.

    Se nao houver tabela de particoes, assume-se que o dispositivo e ele proprio
    um sistema de ficheiros e devolve-se um unico deslocamento zero.
    """
    tsk = _require_pytsk3()
    try:
        volume = tsk.Volume_Info(img)
    except (OSError, IOError):
        return [{"offset": 0, "description": "sem tabela de particoes"}]

    sector_size = getattr(volume.info, "block_size", DEFAULT_SECTOR_SIZE) or DEFAULT_SECTOR_SIZE
    partitions = []
    for part in volume:
        if not part.flags & _constante("TSK_VS_PART_FLAG_ALLOC"):
            continue
        if part.len <= 2:  # entradas meta da tabela de particoes
            continue
        partitions.append(
            {
                "offset": int(part.start) * sector_size,
                "description": _decode_name(part.desc),
            }
        )
    if not partitions:
        return [{"offset": 0, "description": "sem particoes alocadas"}]
    return partitions


def _is_deleted(entry) -> bool:
    name = entry.info.name
    if name is not None and name.flags & _constante("TSK_FS_NAME_FLAG_UNALLOC"):
        return True
    meta = entry.info.meta
    if meta is not None and meta.flags & _constante("TSK_FS_META_FLAG_UNALLOC"):
        return True
    return False


def _is_directory(entry) -> bool:
    meta = entry.info.meta
    return meta is not None and meta.type == _constante("TSK_FS_META_TYPE_DIR")


def _data_runs(entry) -> tuple[list[dict], bool]:
    """Runs de clusters do fluxo de dados principal e indicador de residencia."""
    data_types = (
        _constante("TSK_FS_ATTR_TYPE_DEFAULT"),
        _constante("TSK_FS_ATTR_TYPE_NTFS_DATA"),
    )
    residente = _constante("TSK_FS_ATTR_RES")
    ignored_run_flags = (
        _constante("TSK_FS_ATTR_RUN_FLAG_FILLER")
        | _constante("TSK_FS_ATTR_RUN_FLAG_SPARSE")
    )
    runs: list[dict] = []
    resident = False
    try:
        attributes = list(entry)
    except OSError:  # atributos ilegiveis: entrada sem runs, nao e um erro fatal
        return runs, resident

    for attribute in attributes:
        info = attribute.info
        if info.type not in data_types:
            continue
        if _decode_name(info.name):  # fluxos alternativos (ADS) sao ignorados
            continue
        if info.flags & residente:
            resident = True
            continue
        try:
            attribute_runs = list(attribute)
        except OSError:
            continue
        for run in attribute_runs:
            if run.len == 0 or run.flags & ignored_run_flags:
                continue
            runs.append({"block": int(run.addr), "count": int(run.len)})
    return runs, resident


def _nome_da_entrada(entry) -> str:
    """Nome da entrada; vazio quando o ficheiro foi aberto pelo inode."""
    nome = entry.info.name
    if nome is None:
        return ""
    return _decode_name(nome.name)


def _describe(entry, path: str, partition: dict, fs,
              origem: str = ORIGEM_DIRECTORIO) -> dict:
    meta = entry.info.meta
    runs, resident = _data_runs(entry)
    block_size = int(fs.info.block_size)
    sector_size = int(getattr(fs.info, "dev_bsize", DEFAULT_SECTOR_SIZE) or DEFAULT_SECTOR_SIZE)
    sectors_per_block = max(1, block_size // sector_size)
    mtime = int(meta.mtime) if meta is not None and meta.mtime else None
    nome = _nome_da_entrada(entry)
    if not nome and meta is not None:
        nome = "registo_%d" % int(meta.addr)  # sem nome recuperavel
    return {
        "name": nome,
        "path": path or SEM_CAMINHO,
        "origem": origem,
        "size": int(meta.size) if meta is not None else 0,
        "inode": int(meta.addr) if meta is not None else None,
        "fs_type": str(fs.info.ftype),
        "partition_offset": int(partition["offset"]),
        "partition_description": partition["description"],
        "block_size": block_size,
        "sector_size": sector_size,
        "runs": runs,
        "sectors": [
            {
                "sector": run["block"] * sectors_per_block,
                "count": run["count"] * sectors_per_block,
            }
            for run in runs
        ],
        "resident": resident,
        "allocated": False,
        "mtime": mtime,
        "mtime_iso": _to_iso(mtime),
        "crtime_iso": _to_iso(meta.crtime if meta is not None else None),
    }


def _orfaos(fs, partition, entries, inodes) -> None:
    """Ficheiros que o Sleuth Kit encontra sem entrada de directorio.

    O TSK recupera o nome a partir do registo de metadados e junta-os na
    directoria virtual ``$OrphanFiles``.
    """
    try:
        directorio = fs.open_dir(path=CAMINHO_DOS_ORFAOS)
    except (OSError, IOError):
        return
    for entry in directorio:
        meta = entry.info.meta
        if meta is None or int(meta.addr) in inodes:
            continue
        if not _is_deleted(entry) or _is_directory(entry):
            continue
        try:
            entries.append(
                _describe(entry, CAMINHO_DOS_ORFAOS + "/" + _nome_da_entrada(entry),
                          partition, fs, ORIGEM_DIRECTORIO)
            )
        except OSError:
            continue
        inodes.add(int(meta.addr))


def _registos_nao_alocados(fs, partition, entries, inodes) -> int:
    """Percorre os registos de metadados nao alocados (a MFT, no NTFS).

    E aqui que aparecem os ficheiros apagados em NTFS: ao eliminar, a entrada
    sai do indice da directoria, mas o registo permanece marcado como nao
    alocado ate ser reutilizado. Devolve o numero de registos examinados.
    """
    nao_alocado = _constante("TSK_FS_META_FLAG_UNALLOC")
    tipo_directoria = _constante("TSK_FS_META_TYPE_DIR")
    primeiro = int(getattr(fs.info, "first_inum", 0) or 0)
    ultimo = int(getattr(fs.info, "last_inum", 0) or 0)
    ultimo = min(ultimo, primeiro + MAX_REGISTOS)

    examinados = 0
    for inode in range(primeiro, ultimo + 1):
        examinados += 1
        if inode in inodes:
            continue
        try:
            ficheiro = fs.open_meta(inode=inode)
        except (OSError, IOError, ValueError):
            continue  # registo por usar ou ilegivel
        meta = ficheiro.info.meta
        if meta is None or not meta.flags & nao_alocado:
            continue
        if meta.type == tipo_directoria or not meta.size:
            continue
        try:
            entries.append(_describe(ficheiro, "", partition, fs, ORIGEM_REGISTO))
        except OSError:
            continue
        inodes.add(inode)
    return examinados


def _walk(fs, directory, parent_path, partition, entries, visited, depth,
          inodes=None) -> None:
    inodes = inodes if inodes is not None else set()
    for entry in directory:
        if entry.info.name is None:
            continue
        name = _decode_name(entry.info.name.name)
        if name in ("", ".", ".."):
            continue
        path = parent_path.rstrip("/") + "/" + name

        if _is_deleted(entry):
            try:
                entries.append(_describe(entry, path, partition, fs))
            except OSError:  # entrada corrompida: continua para a seguinte
                continue
            if entry.info.meta is not None:
                inodes.add(int(entry.info.meta.addr))

        if depth < MAX_DEPTH and _is_directory(entry):
            inode = entry.info.meta.addr
            if inode in visited:
                continue
            visited.add(inode)
            try:
                sub_directory = entry.as_directory()
            except OSError:  # directoria apagada e ja ilegivel
                continue
            _walk(fs, sub_directory, path, partition, entries, visited, depth + 1,
                  inodes)


def scan_deleted_entries(device_path: str,
                         diagnostico: dict | None = None) -> list[dict]:
    """Lista as entradas apagadas (nao alocadas) do dispositivo indicado.

    Combina tres fontes, por esta ordem: as entradas ainda presentes nas
    directorias (tipico do FAT), os ficheiros orfaos que o Sleuth Kit
    reconstroi, e o varrimento dos registos de metadados nao alocados (a MFT,
    onde estao os ficheiros apagados em NTFS). As repeticoes sao eliminadas
    pelo numero de inode.

    Cada entrada e um dicionario com nome, caminho original, tamanho, inode,
    runs de clusters e sectores absolutos da particao, e timestamps quando
    disponiveis. Passando um dicionario em ``diagnostico``, este fica com o
    numero de particoes vistas, de sistemas de ficheiros abertos e de registos
    examinados — util para distinguir "nao ha nada apagado" de "nao foi
    possivel ler o sistema de ficheiros".
    """
    tsk = _require_pytsk3()
    image = _abrir_imagem(device_path)
    entries: list[dict] = []
    resumo = {
        "particoes": 0,
        "sistemas_de_ficheiros": 0,
        "tipos": [],
        "registos_examinados": 0,
    }

    for partition in _partitions(image):
        resumo["particoes"] += 1
        try:
            fs = tsk.FS_Info(image, offset=partition["offset"])
        except (OSError, IOError):
            continue  # particao sem sistema de ficheiros reconhecido
        resumo["sistemas_de_ficheiros"] += 1
        resumo["tipos"].append(str(fs.info.ftype))

        inodes: set[int] = set()
        try:
            root = fs.open_dir(path="/")
        except (OSError, IOError):
            root = None
        if root is not None:
            _walk(fs, root, "", partition, entries, set(), 0, inodes)
        _orfaos(fs, partition, entries, inodes)
        resumo["registos_examinados"] += _registos_nao_alocados(
            fs, partition, entries, inodes
        )

    if diagnostico is not None:
        diagnostico.update(resumo)
    return entries
