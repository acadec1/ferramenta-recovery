"""Testes de src/report.py."""

import os
import shutil
import tempfile
import unittest

from src.audit_log import (
    ACTION_RECOVER,
    ACTION_SCAN,
    ACTION_VERIFY_FAILED,
    ACTION_VERIFY_OK,
)

try:
    from src import report
except ImportError:  # pragma: no cover - depende do ambiente
    report = None

DISPOSITIVO = r"\\.\PhysicalDrive0"


def evento(action, file_path=None, timestamp="2026-09-05T10:00:00+00:00",
           device_path=DISPOSITIVO, file_hash=None, os_user="mambo",
           app_user="admin", identificador=1):
    return {
        "id": identificador,
        "timestamp": timestamp,
        "device_path": device_path,
        "action": action,
        "file_path": file_path,
        "file_hash": file_hash,
        "os_user": os_user,
        "app_user": app_user,
    }


EVENTOS = [
    evento(ACTION_SCAN, timestamp="2026-09-05T10:00:00+00:00", identificador=1),
    evento(ACTION_RECOVER, r"D:\saida\foto.jpg", "2026-09-05T10:01:00+00:00",
           file_hash="a" * 64, identificador=2),
    evento(ACTION_VERIFY_OK, r"D:\saida\foto.jpg", "2026-09-05T10:01:01+00:00",
           file_hash="a" * 64, identificador=3),
    evento(ACTION_RECOVER, r"D:\saida\nota.txt", "2026-09-05T10:02:00+00:00",
           file_hash="b" * 64, identificador=4),
    evento(ACTION_VERIFY_FAILED, r"D:\saida\nota.txt", "2026-09-05T10:02:01+00:00",
           file_hash="b" * 64, identificador=5),
]


@unittest.skipIf(report is None, "reportlab nao esta instalado")
class SummarizeEventsTest(unittest.TestCase):
    def test_totais(self):
        resumo = report.summarize_events(EVENTOS)
        self.assertEqual(resumo["total_eventos"], 5)
        self.assertEqual(resumo["ficheiros_recuperados"], 2)
        self.assertEqual(resumo["verificados_com_sucesso"], 1)
        self.assertEqual(resumo["verificacoes_falhadas"], 1)
        self.assertEqual(resumo["dispositivos"], [DISPOSITIVO])
        self.assertEqual(resumo["peritos"], ["admin"])
        self.assertEqual(resumo["primeiro_evento"], "2026-09-05T10:00:00+00:00")
        self.assertEqual(resumo["ultimo_evento"], "2026-09-05T10:02:01+00:00")

    def test_ficheiro_recuperado_duas_vezes_conta_uma(self):
        eventos = [
            evento(ACTION_RECOVER, r"D:\saida\foto.jpg"),
            evento(ACTION_RECOVER, r"D:\saida\foto.jpg"),
        ]
        self.assertEqual(report.summarize_events(eventos)["ficheiros_recuperados"], 1)

    def test_evento_sem_ficheiro_nao_conta(self):
        eventos = [evento(ACTION_RECOVER, None)]
        self.assertEqual(report.summarize_events(eventos)["ficheiros_recuperados"], 0)

    def test_varios_dispositivos(self):
        eventos = [
            evento(ACTION_SCAN, device_path=r"\\.\PhysicalDrive1"),
            evento(ACTION_SCAN, device_path=DISPOSITIVO),
            evento(ACTION_SCAN, device_path=None),
        ]
        self.assertEqual(
            report.summarize_events(eventos)["dispositivos"],
            [r"\\.\PhysicalDrive0", r"\\.\PhysicalDrive1"],
        )

    def test_peritos_intervenientes(self):
        eventos = [
            evento(ACTION_SCAN, app_user="operador"),
            evento(ACTION_RECOVER, r"D:\saida.bin", app_user="admin"),
            evento(ACTION_SCAN, app_user=None),
        ]
        self.assertEqual(
            report.summarize_events(eventos)["peritos"], ["admin", "operador"]
        )

    def test_sem_eventos(self):
        resumo = report.summarize_events([])
        self.assertEqual(resumo["total_eventos"], 0)
        self.assertEqual(resumo["ficheiros_recuperados"], 0)
        self.assertIsNone(resumo["primeiro_evento"])
        self.assertEqual(resumo["dispositivos"], [])
        self.assertEqual(resumo["peritos"], [])


@unittest.skipIf(report is None, "reportlab nao esta instalado")
class GenerateReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _gerar(self, eventos, nome="relatorio.pdf"):
        caminho = os.path.join(self.tmp, nome)
        report.generate_report(eventos, caminho)
        return caminho

    def _cabecalho(self, caminho):
        with open(caminho, "rb") as handle:
            return handle.read(5)

    def test_gera_pdf(self):
        caminho = self._gerar(EVENTOS)
        self.assertTrue(os.path.isfile(caminho))
        self.assertEqual(self._cabecalho(caminho), b"%PDF-")
        self.assertGreater(os.path.getsize(caminho), 1000)

    def test_gera_pdf_sem_eventos(self):
        caminho = self._gerar([], "vazio.pdf")
        self.assertEqual(self._cabecalho(caminho), b"%PDF-")

    def test_cria_pasta_de_destino(self):
        caminho = os.path.join(self.tmp, "nova", "pasta", "relatorio.pdf")
        report.generate_report(EVENTOS, caminho)
        self.assertTrue(os.path.isfile(caminho))

    def test_muitos_eventos_geram_varias_paginas(self):
        eventos = [
            evento(ACTION_RECOVER, r"D:\saida\ficheiro_%d.bin" % i,
                   file_hash="%064x" % i, identificador=i)
            for i in range(300)
        ]
        caminho = self._gerar(eventos, "grande.pdf")
        with open(caminho, "rb") as handle:
            conteudo = handle.read()
        self.assertEqual(conteudo[:5], b"%PDF-")
        self.assertGreater(conteudo.count(b"/Page"), 3)

    def test_campos_nulos_e_acentos(self):
        eventos = [
            {"id": 1, "timestamp": None, "device_path": None, "action": ACTION_SCAN,
             "file_path": None, "file_hash": None, "os_user": None, "app_user": None},
            evento(ACTION_RECOVER, "D:/saida/relatório único (cópia).docx",
                   file_hash="c" * 64, os_user="perícia"),
        ]
        caminho = self._gerar(eventos, "acentos.pdf")
        self.assertEqual(self._cabecalho(caminho), b"%PDF-")

    def test_sobrescreve_relatorio_existente(self):
        caminho = self._gerar(EVENTOS)
        tamanho_inicial = os.path.getsize(caminho)
        report.generate_report(EVENTOS[:1], caminho)
        self.assertNotEqual(os.path.getsize(caminho), tamanho_inicial)


if __name__ == "__main__":
    unittest.main()
