"""Testes de src/historico.py: registo das operacoes de recuperacao."""

import os
import shutil
import sqlite3
import tempfile
import unittest

from src.historico import (
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
    Historico,
)

DISPOSITIVO = r"\\.\PhysicalDrive0"


class OperacoesTest(unittest.TestCase):
    """Historico das operacoes de recuperacao, que alimenta o relatorio."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "auditoria.db")
        self.log = Historico(self.db_path)
        self.addCleanup(self.log.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _ficheiros(self):
        return [
            {"nome": "foto.jpg", "tipo": "JPEG", "tamanho": 2048,
             "estado": ESTADO_RECUPERADO, "caminho": r"D:\saida\foto.jpg",
             "file_hash": "a" * 64},
            {"nome": "nota.txt", "tipo": "TXT", "tamanho": 100,
             "estado": ESTADO_FALHADO, "erro": "entrada sem clusters"},
        ]

    def _registar(self, **extra):
        campos = {
            "device_path": DISPOSITIVO,
            "device_type": "Removivel",
            "device_size": 58_300_000_000,
            "filesystem": "exFAT",
            "metodo": METODO_METADADOS,
            "encontrados": 92,
            "seleccionados": 2,
            "pasta_destino": r"D:\Recuperados",
            "app_user": "admin",
        }
        campos.update(extra)
        return self.log.log_operation(ficheiros=self._ficheiros(), **campos)

    def test_regista_a_operacao(self):
        identificador = self._registar()
        operacao = self.log.get_operations(identificador)[0]

        self.assertEqual(operacao["device_path"], DISPOSITIVO)
        self.assertEqual(operacao["metodo"], METODO_METADADOS)
        self.assertEqual(operacao["encontrados"], 92)
        self.assertEqual(operacao["filesystem"], "exFAT")
        self.assertEqual(operacao["pasta_destino"], r"D:\Recuperados")
        self.assertEqual(operacao["app_user"], "admin")
        self.assertTrue(operacao["inicio"])
        self.assertTrue(operacao["os_user"])

    def test_totais_calculados_a_partir_dos_ficheiros(self):
        operacao = self.log.get_operations(self._registar())[0]
        self.assertEqual(operacao["recuperados"], 1)
        self.assertEqual(operacao["nao_recuperados"], 1)

    def test_totais_indicados_sao_respeitados(self):
        operacao = self.log.get_operations(
            self._registar(recuperados=13, nao_recuperados=2, seleccionados=15)
        )[0]
        self.assertEqual(operacao["recuperados"], 13)
        self.assertEqual(operacao["nao_recuperados"], 2)
        self.assertEqual(operacao["seleccionados"], 15)

    def test_ficheiros_processados(self):
        ficheiros = self.log.get_operation_files(self._registar())
        self.assertEqual([f["nome"] for f in ficheiros], ["foto.jpg", "nota.txt"])
        self.assertEqual(ficheiros[0]["estado"], ESTADO_RECUPERADO)
        self.assertEqual(ficheiros[0]["file_hash"], "a" * 64)
        self.assertEqual(ficheiros[1]["erro"], "entrada sem clusters")

    def test_operacao_sem_ficheiros(self):
        identificador = self.log.log_operation(
            metodo=METODO_CARVING, device_path=DISPOSITIVO, encontrados=0
        )
        operacao = self.log.get_operations(identificador)[0]
        self.assertEqual(operacao["recuperados"], 0)
        self.assertEqual(self.log.get_operation_files(identificador), [])

    def test_metodo_obrigatorio_e_validado(self):
        with self.assertRaises(ValueError):
            self.log.log_operation(device_path=DISPOSITIVO)
        with self.assertRaises(ValueError):
            self.log.log_operation(metodo="adivinhacao")

    def test_campo_desconhecido_e_rejeitado(self):
        with self.assertRaises(ValueError):
            self.log.log_operation(metodo=METODO_CARVING, cor_preferida="azul")

    def test_historico_da_mais_recente_para_a_mais_antiga(self):
        primeira = self._registar()
        segunda = self._registar(metodo=METODO_CARVING)
        historico = self.log.get_operations()
        self.assertEqual([o["id"] for o in historico], [segunda, primeira])

    def test_ficheiros_de_operacoes_diferentes_nao_se_misturam(self):
        primeira = self._registar()
        segunda = self.log.log_operation(
            metodo=METODO_CARVING, device_path=DISPOSITIVO,
            ficheiros=[{"nome": "outro.pdf", "estado": ESTADO_RECUPERADO}],
        )
        self.assertEqual(len(self.log.get_operation_files(primeira)), 2)
        self.assertEqual(
            [f["nome"] for f in self.log.get_operation_files(segunda)], ["outro.pdf"]
        )

    def test_persistencia_entre_sessoes(self):
        identificador = self._registar()
        self.log.close()
        with Historico(self.db_path) as nova:
            self.assertEqual(len(nova.get_operations(identificador)), 1)
            self.assertEqual(len(nova.get_operation_files(identificador)), 2)


if __name__ == "__main__":
    unittest.main()
