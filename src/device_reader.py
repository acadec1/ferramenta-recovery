r"""Enumeracao de dispositivos fisicos no Windows via \\.\PhysicalDriveN.

Usa ctypes sobre kernel32 (CreateFileW + DeviceIoControl) para obter o tamanho
de cada disco fisico. A leitura bruta exige privilegios de Administrador, mas a
enumeracao funciona sem elevacao: IOCTL_DISK_GET_LENGTH_INFO precisa de acesso
de leitura, enquanto IOCTL_DISK_GET_DRIVE_GEOMETRY_EX responde com acesso zero
e serve de alternativa.
"""

from __future__ import annotations

import ctypes
import struct

DEVICE_PATH_TEMPLATE = r"\\.\PhysicalDrive{}"

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_kernel32 = None


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


def is_admin() -> bool:
    """Indica se o processo esta a correr com privilegios de Administrador."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
