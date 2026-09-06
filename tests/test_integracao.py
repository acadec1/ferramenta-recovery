"""Testes de integracao com o pytsk3 verdadeiro, sobre uma imagem FAT16 real.

Ao contrario dos restantes testes, aqui nao ha mocks: exercitam-se o varrimento,
a reconstrucao a partir dos clusters, o carving e a verificacao de integridade
sobre uma imagem de disco gerada em ficheiro. Nao e preciso hardware nem
privilegios de Administrador.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import carving, filesystem_parser, integrity, recovery
from tests.fat16 import construir_imagem

try:
    import pytsk3
except ImportError:  # pragma: no cover - depende do ambiente
    pytsk3 = None

CONTEUDO_APAGADO = b"CONTEUDO SECRETO APAGADO\n" * 40  # 1000 bytes


@unittest.skipIf(pytsk3 is None, "pytsk3 nao esta instalado")
class VarrimentoRealTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # o FAT16 declara mais de um milhao de registos possiveis; nos testes
        # basta varrer os primeiros para exercitar o percurso completo
        patcher = mock.patch.object(filesystem_parser, "MAX_REGISTOS", 20_000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.imagem = construir_imagem(
            os.path.join(self.tmp, "prova.dd"), CONTEUDO_APAGADO
        )

    def test_encontra_o_ficheiro_apagado(self):
        entradas = filesystem_parser.scan_deleted_entries(self.imagem)
        self.assertEqual(len(entradas), 1)
        entrada = entradas[0]
        self.assertTrue(entrada["name"].endswith("ROVA.TXT"))  # 0xE5 no 1.o byte
        self.assertEqual(entrada["size"], len(CONTEUDO_APAGADO))
        self.assertFalse(entrada["allocated"])
        self.assertTrue(entrada["runs"], "a entrada tem de trazer clusters")

    def test_o_ficheiro_activo_nao_aparece(self):
        entradas = filesystem_parser.scan_deleted_entries(self.imagem)
        self.assertNotIn("ACTIVO.TXT", [e["name"] for e in entradas])

    def test_recupera_o_conteudo_byte_a_byte(self):
        entrada = filesystem_parser.scan_deleted_entries(self.imagem)[0]
        destino = recovery.recover_file(
            self.imagem, entrada, os.path.join(self.tmp, "saida")
        )
        with open(destino, "rb") as ficheiro:
            recuperado = ficheiro.read()
        self.assertEqual(recuperado, CONTEUDO_APAGADO)

    def test_integridade_do_ficheiro_recuperado(self):
        entrada = filesystem_parser.scan_deleted_entries(self.imagem)[0]
        destino = recovery.recover_file(
            self.imagem, entrada, os.path.join(self.tmp, "saida")
        )
        hash_sha256 = integrity.compute_hash(destino)
        self.assertEqual(len(hash_sha256), 64)
        self.assertTrue(integrity.verify_integrity(hash_sha256, destino))

    def test_imagem_sem_ficheiros_apagados(self):
        limpa = construir_imagem(
            os.path.join(self.tmp, "limpa.dd"), com_ficheiro_apagado=False
        )
        self.assertEqual(filesystem_parser.scan_deleted_entries(limpa), [])

    def test_ficheiro_que_nao_e_uma_imagem(self):
        caminho = os.path.join(self.tmp, "lixo.bin")
        with open(caminho, "wb") as ficheiro:
            ficheiro.write(b"\x00" * 4096)
        self.assertEqual(filesystem_parser.scan_deleted_entries(caminho), [])

    def test_caminho_inexistente(self):
        with self.assertRaises(OSError):
            filesystem_parser.scan_deleted_entries(
                os.path.join(self.tmp, "nao_existe.dd")
            )

    def test_diagnostico_do_varrimento(self):
        diagnostico = {}
        filesystem_parser.scan_deleted_entries(self.imagem, diagnostico)
        self.assertEqual(diagnostico["particoes"], 1)
        self.assertEqual(diagnostico["sistemas_de_ficheiros"], 1)
        self.assertEqual(diagnostico["registos_examinados"], 20_001)

    def test_varrimento_dos_registos_nao_duplica_a_entrada(self):
        """A entrada esta na directoria e tambem na MFT: conta uma so vez."""
        entradas = filesystem_parser.scan_deleted_entries(self.imagem)
        inodes = [e["inode"] for e in entradas]
        self.assertEqual(len(inodes), len(set(inodes)))

    def test_constantes_do_tsk_coincidem_com_a_biblioteca(self):
        """As alternativas documentadas tem de bater certo com o pytsk3 real."""
        for nome, valor in filesystem_parser.CONSTANTES_TSK.items():
            if hasattr(pytsk3, nome):
                self.assertEqual(int(getattr(pytsk3, nome)), valor, nome)


@unittest.skipIf(pytsk3 is None, "pytsk3 nao esta instalado")
class CarvingRealTest(unittest.TestCase):
    """O carving nao usa pytsk3, mas aqui corre sobre a mesma imagem real."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_carving_encontra_o_jpeg_apagado(self):
        jpeg = b"\xff\xd8\xff\xe0" + b"J" * 3000 + b"\xff\xd9"
        imagem = construir_imagem(os.path.join(self.tmp, "fotos.dd"), jpeg)
        extraidos = carving.carve_by_signature(
            imagem, "jpeg", os.path.join(self.tmp, "carved")
        )
        self.assertEqual(len(extraidos), 1)
        with open(extraidos[0], "rb") as ficheiro:
            self.assertEqual(ficheiro.read(), jpeg)


if __name__ == "__main__":
    unittest.main()
