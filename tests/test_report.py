"""Testes de src/report.py: relatorio da operacao de recuperacao."""

import os
import shutil
import tempfile
import unittest

try:
    from src import report
except ImportError:  # pragma: no cover - depende do ambiente
    report = None

DISPOSITIVO = r"\\.\PhysicalDrive0"


@unittest.skipIf(report is None, "reportlab nao esta instalado")
class RelatorioDaOperacaoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.operacao = {
            "id": 7,
            "inicio": "2026-09-19T10:00:00+00:00",
            "fim": "2026-09-19T10:04:00+00:00",
            "device_path": DISPOSITIVO,
            "device_type": "Removivel",
            "device_size": 58_300_000_000,
            "filesystem": "exFAT",
            "metodo": "metadados",
            "estado": "recuperada",
            "encontrados": 92,
            "seleccionados": 15,
            "recuperados": 13,
            "nao_recuperados": 2,
            "pasta_destino": r"D:\Recuperados",
            "app_user": "admin",
            "os_user": "mambo",
        }
        self.ficheiros = [
            {"nome": "foto.jpg", "tipo": "JPEG", "tamanho": 2_458_112,
             "estado": "recuperado", "caminho": r"D:\Recuperados\foto.jpg"},
            {"nome": "nota.txt", "tipo": "TXT", "tamanho": 100,
             "estado": "nao recuperado", "erro": "entrada sem clusters"},
        ]

    def _gerar(self, operacao=None, ficheiros=None, nome="operacao.pdf"):
        caminho = os.path.join(self.tmp, nome)
        report.generate_operation_report(
            self.operacao if operacao is None else operacao,
            self.ficheiros if ficheiros is None else ficheiros,
            caminho,
        )
        return caminho

    def test_gera_pdf(self):
        caminho = self._gerar()
        with open(caminho, "rb") as ficheiro:
            self.assertEqual(ficheiro.read(5), b"%PDF-")
        self.assertGreater(os.path.getsize(caminho), 1000)

    def test_identificacao_tem_todos_os_campos_pedidos(self):
        rotulos = [r for r, _ in report._identificacao_da_operacao(self.operacao)]
        for esperado in ("Identificacao da operacao", "Inicio", "Dispositivo analisado",
                         "Tipo de dispositivo", "Capacidade", "Sistema de ficheiros",
                         "Metodo utilizado", "Estado da operacao",
                         "Ficheiros encontrados",
                         "Ficheiros seleccionados", "Ficheiros recuperados",
                         "Ficheiros nao recuperados", "Pasta de destino",
                         "Observacoes"):
            self.assertIn(esperado, rotulos)

    def test_metodo_aparece_por_extenso(self):
        valores = dict(report._identificacao_da_operacao(self.operacao))
        self.assertEqual(
            valores["Metodo utilizado"], "Recuperacao baseada em metadados"
        )

    def test_estado_aparece_por_extenso(self):
        valores = dict(report._identificacao_da_operacao(self.operacao))
        self.assertEqual(valores["Estado da operacao"], "Recuperacao")

    def test_operacao_antiga_sem_estado(self):
        operacao = dict(self.operacao)
        del operacao["estado"]
        valores = dict(report._identificacao_da_operacao(operacao))
        self.assertEqual(valores["Estado da operacao"], "-")

    def test_sistema_de_ficheiros_por_identificar(self):
        operacao = dict(self.operacao, filesystem=None)
        valores = dict(report._identificacao_da_operacao(operacao))
        self.assertEqual(valores["Sistema de ficheiros"], "nao identificado")

    def test_capacidade_legivel(self):
        valores = dict(report._identificacao_da_operacao(self.operacao))
        self.assertEqual(valores["Capacidade"], "54.3 GB")

    def test_operacao_sem_ficheiros(self):
        caminho = self._gerar(ficheiros=[], nome="vazia.pdf")
        with open(caminho, "rb") as ficheiro:
            self.assertEqual(ficheiro.read(5), b"%PDF-")

    def test_muitos_ficheiros_geram_varias_paginas(self):
        ficheiros = [
            {"nome": "ficheiro_%d.bin" % i, "tipo": "BIN", "tamanho": i * 1000,
             "estado": "recuperado"}
            for i in range(300)
        ]
        caminho = self._gerar(ficheiros=ficheiros, nome="grande.pdf")
        with open(caminho, "rb") as ficheiro:
            self.assertGreater(ficheiro.read().count(b"/Page"), 3)

    def test_cria_pasta_de_destino(self):
        caminho = os.path.join(self.tmp, "nova", "pasta", "op.pdf")
        report.generate_operation_report(self.operacao, self.ficheiros, caminho)
        self.assertTrue(os.path.isfile(caminho))


if __name__ == "__main__":
    unittest.main()
