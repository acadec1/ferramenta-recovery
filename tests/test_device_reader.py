"""Testes de src/device_reader.py com kernel32 simulado (sem hardware real)."""

import ctypes
import struct
import unittest
from unittest import mock

from src import device_reader


class FakeKernel32:
    """Substituto de kernel32: apenas os discos em ``sizes`` existem.

    ``length_info_ok=False`` reproduz o comportamento sem elevacao, em que
    IOCTL_DISK_GET_LENGTH_INFO falha com acesso negado e apenas
    IOCTL_DISK_GET_DRIVE_GEOMETRY_EX responde.
    """

    def __init__(self, sizes: dict, length_info_ok: bool = True, geometry_ok: bool = True):
        self.sizes = sizes
        self.length_info_ok = length_info_ok
        self.geometry_ok = geometry_ok
        self.opened = []
        self.closed = []
        self.ioctls = []
        self._next_handle = 100

    def _index_of(self, path):
        return int(path.rsplit("PhysicalDrive", 1)[1])

    def CreateFileW(self, path, access, share, sa, disposition, flags, template):
        if self._index_of(path) not in self.sizes:
            return device_reader.INVALID_HANDLE_VALUE
        if access == device_reader.GENERIC_READ and not self.length_info_ok:
            return device_reader.INVALID_HANDLE_VALUE  # sem privilegios
        self._next_handle += 1
        self.opened.append((self._next_handle, path, access))
        return self._next_handle

    def DeviceIoControl(self, handle, code, inbuf, insize, outbuf, outsize, ret, ovl):
        self.ioctls.append(code)
        path = next(p for h, p, _ in self.opened if h == handle.value)
        size = self.sizes[self._index_of(path)]
        if code == device_reader.IOCTL_DISK_GET_LENGTH_INFO:
            if not self.length_info_ok:
                return 0
            ctypes.memmove(outbuf, struct.pack("<q", size), 8)
            return 1
        if code == device_reader.IOCTL_DISK_GET_DRIVE_GEOMETRY_EX:
            if not self.geometry_ok:
                return 0
            ctypes.memmove(outbuf, b"\x00" * 24 + struct.pack("<q", size), 32)
            return 1
        raise AssertionError("ioctl inesperado: %#x" % code)

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


class DeviceReaderTest(unittest.TestCase):
    def _patch(self, fake):
        patcher = mock.patch.object(device_reader, "_get_kernel32", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_physical_drive_path(self):
        self.assertEqual(device_reader.physical_drive_path(3), r"\\.\PhysicalDrive3")

    def test_get_drive_size_com_privilegios(self):
        fake = self._patch(FakeKernel32({0: 512 * 1024 * 1024}))
        self.assertEqual(device_reader.get_drive_size(0), 512 * 1024 * 1024)
        self.assertEqual(fake.ioctls, [device_reader.IOCTL_DISK_GET_LENGTH_INFO])
        self.assertEqual(len(fake.closed), 1)

    def test_get_drive_size_sem_privilegios_usa_geometria(self):
        fake = self._patch(FakeKernel32({1: 500107862016}, length_info_ok=False))
        self.assertEqual(device_reader.get_drive_size(1), 500107862016)
        self.assertIn(device_reader.IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, fake.ioctls)
        self.assertEqual(len(fake.closed), 1)

    def test_get_drive_size_dispositivo_inexistente(self):
        self._patch(FakeKernel32({}))
        self.assertIsNone(device_reader.get_drive_size(7))

    def test_get_drive_size_ioctls_falhados_libertam_handle(self):
        fake = self._patch(
            FakeKernel32({0: 1}, length_info_ok=False, geometry_ok=False)
        )
        self.assertIsNone(device_reader.get_drive_size(0))
        self.assertEqual(len(fake.closed), 1)

    def test_list_physical_drives_ignora_numeros_em_falta(self):
        self._patch(FakeKernel32({0: 1000, 2: 2000}))
        drives = device_reader.list_physical_drives(max_index=4)
        self.assertEqual(
            drives,
            [
                {"index": 0, "path": r"\\.\PhysicalDrive0", "size_bytes": 1000},
                {"index": 2, "path": r"\\.\PhysicalDrive2", "size_bytes": 2000},
            ],
        )

    def test_list_physical_drives_sem_discos(self):
        self._patch(FakeKernel32({}))
        self.assertEqual(device_reader.list_physical_drives(max_index=4), [])

    def test_is_admin_devolve_bool(self):
        self.assertIsInstance(device_reader.is_admin(), bool)


if __name__ == "__main__":
    unittest.main()
