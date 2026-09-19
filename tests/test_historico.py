"""Testes de src/historico.py: registo das operacoes de recuperacao."""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from src.historico import (
    BASE_EM_MEMORIA,
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
    OPERACAO_ANALISADA,
    OPERACAO_RECUPERADA,
    VERSAO_DO_JSON,
    Historico,
)

DISPOSITIVO = r"\\.\PhysicalDrive0"


class HistoricoBase(unittest.TestCase):
    """Historico em disco numa pasta temporaria, com uma operacao de exemplo."""

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


class OperacoesTest(HistoricoBase):
    """Historico das operacoes de recuperacao, que alimenta o relatorio."""

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

    def test_estado_por_omissao_distingue_analise_de_recuperacao(self):
        so_analise = self.log.log_operation(
            metodo=METODO_METADADOS, device_path=DISPOSITIVO, encontrados=7
        )
        com_recuperacao = self._registar()

        self.assertEqual(self.log.get_operations(so_analise)[0]["estado"],
                         OPERACAO_ANALISADA)
        self.assertEqual(self.log.get_operations(com_recuperacao)[0]["estado"],
                         OPERACAO_RECUPERADA)


class ActualizacaoTest(HistoricoBase):
    """A analise fica registada e e completada quando ha recuperacao."""

    def test_completa_a_operacao_em_vez_de_criar_outra(self):
        identificador = self.log.log_operation(
            metodo=METODO_METADADOS, device_path=DISPOSITIVO, encontrados=92
        )

        self.log.update_operation(
            identificador, ficheiros=self._ficheiros(),
            estado=OPERACAO_RECUPERADA, pasta_destino=r"D:\Recuperados",
            seleccionados=2, recuperados=1, nao_recuperados=1,
        )

        operacoes = self.log.get_operations()
        self.assertEqual(len(operacoes), 1)
        self.assertEqual(operacoes[0]["estado"], OPERACAO_RECUPERADA)
        self.assertEqual(operacoes[0]["encontrados"], 92)  # vem da analise
        self.assertEqual(operacoes[0]["recuperados"], 1)
        self.assertEqual(operacoes[0]["pasta_destino"], r"D:\Recuperados")
        self.assertEqual(len(self.log.get_operation_files(identificador)), 2)

    def test_os_ficheiros_indicados_substituem_os_guardados(self):
        identificador = self._registar()

        self.log.update_operation(
            identificador,
            ficheiros=[{"nome": "unico.pdf", "estado": ESTADO_RECUPERADO}],
        )

        self.assertEqual(
            [f["nome"] for f in self.log.get_operation_files(identificador)],
            ["unico.pdf"],
        )

    def test_sem_ficheiros_indicados_os_guardados_ficam(self):
        identificador = self._registar()
        self.log.update_operation(identificador, observacoes="nota nova")

        self.assertEqual(len(self.log.get_operation_files(identificador)), 2)
        self.assertEqual(
            self.log.get_operations(identificador)[0]["observacoes"], "nota nova"
        )

    def test_operacao_inexistente_e_rejeitada(self):
        with self.assertRaises(ValueError):
            self.log.update_operation(99, observacoes="x")

    def test_campo_desconhecido_e_rejeitado(self):
        identificador = self._registar()
        with self.assertRaises(ValueError):
            self.log.update_operation(identificador, cadeia_de_custodia="x")


class JsonTest(HistoricoBase):
    """Cada operacao e tambem escrita num JSON legivel fora da ferramenta."""

    def _ler_json(self):
        with open(self.log.json_path, encoding="utf-8") as ficheiro:
            return json.load(ficheiro)

    def test_json_fica_ao_lado_da_base_de_dados(self):
        self.assertEqual(self.log.json_path,
                         os.path.join(self.tmp, "auditoria.json"))

    def test_cada_operacao_e_escrita_no_json(self):
        self._registar()
        dados = self._ler_json()

        self.assertEqual(dados["ferramenta"], "FRDA")
        self.assertEqual(dados["versao"], VERSAO_DO_JSON)
        self.assertEqual(dados["total_de_operacoes"], 1)
        operacao = dados["operacoes"][0]
        self.assertEqual(operacao["device_path"], DISPOSITIVO)
        self.assertEqual(operacao["metodo"], METODO_METADADOS)
        self.assertIn("Recuperacao baseada em metadados", operacao["metodo_nome"])
        self.assertEqual([f["nome"] for f in operacao["ficheiros"]],
                         ["foto.jpg", "nota.txt"])

    def test_a_actualizacao_tambem_reescreve_o_json(self):
        identificador = self.log.log_operation(
            metodo=METODO_CARVING, device_path=DISPOSITIVO, encontrados=3
        )
        self.assertEqual(self._ler_json()["operacoes"][0]["ficheiros"], [])

        self.log.update_operation(
            identificador, ficheiros=[{"nome": "x.jpg", "estado": ESTADO_RECUPERADO}],
            estado=OPERACAO_RECUPERADA,
        )

        operacao = self._ler_json()["operacoes"][0]
        self.assertEqual(operacao["estado"], OPERACAO_RECUPERADA)
        self.assertEqual([f["nome"] for f in operacao["ficheiros"]], ["x.jpg"])

    def test_json_tem_todas_as_operacoes_da_mais_recente_a_mais_antiga(self):
        self._registar()
        self._registar(metodo=METODO_CARVING)

        metodos = [o["metodo"] for o in self._ler_json()["operacoes"]]
        self.assertEqual(metodos, [METODO_CARVING, METODO_METADADOS])

    def test_nao_fica_ficheiro_temporario_por_tras(self):
        self._registar()
        self.assertFalse(os.path.exists(self.log.json_path + ".tmp"))

    def test_base_em_memoria_nao_escreve_ficheiro(self):
        with Historico(BASE_EM_MEMORIA) as memoria:
            self.assertIsNone(memoria.json_path)
            memoria.log_operation(metodo=METODO_METADADOS, encontrados=1)
            self.assertIsNone(memoria.exportar_json())

    def test_falha_a_escrever_o_json_nao_perde_a_operacao(self):
        """A base de dados e o que conta: o JSON e um espelho."""
        # uma pasta no lugar do ficheiro faz a escrita falhar
        os.mkdir(self.log.json_path + ".tmp")

        identificador = self._registar()

        self.assertEqual(len(self.log.get_operations(identificador)), 1)
        self.assertTrue(self.log.erro_do_json)

    def test_json_pode_ser_escrito_noutro_caminho(self):
        self._registar()
        destino = os.path.join(self.tmp, "exportado.json")

        self.assertEqual(self.log.exportar_json(destino), destino)

        with open(destino, encoding="utf-8") as ficheiro:
            self.assertEqual(json.load(ficheiro)["total_de_operacoes"], 1)


class MigracaoTest(unittest.TestCase):
    """Um historico criado por uma versao anterior continua a abrir."""

    def test_acrescenta_as_colunas_em_falta(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        db_path = os.path.join(tmp, "antigo.db")

        antiga = sqlite3.connect(db_path)
        with antiga:
            antiga.execute(
                "CREATE TABLE operacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "inicio TEXT NOT NULL, metodo TEXT NOT NULL, encontrados INTEGER)"
            )
            antiga.execute(
                "INSERT INTO operacoes (inicio, metodo, encontrados) VALUES (?, ?, ?)",
                ("2026-01-01T00:00:00+00:00", METODO_METADADOS, 4),
            )
        antiga.close()

        with Historico(db_path) as log:
            operacoes = log.get_operations()
            self.assertEqual(len(operacoes), 1)
            self.assertIsNone(operacoes[0]["estado"])
            self.assertEqual(operacoes[0]["encontrados"], 4)
            # e continua a aceitar operacoes novas
            log.log_operation(metodo=METODO_CARVING, encontrados=1)
            self.assertEqual(len(log.get_operations()), 2)


if __name__ == "__main__":
    unittest.main()
