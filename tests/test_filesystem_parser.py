"""Testes de src/filesystem_parser.py com um pytsk3 simulado (sem imagem real)."""

import types
import unittest
from unittest import mock

from src import filesystem_parser

# Valores reais das constantes do Sleuth Kit (verificados contra o pytsk3
# instalado em tests/test_integracao.py).
TSK_VS_PART_FLAG_ALLOC = 0x01
TSK_FS_NAME_FLAG_ALLOC = 0x01
TSK_FS_NAME_FLAG_UNALLOC = 0x02
TSK_FS_META_FLAG_ALLOC = 0x01
TSK_FS_META_FLAG_UNALLOC = 0x02
TSK_FS_META_TYPE_REG = 0x01
TSK_FS_META_TYPE_DIR = 0x02
TSK_FS_ATTR_TYPE_DEFAULT = 0x01
TSK_FS_ATTR_TYPE_NTFS_DATA = 0x80
TSK_FS_ATTR_RES = 0x04
TSK_FS_ATTR_NONRES = 0x02
TSK_FS_ATTR_RUN_FLAG_FILLER = 0x01
TSK_FS_ATTR_RUN_FLAG_SPARSE = 0x02


class FakeRun:
    def __init__(self, addr, length, flags=0):
        self.addr = addr
        self.len = length
        self.flags = flags


class FakeAttribute:
    def __init__(self, runs, attr_type=TSK_FS_ATTR_TYPE_NTFS_DATA, name=None,
                 flags=TSK_FS_ATTR_NONRES):
        self.info = types.SimpleNamespace(type=attr_type, name=name, flags=flags)
        self._runs = runs

    def __iter__(self):
        return iter(self._runs)


class FakeFile:
    def __init__(self, name, *, deleted=False, size=0, inode=1, is_dir=False,
                 runs=(), attributes=None, children=None, mtime=0, crtime=0):
        name_flags = TSK_FS_NAME_FLAG_UNALLOC if deleted else TSK_FS_NAME_FLAG_ALLOC
        meta_flags = TSK_FS_META_FLAG_UNALLOC if deleted else TSK_FS_META_FLAG_ALLOC
        self.info = types.SimpleNamespace(
            name=types.SimpleNamespace(name=name.encode(), flags=name_flags),
            meta=types.SimpleNamespace(
                addr=inode,
                size=size,
                flags=meta_flags,
                type=TSK_FS_META_TYPE_DIR if is_dir else TSK_FS_META_TYPE_REG,
                mtime=mtime,
                crtime=crtime,
            ),
        )
        if attributes is None:
            attributes = [FakeAttribute(list(runs))] if runs else []
        self._attributes = attributes
        self._children = list(children or [])

    def __iter__(self):
        return iter(self._attributes)

    def as_directory(self):
        return FakeDirectory(self._children)


class FakeOrphanFile(FakeFile):
    """Entrada sem metadados (nome apagado cujo registo ja foi reutilizado)."""

    def __init__(self, name):
        super().__init__(name, deleted=True)
        self.info.meta = None


class FakeDirectory:
    def __init__(self, entries):
        self._entries = list(entries)

    def __iter__(self):
        return iter(self._entries)


class FakeFSInfo:
    """Sistema de ficheiros simulado, com directorias e registos de metadados.

    ``registos`` e o equivalente a MFT: {inode: FakeFile}. ``orfaos`` sao as
    entradas que o TSK poe na directoria virtual $OrphanFiles.
    """

    def __init__(self, image, offset=0, root=None, ftype="TSK_FS_TYPE_NTFS",
                 block_size=4096, dev_bsize=512, registos=None, orfaos=None,
                 first_inum=0, last_inum=None):
        self.image = image
        self.offset = offset
        self.registos = dict(registos or {})
        self.orfaos = list(orfaos or [])
        if last_inum is None:
            last_inum = max(self.registos) if self.registos else -1
        self.info = types.SimpleNamespace(
            ftype=ftype, block_size=block_size, dev_bsize=dev_bsize,
            first_inum=first_inum, last_inum=last_inum,
        )
        self._root = root or FakeDirectory([])

    def open_dir(self, path="/"):
        if path == filesystem_parser.CAMINHO_DOS_ORFAOS:
            if not self.orfaos:
                raise IOError("sem ficheiros orfaos")
            return FakeDirectory(self.orfaos)
        return self._root

    def open_meta(self, inode=0):
        if inode not in self.registos:
            raise IOError("registo %d por usar" % inode)
        return self.registos[inode]


class FakePart:
    def __init__(self, start, length, flags=TSK_VS_PART_FLAG_ALLOC, desc=b"NTFS"):
        self.start = start
        self.len = length
        self.flags = flags
        self.desc = desc


def build_fake_pytsk3(root=None, parts=None, volume_error=False, fs_error=False,
                      **fs_kwargs):
    """Constroi um modulo pytsk3 simulado com o conteudo indicado."""
    module = types.SimpleNamespace(
        TSK_VS_PART_FLAG_ALLOC=TSK_VS_PART_FLAG_ALLOC,
        TSK_FS_NAME_FLAG_UNALLOC=TSK_FS_NAME_FLAG_UNALLOC,
        TSK_FS_META_FLAG_UNALLOC=TSK_FS_META_FLAG_UNALLOC,
        TSK_FS_META_TYPE_DIR=TSK_FS_META_TYPE_DIR,
        TSK_FS_ATTR_TYPE_DEFAULT=TSK_FS_ATTR_TYPE_DEFAULT,
        TSK_FS_ATTR_TYPE_NTFS_DATA=TSK_FS_ATTR_TYPE_NTFS_DATA,
        TSK_FS_ATTR_RES=TSK_FS_ATTR_RES,
        TSK_FS_ATTR_RUN_FLAG_FILLER=TSK_FS_ATTR_RUN_FLAG_FILLER,
        TSK_FS_ATTR_RUN_FLAG_SPARSE=TSK_FS_ATTR_RUN_FLAG_SPARSE,
    )
    module.opened_images = []
    module.opened_offsets = []

    def img_info(path):
        module.opened_images.append(path)
        return types.SimpleNamespace(path=path)

    class Volume:
        def __init__(self, image):
            if volume_error:
                raise IOError("sem tabela de particoes")
            self.info = types.SimpleNamespace(block_size=512)

        def __iter__(self):
            return iter(parts or [])

    def fs_info(image, offset=0):
        module.opened_offsets.append(offset)
        if fs_error:
            raise IOError("sistema de ficheiros nao reconhecido")
        return FakeFSInfo(image, offset=offset, root=root, **fs_kwargs)

    module.Img_Info = img_info
    module.Volume_Info = Volume
    module.FS_Info = fs_info
    return module


class FilesystemParserTest(unittest.TestCase):
    def _scan(self, fake, device=r"\\.\PhysicalDrive0"):
        with mock.patch.object(filesystem_parser, "pytsk3", fake):
            return filesystem_parser.scan_deleted_entries(device)

    def test_lista_apenas_entradas_nao_alocadas(self):
        root = FakeDirectory(
            [
                FakeFile(".", is_dir=True, inode=5),
                FakeFile("relatorio.docx", deleted=True, size=15000, inode=42,
                         runs=[FakeRun(100, 2)], mtime=1700000000),
                FakeFile("ativo.txt", size=10, inode=43, runs=[FakeRun(200, 1)]),
                FakeFile(
                    "Documentos", is_dir=True, inode=44,
                    children=[
                        FakeFile("foto.jpg", deleted=True, size=4096, inode=45,
                                 runs=[FakeRun(300, 1)]),
                    ],
                ),
            ]
        )
        fake = build_fake_pytsk3(root=root, parts=[FakePart(2048, 1000000)])
        entries = self._scan(fake)

        self.assertEqual([e["name"] for e in entries], ["relatorio.docx", "foto.jpg"])
        self.assertEqual([e["path"] for e in entries],
                         ["/relatorio.docx", "/Documentos/foto.jpg"])
        self.assertTrue(all(e["allocated"] is False for e in entries))
        self.assertEqual(fake.opened_images, [r"\\.\PhysicalDrive0"])

    def test_detalhes_da_entrada(self):
        root = FakeDirectory(
            [FakeFile("relatorio.docx", deleted=True, size=15000, inode=42,
                      runs=[FakeRun(100, 2), FakeRun(500, 1)], mtime=1700000000)]
        )
        fake = build_fake_pytsk3(root=root, parts=[FakePart(2048, 1000000)])
        entry = self._scan(fake)[0]

        self.assertEqual(entry["size"], 15000)
        self.assertEqual(entry["inode"], 42)
        self.assertEqual(entry["partition_offset"], 2048 * 512)
        self.assertEqual(entry["block_size"], 4096)
        self.assertEqual(entry["sector_size"], 512)
        self.assertEqual(entry["runs"],
                         [{"block": 100, "count": 2}, {"block": 500, "count": 1}])
        self.assertEqual(entry["sectors"],
                         [{"sector": 800, "count": 16}, {"sector": 4000, "count": 8}])
        self.assertEqual(entry["mtime"], 1700000000)
        self.assertTrue(entry["mtime_iso"].startswith("2023-11-14"))
        self.assertFalse(entry["resident"])

    def test_runs_sparse_e_filler_sao_ignorados(self):
        root = FakeDirectory(
            [FakeFile("x.bin", deleted=True, size=100, inode=10, runs=[
                FakeRun(10, 1),
                FakeRun(11, 1, flags=TSK_FS_ATTR_RUN_FLAG_SPARSE),
                FakeRun(12, 0),
                FakeRun(13, 1, flags=TSK_FS_ATTR_RUN_FLAG_FILLER),
            ])]
        )
        entry = self._scan(build_fake_pytsk3(root=root, parts=[FakePart(0, 100)]))[0]
        self.assertEqual(entry["runs"], [{"block": 10, "count": 1}])

    def test_atributo_residente_e_fluxos_alternativos(self):
        residente = FakeAttribute([], flags=TSK_FS_ATTR_RES)
        ads = FakeAttribute([FakeRun(900, 5)], name=b"Zone.Identifier")
        root = FakeDirectory(
            [FakeFile("nota.txt", deleted=True, size=64, inode=11,
                      attributes=[residente, ads])]
        )
        entry = self._scan(build_fake_pytsk3(root=root, parts=[FakePart(0, 100)]))[0]
        self.assertTrue(entry["resident"])
        self.assertEqual(entry["runs"], [])

    def test_entrada_sem_metadados(self):
        root = FakeDirectory([FakeOrphanFile("orfao.dat")])
        entry = self._scan(build_fake_pytsk3(root=root, parts=[FakePart(0, 100)]))[0]
        self.assertEqual(entry["name"], "orfao.dat")
        self.assertEqual(entry["size"], 0)
        self.assertIsNone(entry["inode"])
        self.assertIsNone(entry["mtime_iso"])

    def test_particoes_meta_sao_ignoradas(self):
        root = FakeDirectory([FakeFile("a.txt", deleted=True, inode=1)])
        fake = build_fake_pytsk3(
            root=root,
            parts=[FakePart(0, 1), FakePart(2048, 500000), FakePart(1, 2)],
        )
        self._scan(fake)
        self.assertEqual(fake.opened_offsets, [2048 * 512])

    def test_particao_nao_alocada_e_ignorada(self):
        root = FakeDirectory([FakeFile("a.txt", deleted=True, inode=1)])
        fake = build_fake_pytsk3(
            root=root, parts=[FakePart(100, 1000, flags=0), FakePart(2048, 1000)]
        )
        self._scan(fake)
        self.assertEqual(fake.opened_offsets, [2048 * 512])

    def test_sem_tabela_de_particoes_usa_offset_zero(self):
        root = FakeDirectory([FakeFile("a.txt", deleted=True, inode=1,
                                       runs=[FakeRun(1, 1)])])
        fake = build_fake_pytsk3(root=root, volume_error=True,
                                 ftype="TSK_FS_TYPE_FAT32")
        entries = self._scan(fake)
        self.assertEqual(fake.opened_offsets, [0])
        self.assertEqual(entries[0]["fs_type"], "TSK_FS_TYPE_FAT32")

    def test_filesystem_ilegivel_nao_rebenta(self):
        fake = build_fake_pytsk3(parts=[FakePart(2048, 1000)], fs_error=True)
        self.assertEqual(self._scan(fake), [])

    def test_directoria_ciclica_nao_causa_recursao_infinita(self):
        ciclo = FakeFile("Loop", is_dir=True, inode=77)
        ciclo._children = [ciclo, FakeFile("dentro.txt", deleted=True, inode=78)]
        root = FakeDirectory([ciclo])
        entries = self._scan(build_fake_pytsk3(root=root, parts=[FakePart(0, 100)]))
        self.assertEqual([e["path"] for e in entries], ["/Loop/dentro.txt"])

    def test_constantes_em_falta_usam_a_alternativa_documentada(self):
        """Ha versoes do pytsk3 que nao exportam todos os nomes."""
        residente = FakeAttribute([], flags=TSK_FS_ATTR_RES)
        root = FakeDirectory([FakeFile("nota.txt", deleted=True, size=64, inode=11,
                                       attributes=[residente])])
        fake = build_fake_pytsk3(root=root, parts=[FakePart(0, 100)])
        del fake.TSK_FS_ATTR_RES  # a biblioteca nao exporta este nome

        entry = self._scan(fake)[0]

        self.assertTrue(entry["resident"])
        self.assertEqual(filesystem_parser.CONSTANTES_TSK["TSK_FS_ATTR_RES"], 4)

    def test_varre_os_registos_nao_alocados(self):
        """Em NTFS os apagados nao estao nas directorias, estao na MFT."""
        root = FakeDirectory([FakeFile("activo.txt", size=10, inode=5,
                                       runs=[FakeRun(1, 1)])])
        registos = {
            5: FakeFile("activo.txt", size=10, inode=5, runs=[FakeRun(1, 1)]),
            7: FakeFile("", deleted=True, size=2048, inode=7, runs=[FakeRun(90, 2)]),
            9: FakeFile("", deleted=True, size=4096, inode=9, runs=[FakeRun(95, 1)]),
        }
        fake = build_fake_pytsk3(root=root, parts=[FakePart(0, 1000)],
                                 registos=registos)
        entradas = self._scan(fake)

        self.assertEqual(len(entradas), 2)
        self.assertEqual([e["inode"] for e in entradas], [7, 9])
        self.assertEqual(entradas[0]["name"], "registo_7")  # sem nome recuperavel
        self.assertEqual(entradas[0]["path"], filesystem_parser.SEM_CAMINHO)
        self.assertEqual(entradas[0]["origem"], filesystem_parser.ORIGEM_REGISTO)
        self.assertEqual(entradas[0]["runs"], [{"block": 90, "count": 2}])

    def test_registos_alocados_directorias_e_vazios_sao_ignorados(self):
        registos = {
            1: FakeFile("activo.txt", size=10, inode=1),  # alocado
            2: FakeFile("", deleted=True, size=0, inode=2),  # sem conteudo
            3: FakeFile("pasta", deleted=True, size=100, inode=3, is_dir=True),
            4: FakeFile("", deleted=True, size=50, inode=4, runs=[FakeRun(7, 1)]),
        }
        fake = build_fake_pytsk3(parts=[FakePart(0, 1000)], registos=registos)
        entradas = self._scan(fake)
        self.assertEqual([e["inode"] for e in entradas], [4])

    def test_entrada_de_directorio_nao_se_repete_no_varrimento(self):
        apagado = FakeFile("apagado.docx", deleted=True, size=15000, inode=42,
                           runs=[FakeRun(100, 2)])
        root = FakeDirectory([apagado])
        fake = build_fake_pytsk3(root=root, parts=[FakePart(0, 1000)],
                                 registos={42: apagado})
        entradas = self._scan(fake)

        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["name"], "apagado.docx")
        self.assertEqual(entradas[0]["origem"], filesystem_parser.ORIGEM_DIRECTORIO)

    def test_ficheiros_orfaos_trazem_o_nome(self):
        orfao = FakeFile("foto_apagada.jpg", deleted=True, size=4096, inode=77,
                         runs=[FakeRun(300, 1)])
        fake = build_fake_pytsk3(parts=[FakePart(0, 1000)], orfaos=[orfao],
                                 registos={77: orfao})
        entradas = self._scan(fake)

        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["name"], "foto_apagada.jpg")
        self.assertIn("$OrphanFiles", entradas[0]["path"])
        self.assertEqual(entradas[0]["origem"], filesystem_parser.ORIGEM_DIRECTORIO)

    def test_limite_de_registos_examinados(self):
        fake = build_fake_pytsk3(parts=[FakePart(0, 1000)], registos={},
                                 last_inum=10_000_000)
        with mock.patch.object(filesystem_parser, "MAX_REGISTOS", 50):
            diagnostico = {}
            with mock.patch.object(filesystem_parser, "pytsk3", fake):
                filesystem_parser.scan_deleted_entries(r"\\.\PhysicalDrive0",
                                                       diagnostico)
        self.assertEqual(diagnostico["registos_examinados"], 51)

    def test_diagnostico_do_varrimento(self):
        root = FakeDirectory([FakeFile("x.txt", deleted=True, inode=3,
                                       runs=[FakeRun(1, 1)])])
        fake = build_fake_pytsk3(root=root, parts=[FakePart(0, 1000)],
                                 registos={3: FakeFile("x.txt", deleted=True, inode=3)})
        diagnostico = {}
        with mock.patch.object(filesystem_parser, "pytsk3", fake):
            filesystem_parser.scan_deleted_entries(r"\\.\PhysicalDrive0", diagnostico)

        self.assertEqual(diagnostico["particoes"], 1)
        self.assertEqual(diagnostico["sistemas_de_ficheiros"], 1)
        self.assertEqual(diagnostico["tipos"], ["TSK_FS_TYPE_NTFS"])
        self.assertGreaterEqual(diagnostico["registos_examinados"], 1)

    def test_diagnostico_quando_nenhum_filesystem_abre(self):
        fake = build_fake_pytsk3(parts=[FakePart(2048, 1000)], fs_error=True)
        diagnostico = {}
        with mock.patch.object(filesystem_parser, "pytsk3", fake):
            entradas = filesystem_parser.scan_deleted_entries(
                r"\\.\PhysicalDrive0", diagnostico
            )
        self.assertEqual(entradas, [])
        self.assertEqual(diagnostico["particoes"], 1)
        self.assertEqual(diagnostico["sistemas_de_ficheiros"], 0)

    def test_sem_pytsk3_instalado(self):
        with mock.patch.object(filesystem_parser, "pytsk3", None):
            with self.assertRaises(RuntimeError):
                filesystem_parser.scan_deleted_entries(r"\\.\PhysicalDrive0")


if __name__ == "__main__":
    unittest.main()
