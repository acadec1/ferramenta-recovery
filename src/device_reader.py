r"""Enumeracao de dispositivos fisicos no Windows via \\.\PhysicalDriveN.

Usa ctypes sobre kernel32 (CreateFileW + DeviceIoControl) para obter o tamanho
de cada disco fisico. A leitura bruta exige privilegios de Administrador, mas a
enumeracao funciona sem elevacao: IOCTL_DISK_GET_LENGTH_INFO precisa de acesso
de leitura, enquanto IOCTL_DISK_GET_DRIVE_GEOMETRY_EX responde com acesso zero
e serve de alternativa.
"""

from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import sys

DEVICE_PATH_TEMPLATE = r"\\.\PhysicalDrive{}"

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
NUMERO_DE_DISCO_INVALIDO = 0xFFFFFFFF

TIPOS_DE_UNIDADE = {
    0: "Desconhecido",
    1: "Inexistente",
    2: "Removivel",
    3: "Fixo",
    4: "Rede",
    5: "CD-ROM",
    6: "Disco RAM",
}

SHELL_EXECUTE_MINIMO = 32  # ShellExecuteW devolve <= 32 em caso de erro
SW_SHOWNORMAL = 1

_kernel32 = None
_shell32 = None


def _get_shell32():
    """Devolve (e memoriza) o handle para shell32. Ponto de patch nos testes."""
    global _shell32
    if _shell32 is None:
        _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    return _shell32


def _get_kernel32():
    """Devolve (e memoriza) o handle para kernel32. Ponto de patch nos testes."""
    global _kernel32
    if _kernel32 is None:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _kernel32.CreateFileW.restype = ctypes.c_void_p
    return _kernel32


def physical_drive_path(index: int) -> str:
    """Caminho do dispositivo fisico com o numero indicado."""
    return DEVICE_PATH_TEMPLATE.format(index)


def _open_device(path: str, desired_access: int = 0):
    """Abre um dispositivo em modo partilhado. Devolve o handle ou None."""
    handle = _get_kernel32().CreateFileW(
        path,
        desired_access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle is None or handle == INVALID_HANDLE_VALUE:
        return None
    return handle


def _close_device(handle) -> None:
    _get_kernel32().CloseHandle(handle)


def _device_io_control(handle, code: int, out_size: int) -> bytes | None:
    """Executa um DeviceIoControl sem buffer de entrada. Devolve os bytes lidos."""
    buffer = ctypes.create_string_buffer(out_size)
    returned = ctypes.c_ulong(0)
    ok = _get_kernel32().DeviceIoControl(
        ctypes.c_void_p(handle),
        code,
        None,
        0,
        buffer,
        ctypes.sizeof(buffer),
        ctypes.byref(returned),
        None,
    )
    if not ok:
        return None
    return buffer.raw


def _size_from_length_info(handle) -> int | None:
    """GET_LENGTH_INFORMATION: LARGE_INTEGER Length."""
    raw = _device_io_control(handle, IOCTL_DISK_GET_LENGTH_INFO, 8)
    if raw is None:
        return None
    return struct.unpack("<q", raw[:8])[0]


def _size_from_geometry(handle) -> int | None:
    """DISK_GEOMETRY_EX: DISK_GEOMETRY (24 bytes) + LARGE_INTEGER DiskSize."""
    raw = _device_io_control(handle, IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, 32)
    if raw is None or len(raw) < 32:
        return None
    return struct.unpack("<q", raw[24:32])[0]


def get_drive_size(index: int) -> int | None:
    """Tamanho em bytes do disco fisico, ou None se nao existir/nao for legivel."""
    path = physical_drive_path(index)
    handle = _open_device(path, GENERIC_READ)
    if handle is None:
        handle = _open_device(path)
    if handle is None:
        return None
    try:
        size = _size_from_length_info(handle)
        if size is None:
            size = _size_from_geometry(handle)
        return size
    finally:
        _close_device(handle)


def list_physical_drives(max_index: int = 32) -> list[dict]:
    r"""Lista os discos fisicos acessiveis.

    Devolve uma lista de dicionarios com as chaves ``index`` (numero do drive),
    ``path`` (\\.\PhysicalDriveN) e ``size_bytes`` (tamanho em bytes).
    """
    drives: list[dict] = []
    for index in range(max_index):
        size = get_drive_size(index)
        if size is None:
            continue
        drives.append(
            {
                "index": index,
                "path": physical_drive_path(index),
                "size_bytes": size,
            }
        )
    return drives


def _informacao_do_volume(raiz: str) -> tuple[str, str]:
    """Etiqueta e sistema de ficheiros de um volume (GetVolumeInformationW)."""
    nome = ctypes.create_unicode_buffer(261)
    sistema = ctypes.create_unicode_buffer(261)
    ok = _get_kernel32().GetVolumeInformationW(
        raiz,
        nome,
        260,
        ctypes.pointer(ctypes.c_ulong()),
        ctypes.pointer(ctypes.c_ulong()),
        ctypes.pointer(ctypes.c_ulong()),
        sistema,
        260,
    )
    if not ok:
        return "", ""
    return nome.value, sistema.value


def _capacidade_do_volume(raiz: str) -> tuple[int | None, int | None]:
    """Capacidade e espaco livre de um volume (GetDiskFreeSpaceExW)."""
    disponivel = ctypes.c_ulonglong(0)
    total = ctypes.c_ulonglong(0)
    livre = ctypes.c_ulonglong(0)
    ok = _get_kernel32().GetDiskFreeSpaceExW(
        raiz,
        ctypes.pointer(disponivel),
        ctypes.pointer(total),
        ctypes.pointer(livre),
    )
    if not ok:
        return None, None
    return total.value, livre.value


def _disco_do_volume(letra: str) -> int | None:
    """Numero do disco fisico que suporta o volume, se for um so."""
    handle = _open_device(r"\\.\%s:" % letra)
    if handle is None:
        return None
    try:
        raw = _device_io_control(handle, IOCTL_STORAGE_GET_DEVICE_NUMBER, 12)
        if raw is None or len(raw) < 12:
            return None
        _tipo, numero, _particao = struct.unpack("<III", raw[:12])
        if numero == NUMERO_DE_DISCO_INVALIDO:
            return None  # volume distribuido por varios discos
        return numero
    finally:
        _close_device(handle)


def list_logical_volumes() -> list[dict]:
    r"""Lista os volumes logicos (letras de unidade) montados no sistema.

    Cada volume traz ``letter``, ``root`` (C:\), ``path`` (\\.\C:), ``label``,
    ``filesystem``, ``size_bytes``, ``free_bytes``, ``drive_type`` e
    ``disk_index`` (numero do disco fisico correspondente, ou None).
    """
    kernel32 = _get_kernel32()
    mascara = kernel32.GetLogicalDrives()
    volumes: list[dict] = []
    for posicao in range(26):
        if not mascara & (1 << posicao):
            continue
        letra = chr(ord("A") + posicao)
        raiz = "%s:\\" % letra
        etiqueta, sistema_de_ficheiros = _informacao_do_volume(raiz)
        tamanho, livre = _capacidade_do_volume(raiz)
        volumes.append(
            {
                "letter": letra,
                "root": raiz,
                "path": r"\\.\%s:" % letra,
                "label": etiqueta,
                "filesystem": sistema_de_ficheiros or "RAW",
                "size_bytes": tamanho,
                "free_bytes": livre,
                "drive_type": TIPOS_DE_UNIDADE.get(
                    kernel32.GetDriveTypeW(raiz), "Desconhecido"
                ),
                "disk_index": _disco_do_volume(letra),
            }
        )
    return volumes


def is_admin() -> bool:
    """Indica se o processo esta a correr com privilegios de Administrador."""
    try:
        return bool(_get_shell32().IsUserAnAdmin())
    except Exception:
        return False


def _argumentos_de_relancamento() -> str:
    """Argumentos que repetem o arranque actual (incluindo o modo ``-m``)."""
    modulo = getattr(getattr(sys.modules.get("__main__"), "__spec__", None), "name", "")
    if modulo:
        if modulo.endswith(".__main__"):
            modulo = modulo[: -len(".__main__")]
        return subprocess.list2cmdline(["-m", modulo] + sys.argv[1:])
    return subprocess.list2cmdline(sys.argv)


def relaunch_as_admin() -> bool:
    """Relanca a aplicacao pedindo elevacao ao Windows (UAC).

    Devolve True se o processo elevado foi lancado — nesse caso o processo
    actual deve terminar. Devolve False se ja havia privilegios ou se o
    utilizador recusou o pedido de elevacao.
    """
    if is_admin():
        return False
    try:
        resultado = _get_shell32().ShellExecuteW(
            None,
            "runas",
            sys.executable,
            _argumentos_de_relancamento(),
            os.getcwd(),
            SW_SHOWNORMAL,
        )
    except Exception:
        return False
    return int(resultado) > SHELL_EXECUTE_MINIMO
