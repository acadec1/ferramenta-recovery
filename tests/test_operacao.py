"""Testes de src/operacao.py: analise e recuperacao pelos dois metodos."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import operacao
from src.historico import (
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
)

DISPOSITIVO = r"\\.\PhysicalDrive1"

ENTRADA_DE_METADADOS = {
    "name": "relatorio.docx",
    "path": "/Documentos/relatorio.docx",
    "size": 15000,
    "runs": [{"block": 100, "count": 4}],
}

CANDIDATO_DE_CARVING = {
    "name": "jpeg_00001_offset_4096.jpg",
    "offset": 4096,
    "size": 3009,
    "type": "jpeg",
    "extension": ".jpg",
}


class TipoDoFicheiroTest(unittest.TestCase):
    def test_extensao_em_maiusculas(self):
        self.assertEqual(operacao.tipo_do_ficheiro("foto.jpg"), "JPG")
        self.assertEqual(operacao.tipo_do_ficheiro("relatorio.DOCX"), "DOCX")

    def test_sem_extensao(self):
        self.assertEqual(operacao.tipo_do_ficheiro("registo_42"), "?")
        self.assertEqual(operacao.tipo_do_ficheiro(""), "?")


class AnaliseTest(unittest.TestCase):
    def test_metodo_de_metadados(self):
        def scan(device_path, diagnostico=None, progresso=None, ao_encontrar=None):
            if diagnostico is not None:
                diagnostico.update({"particoes": 1, "sistemas_de_ficheiros": 1})
            return [dict(ENTRADA_DE_METADADOS)]

        with mock.patch.object(operacao.filesystem_parser, "scan_deleted_entries",
                               side_effect=scan):
            entradas, diagnostico = operacao.analisar(DISPOSITIVO, METODO_METADADOS)

        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["nome"], "relatorio.docx")
        self.assertEqual(entradas[0]["tipo"], "DOCX")
        self.assertEqual(entradas[0]["tamanho"], 15000)
        self.assertEqual(entradas[0]["metodo"], METODO_METADADOS)
        self.assertEqual(entradas[0]["runs"], ENTRADA_DE_METADADOS["runs"])
        self.assertEqual(diagnostico["metodo"], METODO_METADADOS)
        self.assertEqual(diagnostico["particoes"], 1)

    def test_metodo_de_carving_percorre_todos_os_tipos(self):
        def procurar(device_path, tipo, progresso=None, ao_encontrar=None):
            return [dict(CANDIDATO_DE_CARVING, type=tipo, name="%s_1.bin" % tipo)]

        with mock.patch.object(operacao.carving, "find_by_signature",
                               side_effect=procurar) as procura:
            entradas, diagnostico = operacao.analisar(DISPOSITIVO, METODO_CARVING)

        tipos = operacao.carving.supported_types()
        self.assertEqual(procura.call_count, len(tipos))
        self.assertEqual(len(entradas), len(tipos))
        self.assertTrue(all(e["metodo"] == METODO_CARVING for e in entradas))
        self.assertEqual(diagnostico["metodo"], METODO_CARVING)
        self.assertEqual(diagnostico["tipos"], tipos)

    def test_progresso_do_carving_soma_os_tipos(self):
        recebidos = []

        def procurar(device_path, tipo, progresso=None, ao_encontrar=None):
            progresso(50, 100)  # metade deste tipo
            return []

        with mock.patch.object(operacao.carving, "find_by_signature",
                               side_effect=procurar):
            operacao.analisar(DISPOSITIVO, METODO_CARVING,
                              lambda feitos, total: recebidos.append((feitos, total)))

        tipos = len(operacao.carving.supported_types())
        self.assertEqual(len(recebidos), tipos)
        self.assertEqual(recebidos[0], (50, 100 * tipos))
        self.assertEqual(recebidos[-1], (100 * (tipos - 1) + 50, 100 * tipos))

    def test_entradas_entregues_durante_a_analise(self):
        """A lista deve preencher-se enquanto a analise decorre."""
        vistas = []

        def scan(device_path, diagnostico=None, progresso=None, ao_encontrar=None):
            for nome in ("a.txt", "b.jpg"):
                ao_encontrar(dict(ENTRADA_DE_METADADOS, name=nome))
            return [dict(ENTRADA_DE_METADADOS, name=n) for n in ("a.txt", "b.jpg")]

        with mock.patch.object(operacao.filesystem_parser, "scan_deleted_entries",
                               side_effect=scan):
            operacao.analisar(DISPOSITIVO, METODO_METADADOS, None, vistas.append)

        self.assertEqual([e["nome"] for e in vistas], ["a.txt", "b.jpg"])
        self.assertEqual(vistas[1]["tipo"], "JPG")  # ja normalizadas
        self.assertEqual(vistas[0]["metodo"], METODO_METADADOS)

    def test_candidatos_de_carving_entregues_durante_a_analise(self):
        vistas = []

        def procurar(device_path, tipo, progresso=None, ao_encontrar=None):
            candidato = dict(CANDIDATO_DE_CARVING, name="%s_1.bin" % tipo)
            ao_encontrar(candidato)
            return [candidato]

        with mock.patch.object(operacao.carving, "find_by_signature",
                               side_effect=procurar):
            operacao.analisar(DISPOSITIVO, METODO_CARVING, None, vistas.append)

        self.assertEqual(len(vistas), len(operacao.carving.supported_types()))
        self.assertTrue(all(e["metodo"] == METODO_CARVING for e in vistas))

    def test_metodo_desconhecido(self):
        with self.assertRaises(ValueError):
            operacao.analisar(DISPOSITIVO, "adivinhacao")


class DestinoTest(unittest.TestCase):
    VOLUMES = [
        {"letter": "C", "path": r"\\.\C:", "disk_index": 1},
        {"letter": "D", "path": r"\\.\D:", "disk_index": 0},
    ]

    def _patch_volumes(self):
        patcher = mock.patch.object(operacao.device_reader, "list_logical_volumes",
                                    return_value=self.VOLUMES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_destino_noutro_disco_e_aceite(self):
        self._patch_volumes()
        operacao.validar_destino(r"\\.\D:", r"C:\Recuperados")

    def test_destino_no_volume_analisado_e_recusado(self):
        self._patch_volumes()
        with self.assertRaises(ValueError) as erro:
            operacao.validar_destino(r"\\.\D:", r"D:\Recuperados")
        self.assertIn("destroi a prova", str(erro.exception))

    def test_destino_noutro_volume_do_mesmo_disco_fisico_e_recusado(self):
        self._patch_volumes()
        with self.assertRaises(ValueError):
            operacao.validar_destino(r"\\.\PhysicalDrive0", r"D:\Recuperados")

    def test_destino_em_disco_diferente_do_fisico_e_aceite(self):
        self._patch_volumes()
        operacao.validar_destino(r"\\.\PhysicalDrive0", r"C:\Recuperados")

    def test_imagem_de_disco_aceita_qualquer_destino(self):
        self._patch_volumes()
        operacao.validar_destino(r"D:\provas\caso1.dd", r"D:\Recuperados")

    def test_destino_vazio(self):
        with self.assertRaises(ValueError):
            operacao.validar_destino(r"\\.\D:", "")


class RecuperacaoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.destino = os.path.join(self.tmp, "saida")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch.object(operacao, "validar_destino")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _escrever(self, conteudo=b"conteudo recuperado"):
        def recuperar(device_path, entrada, destino):
            os.makedirs(destino, exist_ok=True)
            caminho = os.path.join(destino, entrada.get("nome") or entrada["name"])
            with open(caminho, "wb") as ficheiro:
                ficheiro.write(conteudo)
            return caminho

        return recuperar

    def test_recupera_por_metadados(self):
        entrada = dict(ENTRADA_DE_METADADOS, nome="relatorio.docx", tipo="DOCX",
                       tamanho=15000, metodo=METODO_METADADOS)
        with mock.patch.object(operacao.recovery, "recover_file",
                               side_effect=self._escrever()) as recuperar:
            resultados = operacao.recuperar(DISPOSITIVO, [entrada], self.destino)

        recuperar.assert_called_once()
        resultado = resultados[0]
        self.assertEqual(resultado["estado"], ESTADO_RECUPERADO)
        self.assertEqual(resultado["nome"], "relatorio.docx")
        self.assertEqual(resultado["tipo"], "DOCX")
        self.assertEqual(len(resultado["file_hash"]), 64)
        self.assertIsNone(resultado["erro"])

    def test_recupera_por_carving(self):
        entrada = dict(CANDIDATO_DE_CARVING, nome=CANDIDATO_DE_CARVING["name"],
                       tipo="JPG", tamanho=3009, metodo=METODO_CARVING)
        with mock.patch.object(operacao.carving, "extract_candidate",
                               side_effect=self._escrever()) as extrair:
            resultados = operacao.recuperar(DISPOSITIVO, [entrada], self.destino)

        extrair.assert_called_once()
        self.assertEqual(resultados[0]["estado"], ESTADO_RECUPERADO)

    def test_falha_num_ficheiro_nao_interrompe_os_outros(self):
        entradas = [
            dict(ENTRADA_DE_METADADOS, nome="bom.bin", metodo=METODO_METADADOS),
            dict(ENTRADA_DE_METADADOS, nome="mau.bin", metodo=METODO_METADADOS),
        ]
        escrever = self._escrever()

        def recuperar(device_path, entrada, destino):
            if entrada["nome"] == "mau.bin":
                raise ValueError("entrada sem clusters")
            return escrever(device_path, entrada, destino)

        with mock.patch.object(operacao.recovery, "recover_file",
                               side_effect=recuperar):
            resultados = operacao.recuperar(DISPOSITIVO, entradas, self.destino)

        self.assertEqual([r["estado"] for r in resultados],
                         [ESTADO_RECUPERADO, ESTADO_FALHADO])
        self.assertEqual(resultados[1]["erro"], "entrada sem clusters")
        self.assertIsNone(resultados[1]["caminho"])

    def test_integridade_falhada_marca_o_ficheiro(self):
        entrada = dict(ENTRADA_DE_METADADOS, nome="x.bin", metodo=METODO_METADADOS)
        with mock.patch.object(operacao.recovery, "recover_file",
                               side_effect=self._escrever()), \
             mock.patch.object(operacao.integrity, "verify_integrity",
                               return_value=False):
            resultados = operacao.recuperar(DISPOSITIVO, [entrada], self.destino)

        self.assertEqual(resultados[0]["estado"], ESTADO_FALHADO)
        self.assertIn("integridade", resultados[0]["erro"])

    def test_progresso_por_ficheiro(self):
        entradas = [
            dict(ENTRADA_DE_METADADOS, nome="a.bin", metodo=METODO_METADADOS),
            dict(ENTRADA_DE_METADADOS, nome="b.bin", metodo=METODO_METADADOS),
        ]
        recebidos = []
        with mock.patch.object(operacao.recovery, "recover_file",
                               side_effect=self._escrever()):
            operacao.recuperar(DISPOSITIVO, entradas, self.destino,
                               lambda feitos, total: recebidos.append((feitos, total)))

        self.assertEqual(recebidos, [(1, 2), (2, 2)])


class ResumoTest(unittest.TestCase):
    def test_totais(self):
        resultados = [
            {"estado": ESTADO_RECUPERADO},
            {"estado": ESTADO_RECUPERADO},
            {"estado": ESTADO_FALHADO},
        ]
        self.assertEqual(
            operacao.resumo(92, resultados),
            {"encontrados": 92, "seleccionados": 3, "recuperados": 2,
             "nao_recuperados": 1},
        )

    def test_sem_recuperacoes(self):
        self.assertEqual(
            operacao.resumo(10, []),
            {"encontrados": 10, "seleccionados": 0, "recuperados": 0,
             "nao_recuperados": 0},
        )


if __name__ == "__main__":
    unittest.main()
