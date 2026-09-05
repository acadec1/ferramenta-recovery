"""Testes de src/recovery.py sobre uma imagem sintetica em ficheiro temporario."""

import os
import shutil
import tempfile
import unittest

from src import recovery

SECTOR = 512
BLOCK = 4096


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.tmp, "saida")
        self.device = os.path.join(self.tmp, "disco.dd")
        # Imagem de 64 blocos: cada bloco preenchido com o seu proprio indice.
        with open(self.device, "wb") as image:
            for block_index in range(64):
                image.write(bytes([block_index % 256]) * BLOCK)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _read(self, path: str) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def _entry(self, **overrides):
        entry = {
            "name": "ficheiro.bin",
            "size": BLOCK,
            "block_size": BLOCK,
            "sector_size": SECTOR,
            "partition_offset": 0,
            "runs": [{"block": 3, "count": 1}],
        }
        entry.update(overrides)
        return entry

    def test_recupera_run_unico(self):
        path = recovery.recover_file(self.device, self._entry(), self.output_dir)
        self.assertEqual(os.path.basename(path), "ficheiro.bin")
        self.assertEqual(self._read(path), bytes([3]) * BLOCK)

    def test_cria_pasta_de_destino(self):
        destino = os.path.join(self.tmp, "nova", "pasta")
        path = recovery.recover_file(self.device, self._entry(), destino)
        self.assertTrue(os.path.isfile(path))

    def test_runs_multiplos_sao_concatenados(self):
        entry = self._entry(
            size=2 * BLOCK, runs=[{"block": 5, "count": 1}, {"block": 9, "count": 1}]
        )
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(data, bytes([5]) * BLOCK + bytes([9]) * BLOCK)

    def test_tamanho_trunca_o_ultimo_cluster(self):
        entry = self._entry(size=BLOCK + 10, runs=[{"block": 2, "count": 2}])
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(len(data), BLOCK + 10)
        self.assertEqual(data, bytes([2]) * BLOCK + bytes([3]) * 10)

    def test_run_com_varios_clusters(self):
        entry = self._entry(size=3 * BLOCK, runs=[{"block": 10, "count": 3}])
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(data, bytes([10]) * BLOCK + bytes([11]) * BLOCK + bytes([12]) * BLOCK)

    def test_tamanho_desconhecido_escreve_clusters_completos(self):
        entry = self._entry(size=0, runs=[{"block": 4, "count": 2}])
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(len(data), 2 * BLOCK)

    def test_offset_da_particao_e_somado(self):
        entry = self._entry(partition_offset=8 * BLOCK, runs=[{"block": 1, "count": 1}])
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(data, bytes([9]) * BLOCK)

    def test_leitura_nao_alinhada_ao_sector(self):
        # Offset de particao propositadamente desalinhado (100 bytes).
        entry = self._entry(
            partition_offset=100, size=BLOCK, runs=[{"block": 1, "count": 1}]
        )
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        with open(self.device, "rb") as image:
            image.seek(100 + BLOCK)
            esperado = image.read(BLOCK)
        self.assertEqual(data, esperado)

    def test_leitura_alem_do_fim_do_dispositivo(self):
        entry = self._entry(size=2 * BLOCK, runs=[{"block": 63, "count": 2}])
        data = self._read(recovery.recover_file(self.device, entry, self.output_dir))
        self.assertEqual(data, bytes([63]) * BLOCK)

    def test_entrada_sem_clusters(self):
        with self.assertRaises(ValueError):
            recovery.recover_file(self.device, self._entry(runs=[]), self.output_dir)

    def test_nomes_repetidos_nao_se_sobrepoem(self):
        primeiro = recovery.recover_file(self.device, self._entry(), self.output_dir)
        segundo = recovery.recover_file(self.device, self._entry(), self.output_dir)
        self.assertNotEqual(primeiro, segundo)
        self.assertEqual(os.path.basename(segundo), "ficheiro_1.bin")

    def test_sanitize_filename(self):
        self.assertEqual(recovery.sanitize_filename("a:b?c.txt"), "a_b_c.txt")
        self.assertEqual(recovery.sanitize_filename("..\\..\\evil.txt"), "_.._evil.txt")
        self.assertEqual(recovery.sanitize_filename(""), "recuperado.bin")
        self.assertEqual(recovery.sanitize_filename("   "), "recuperado.bin")

    def test_nome_invalido_e_sanitizado_no_destino(self):
        entry = self._entry(name="rela:torio?.doc")
        path = recovery.recover_file(self.device, entry, self.output_dir)
        self.assertEqual(os.path.basename(path), "rela_torio_.doc")
        self.assertEqual(os.path.dirname(path), self.output_dir)


if __name__ == "__main__":
    unittest.main()
