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


class FakeKernel32ComVolumes(FakeKernel32):
    """Acrescenta ao kernel32 simulado as chamadas de volumes logicos."""

    def __init__(self, sizes, volumes, mascara=None):
        super().__init__(sizes)
        self.volumes = volumes  # {"C": {"fs":..., "label":..., "size":..., "livre":...}}
        self.mascara = mascara

    def _letra_do_caminho(self, path):
        if path.endswith(":\\"):
            return path[0]
        return path.rsplit("\\", 1)[-1].rstrip(":")

    def GetLogicalDrives(self):
        if self.mascara is not None:
            return self.mascara
        mascara = 0
        for letra in self.volumes:
            mascara |= 1 << (ord(letra) - ord("A"))
        return mascara

    def GetVolumeInformationW(self, raiz, nome, tam_nome, serie, comp, flags,
                              sistema, tam_sistema):
        volume = self.volumes.get(self._letra_do_caminho(raiz))
        if volume is None or volume.get("erro"):
            return 0
        nome.value = volume.get("label", "")
        sistema.value = volume.get("fs", "NTFS")
        return 1

    def GetDiskFreeSpaceExW(self, raiz, disponivel, total, livre):
        volume = self.volumes.get(self._letra_do_caminho(raiz))
        if volume is None or volume.get("erro"):
            return 0
        total.contents.value = volume.get("size", 0)
        livre.contents.value = volume.get("livre", 0)
        disponivel.contents.value = volume.get("livre", 0)
        return 1

    def GetDriveTypeW(self, raiz):
        volume = self.volumes.get(self._letra_do_caminho(raiz))
        return 3 if volume is None else volume.get("tipo", 3)

    def CreateFileW(self, path, access, share, sa, disposition, flags, template):
        if "PhysicalDrive" in path:
            return super().CreateFileW(path, access, share, sa, disposition, flags,
                                       template)
        letra = self._letra_do_caminho(path)
        if letra not in self.volumes:
            return device_reader.INVALID_HANDLE_VALUE
        self._next_handle += 1
        self.opened.append((self._next_handle, path, access))
        return self._next_handle

    def DeviceIoControl(self, handle, code, inbuf, insize, outbuf, outsize, ret, ovl):
        if code != device_reader.IOCTL_STORAGE_GET_DEVICE_NUMBER:
            return super().DeviceIoControl(handle, code, inbuf, insize, outbuf,
                                           outsize, ret, ovl)
        self.ioctls.append(code)
        path = next(p for h, p, _ in self.opened if h == handle.value)
        volume = self.volumes[self._letra_do_caminho(path)]
        if "disco" not in volume:
            return 0
        ctypes.memmove(outbuf, struct.pack("<III", 7, volume["disco"], 1), 12)
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


class VolumesLogicosTest(unittest.TestCase):
    def _patch(self, fake):
        patcher = mock.patch.object(device_reader, "_get_kernel32", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_lista_volumes(self):
        self._patch(
            FakeKernel32ComVolumes(
                {0: 500107862016, 1: 128035676160},
                {
                    "C": {"fs": "NTFS", "label": "", "size": 126_400_000_000,
                          "livre": 20_000_000_000, "disco": 1, "tipo": 3},
                    "D": {"fs": "NTFS", "label": "Mamboza Jr.",
                          "size": 500_000_000_000, "livre": 195_000_000_000,
                          "disco": 0, "tipo": 3},
                },
            )
        )
        volumes = device_reader.list_logical_volumes()
        self.assertEqual([v["letter"] for v in volumes], ["C", "D"])
        self.assertEqual(volumes[0]["path"], r"\\.\C:")
        self.assertEqual(volumes[0]["root"], "C:\\")
        self.assertEqual(volumes[0]["disk_index"], 1)
        self.assertEqual(volumes[1]["label"], "Mamboza Jr.")
        self.assertEqual(volumes[1]["disk_index"], 0)
        self.assertEqual(volumes[1]["filesystem"], "NTFS")
        self.assertEqual(volumes[1]["drive_type"], "Fixo")
        self.assertEqual(volumes[1]["size_bytes"], 500_000_000_000)
        self.assertEqual(volumes[1]["free_bytes"], 195_000_000_000)

    def test_volume_removivel_e_exfat(self):
        self._patch(
            FakeKernel32ComVolumes(
                {2: 58_300_000_000},
                {"G": {"fs": "exFAT", "label": "SD Card", "size": 58_300_000_000,
                       "livre": 1_000, "disco": 2, "tipo": 2}},
            )
        )
        volume = device_reader.list_logical_volumes()[0]
        self.assertEqual(volume["filesystem"], "exFAT")
        self.assertEqual(volume["drive_type"], "Removivel")

    def test_volume_sem_sistema_de_ficheiros_reconhecido(self):
        self._patch(
            FakeKernel32ComVolumes(
                {0: 1}, {"E": {"erro": True, "disco": 0, "tipo": 2}}
            )
        )
        volume = device_reader.list_logical_volumes()[0]
        self.assertEqual(volume["filesystem"], "RAW")
        self.assertIsNone(volume["size_bytes"])
        self.assertIsNone(volume["free_bytes"])

    def test_volume_sem_disco_associado(self):
        self._patch(
            FakeKernel32ComVolumes(
                {}, {"Z": {"fs": "NTFS", "size": 1, "livre": 1, "tipo": 4}}
            )
        )
        self.assertIsNone(device_reader.list_logical_volumes()[0]["disk_index"])

    def test_volume_distribuido_por_varios_discos(self):
        fake = self._patch(
            FakeKernel32ComVolumes(
                {}, {"R": {"fs": "NTFS", "size": 1, "livre": 1,
                           "disco": device_reader.NUMERO_DE_DISCO_INVALIDO}}
            )
        )
        self.assertIsNone(device_reader.list_logical_volumes()[0]["disk_index"])
        self.assertIn(device_reader.IOCTL_STORAGE_GET_DEVICE_NUMBER, fake.ioctls)

    def test_sem_volumes_montados(self):
        self._patch(FakeKernel32ComVolumes({}, {}, mascara=0))
        self.assertEqual(device_reader.list_logical_volumes(), [])


if __name__ == "__main__":
    unittest.main()
