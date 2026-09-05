"""Testes de src/integrity.py."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import integrity

SHA256_VAZIO = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


class IntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _file(self, content, name="ficheiro.bin"):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_hash_de_ficheiro_vazio(self):
        self.assertEqual(integrity.compute_hash(self._file(b"")), SHA256_VAZIO)

    def test_hash_conhecido(self):
        self.assertEqual(integrity.compute_hash(self._file(b"abc")), SHA256_ABC)

    def test_hash_por_blocos_de_ficheiro_grande(self):
        path = self._file(b"x" * (3 * 1024 * 1024 + 7))
        with mock.patch.object(integrity, "CHUNK_SIZE", 4096):
            por_blocos = integrity.compute_hash(path)
        self.assertEqual(por_blocos, integrity.compute_hash(path))

    def test_verify_integrity_com_hash_igual(self):
        path = self._file(b"abc")
        self.assertTrue(integrity.verify_integrity(SHA256_ABC, path))

    def test_verify_integrity_ignora_maiusculas_e_espacos(self):
        path = self._file(b"abc")
        self.assertTrue(integrity.verify_integrity("  " + SHA256_ABC.upper() + " ", path))

    def test_verify_integrity_com_conteudo_alterado(self):
        path = self._file(b"abc alterado")
        self.assertFalse(integrity.verify_integrity(SHA256_ABC, path))

    def test_verify_integrity_sem_hash_de_referencia(self):
        path = self._file(b"abc")
        self.assertFalse(integrity.verify_integrity("", path))
        self.assertFalse(integrity.verify_integrity(None, path))

    def test_ficheiro_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            integrity.compute_hash(os.path.join(self.tmp, "nao_existe.bin"))


if __name__ == "__main__":
    unittest.main()
