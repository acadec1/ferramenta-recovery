"""Testes de src/carving.py sobre uma imagem sintetica em ficheiro temporario."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import carving

FILLER = b"\x00"
EOCD_TAIL = b"\x00" * 18  # restante do End Of Central Directory de um ZIP


def jpeg(payload_size=2000):
    return b"\xff\xd8\xff\xe0" + b"J" * payload_size + b"\xff\xd9"


def pdf(payload_size=2000):
    return b"%PDF-1.7\n" + b"P" * payload_size + b"\n%%EOF"


def docx(payload_size=2000, marker=b"word/document.xml"):
    return b"PK\x03\x04" + marker + b"D" * payload_size + b"PK\x05\x06" + EOCD_TAIL


class ImageBuilder:
    """Constroi uma imagem de disco sintetica e regista o offset de cada bloco."""

    def __init__(self):
        self.data = bytearray()
        self.offsets = []

    def gap(self, size=4096):
        self.data.extend(FILLER * size)
        return self

    def add(self, blob):
        self.offsets.append(len(self.data))
        self.data.extend(blob)
        return self

    def write(self, path):
        with open(path, "wb") as image:
            image.write(bytes(self.data))
        return path


class CarvingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.tmp, "carved")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _device(self, builder):
        return builder.write(os.path.join(self.tmp, "disco.dd"))

    def _read(self, path):
        with open(path, "rb") as handle:
            return handle.read()

    def test_tipos_suportados(self):
        self.assertEqual(carving.supported_types(), ["docx", "jpeg", "pdf"])

    def test_tipo_desconhecido(self):
        builder = ImageBuilder().gap()
        with self.assertRaises(ValueError):
            carving.carve_by_signature(self._device(builder), "mp3", self.output_dir)

    def test_extrai_jpeg(self):
        builder = ImageBuilder().gap().add(jpeg()).gap()
        paths = carving.carve_by_signature(self._device(builder), "jpeg", self.output_dir)
        self.assertEqual(len(paths), 1)
        self.assertEqual(self._read(paths[0]), jpeg())
        self.assertTrue(paths[0].endswith(".jpg"))
        self.assertIn("offset_%d" % builder.offsets[0], os.path.basename(paths[0]))

    def test_alias_jpg(self):
        builder = ImageBuilder().gap().add(jpeg())
        paths = carving.carve_by_signature(self._device(builder), "JPG", self.output_dir)
        self.assertEqual(len(paths), 1)

    def test_extrai_pdf(self):
        builder = ImageBuilder().gap().add(pdf()).gap(1024).add(pdf(3000))
        paths = carving.carve_by_signature(self._device(builder), "pdf", self.output_dir)
        self.assertEqual([self._read(p) for p in paths], [pdf(), pdf(3000)])

    def test_extrai_docx(self):
        builder = ImageBuilder().gap().add(docx())
        paths = carving.carve_by_signature(self._device(builder), "docx", self.output_dir)
        self.assertEqual(self._read(paths[0]), docx())

    def test_zip_sem_marcador_word_e_rejeitado(self):
        builder = ImageBuilder().gap().add(docx(marker=b"xl/workbook.xml"))
        paths = carving.carve_by_signature(self._device(builder), "docx", self.output_dir)
        self.assertEqual(paths, [])

    def test_ficheiro_abaixo_do_tamanho_minimo_e_rejeitado(self):
        builder = ImageBuilder().gap().add(jpeg(payload_size=10)).gap().add(jpeg())
        paths = carving.carve_by_signature(self._device(builder), "jpeg", self.output_dir)
        self.assertEqual(len(paths), 1)
        self.assertEqual(self._read(paths[0]), jpeg())

    def test_header_sem_footer_e_ignorado(self):
        builder = ImageBuilder().gap().add(b"\xff\xd8\xff" + b"J" * 5000)
        paths = carving.carve_by_signature(self._device(builder), "jpeg", self.output_dir)
        self.assertEqual(paths, [])

    def test_varios_ficheiros_por_ordem_de_aparecimento(self):
        builder = ImageBuilder().gap().add(jpeg(1100)).gap(2048).add(jpeg(1200)).gap()
        paths = carving.carve_by_signature(self._device(builder), "jpeg", self.output_dir)
        self.assertEqual([self._read(p) for p in paths], [jpeg(1100), jpeg(1200)])
        self.assertIn("offset_%d" % builder.offsets[0], paths[0])
        self.assertIn("offset_%d" % builder.offsets[1], paths[1])

    def test_assinaturas_entre_blocos_de_leitura(self):
        builder = ImageBuilder().gap(300).add(jpeg()).gap(300).add(pdf())
        device = self._device(builder)
        for chunk_size in (64, 100, 256, 1024):
            with self.subTest(chunk=chunk_size):
                destino = os.path.join(self.output_dir, str(chunk_size))
                with mock.patch.object(carving, "CHUNK_SIZE", chunk_size):
                    paths = carving.carve_by_signature(device, "jpeg", destino)
                self.assertEqual([self._read(p) for p in paths], [jpeg()])

    def test_candidato_maior_que_o_limite_e_abandonado(self):
        builder = ImageBuilder().gap().add(b"\xff\xd8\xff" + b"J" * 20000 + b"\xff\xd9")
        with mock.patch.dict(carving.SIGNATURES["jpeg"], {"max_size": 4096}):
            paths = carving.carve_by_signature(
                self._device(builder), "jpeg", self.output_dir
            )
        self.assertEqual(paths, [])

    def test_dispositivo_vazio(self):
        builder = ImageBuilder()
        paths = carving.carve_by_signature(self._device(builder), "pdf", self.output_dir)
        self.assertEqual(paths, [])

    def test_cria_pasta_de_destino(self):
        destino = os.path.join(self.tmp, "nova", "pasta")
        builder = ImageBuilder().gap().add(pdf())
        carving.carve_by_signature(self._device(builder), "pdf", destino)
        self.assertTrue(os.path.isdir(destino))

    def test_carving_independente_do_filesystem(self):
        # Sem tabela de particoes nem sistema de ficheiros: so bytes soltos.
        builder = ImageBuilder().add(jpeg()).add(pdf()).add(docx())
        device = self._device(builder)
        self.assertEqual(
            len(carving.carve_by_signature(device, "jpeg", self.output_dir)), 1
        )
        self.assertEqual(
            len(carving.carve_by_signature(device, "pdf", self.output_dir)), 1
        )
        self.assertEqual(
            len(carving.carve_by_signature(device, "docx", self.output_dir)), 1
        )


if __name__ == "__main__":
    unittest.main()
