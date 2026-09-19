"""Testes da janela principal: fluxo, permissoes e orquestracao dos modulos.

Qt corre em modo offscreen e todo o acesso a hardware esta substituido por
mocks. Os trabalhos em segundo plano sao trocados por substitutos sincronos,
que emitem os mesmos sinais sem criar linhas de execucao.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from src.gui import main_window
    from src.gui.widgets import AGUARDANDO, CONCLUIDO, EM_ANALISE, ERRO
except ImportError:  # pragma: no cover - depende do ambiente
    main_window = None

from src import auth
from src.audit_log import (
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
    AuditLog,
)
from src.auth import ROLE_ADMIN, ROLE_OPERATOR, AuthStore

DISCOS = [
    {"index": 0, "path": r"\\.\PhysicalDrive0", "size_bytes": 500107862016},
    {"index": 1, "path": r"\\.\PhysicalDrive1", "size_bytes": 128035676160},
]
VOLUMES = [
    {"letter": "D", "root": "D:\\", "path": r"\\.\D:", "label": "Dados",
     "filesystem": "NTFS", "size_bytes": 500_000_000_000, "free_bytes": 195_000_000_000,
     "drive_type": "Fixo", "disk_index": 0},
]

ADMIN = {"id": 1, "username": "admin", "role": ROLE_ADMIN}
OPERADOR = {"id": 2, "username": "operador", "role": ROLE_OPERATOR}

ENTRADAS = [
    {"nome": "relatorio.docx", "name": "relatorio.docx", "tipo": "DOCX",
     "tamanho": 15000, "size": 15000, "path": "/Documentos/relatorio.docx",
     "metodo": METODO_METADADOS, "runs": [{"block": 100, "count": 4}]},
    {"nome": "foto.jpg", "name": "foto.jpg", "tipo": "JPG", "tamanho": 4096,
     "size": 4096, "path": "/Imagens/foto.jpg", "metodo": METODO_METADADOS,
     "runs": [{"block": 300, "count": 1}]},
]

DIAGNOSTICO = {
    "metodo": METODO_METADADOS,
    "particoes": 1,
    "sistemas_de_ficheiros": 1,
    "tipos": ["NTFS"],
    "registos_examinados": 5000,
}

DISPOSITIVO = r"\\.\PhysicalDrive0"


def resultado(nome="relatorio.docx", estado=ESTADO_RECUPERADO, erro=None):
    return {
        "nome": nome,
        "tipo": "DOCX",
        "tamanho": 15000,
        "estado": estado,
        "caminho": r"D:\Recuperados\%s" % nome if estado == ESTADO_RECUPERADO else None,
        "file_hash": "a" * 64 if estado == ESTADO_RECUPERADO else None,
        "erro": erro,
    }


def fabrica_de_analise(entradas=(), diagnostico=None, erro=None, progresso=(50, 100)):
    """Substituto sincrono de TrabalhoDeAnalise, com resultado pre-definido."""

    class AnaliseFalsa(QObject):
        progresso_sinal = Signal(int, int)
        concluido = Signal(list, dict)
        falhou = Signal(str)

        def __init__(self, device_path, metodo, parent=None):
            super().__init__()
            self.device_path = device_path
            self.metodo = metodo
            AnaliseFalsa.ultima = self

        def isRunning(self):  # noqa: N802 (nome imposto pelo Qt)
            return False

        def start(self):
            if progresso:
                self.progresso_sinal.emit(*progresso)
            if erro is not None:
                self.falhou.emit(erro)
            else:
                self.concluido.emit(list(entradas), dict(diagnostico or DIAGNOSTICO))

    AnaliseFalsa.progresso = AnaliseFalsa.progresso_sinal
    return AnaliseFalsa


def fabrica_de_recuperacao(resultados=(), erro=None):
    """Substituto sincrono de TrabalhoDeRecuperacao."""

    class RecuperacaoFalsa(QObject):
        progresso_sinal = Signal(int, int)
        concluido = Signal(list)
        falhou = Signal(str)

        def __init__(self, device_path, entradas, destino, parent=None):
            super().__init__()
            self.device_path = device_path
            self.entradas = list(entradas)
            self.destino = destino
            RecuperacaoFalsa.ultima = self

        def isRunning(self):  # noqa: N802 (nome imposto pelo Qt)
            return False

        def start(self):
            self.progresso_sinal.emit(1, max(1, len(self.entradas)))
            if erro is not None:
                self.falhou.emit(erro)
            else:
                self.concluido.emit([dict(r) for r in resultados])

    RecuperacaoFalsa.progresso = RecuperacaoFalsa.progresso_sinal
    return RecuperacaoFalsa


@unittest.skipIf(main_window is None, "PySide6 nao esta instalado")
class JanelaBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = AuditLog(":memory:")
        patcher = mock.patch.object(auth, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.auth_store = AuthStore(":memory:")
        self.auth_store.ensure_default_accounts()
        self._patch("device_reader.is_admin", return_value=False)
        self._patch("operacao.validar_destino")
        for nome, valor in (("list_physical_drives", DISCOS),
                            ("list_logical_volumes", VOLUMES)):
            patcher = mock.patch(
                "src.gui.pages.devices.device_reader." + nome, return_value=list(valor)
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def _patch(self, alvo, **kwargs):
        patcher = mock.patch("src.gui.main_window." + alvo, **kwargs)
        substituto = patcher.start()
        self.addCleanup(patcher.stop)
        return substituto

    def _janela(self, user=ADMIN):
        janela = main_window.MainWindow(
            user=user, audit_log=self.log, auth_store=self.auth_store
        )
        self.addCleanup(janela.close)
        return janela

    def _com_analise(self, janela, entradas=ENTRADAS, diagnostico=None, erro=None):
        self._patch("TrabalhoDeAnalise",
                    new=fabrica_de_analise(entradas, diagnostico, erro))
        return janela

    def _com_recuperacao(self, resultados=(), erro=None):
        self._patch("TrabalhoDeRecuperacao",
                    new=fabrica_de_recuperacao(resultados, erro))

    def _janela_analisada(self, user=ADMIN, entradas=ENTRADAS, metodo=METODO_METADADOS):
        """Janela com um disco seleccionado e a analise ja concluida."""
        janela = self._com_analise(self._janela(user), entradas)
        cartao = self._cartao(janela, "disco", 0)
        cartao.escolhido.emit(cartao.dados)
        janela.devices_page.definir_metodo(metodo)
        janela.devices_page.painel.botao_accao.click()
        return janela

    def _cartao(self, janela, tipo, indice=0):
        cartoes = [c for c in janela.devices_page.cartoes if c.dados["tipo"] == tipo]
        return cartoes[indice]

    def _accoes(self):
        return [evento["action"] for evento in self.log.get_events()]


class SessaoTest(JanelaBase):
    def test_arranca_no_painel_de_login(self):
        janela = self._janela(user=None)
        self.assertIs(janela.janela.currentWidget(), janela.login_page)

    def test_login_abre_a_aplicacao_na_mesma_janela(self):
        janela = self._janela(user=None)
        janela.login_page.campo_utilizador.setText("admin")
        janela.login_page.campo_password.setText("admin123")

        janela.login_page.botao_entrar.click()

        self.assertIsNot(janela.janela.currentWidget(), janela.login_page)
        self.assertEqual(janela.painel_actual(), "dispositivos")
        self.assertEqual(janela.estado.estado, AGUARDANDO)

    def test_terminar_sessao_limpa_a_operacao(self):
        janela = self._janela_analisada()

        janela.botao_terminar_sessao.click()

        self.assertIs(janela.janela.currentWidget(), janela.login_page)
        self.assertEqual(janela.results_page.tabela.rowCount(), 0)
        self.assertEqual(janela.summary_page.tabela.rowCount(), 0)
        self.assertEqual(janela.estado.estado, AGUARDANDO)


class NavegacaoTest(JanelaBase):
    def test_barra_lateral_segue_o_fluxo(self):
        janela = self._janela(ADMIN)
        rotulos = [janela.menu.item(i).text() for i in range(janela.menu.count())]
        self.assertEqual(
            rotulos,
            [
                "Recuperacao de dados",
                "1. Dispositivo e metodo",
                "2. Ficheiros encontrados",
                "3. Resultados",
                "Ferramentas",
                "Cadeia de custodia",
                "Contas de acesso",
            ],
        )

    def test_nao_ha_painel_de_carving_independente(self):
        janela = self._janela(ADMIN)
        self.assertNotIn("carving", janela.paineis)
        self.assertFalse(hasattr(janela, "carving_page"))

    def test_clique_no_menu_muda_de_painel(self):
        janela = self._janela(ADMIN)
        janela.menu.setCurrentItem(janela.itens_do_menu["resumo"])
        self.assertEqual(janela.painel_actual(), "resumo")

    def test_painel_de_auditoria_carrega_os_eventos(self):
        janela = self._janela_analisada()
        janela.ir_para("auditoria")
        self.assertEqual(janela.audit_page.tabela.rowCount(), 1)


class PermissoesTest(JanelaBase):
    def test_operador_nao_ve_auditoria_nem_contas(self):
        janela = self._janela(OPERADOR)
        self.assertFalse(janela.itens_do_menu["dispositivos"].isHidden())
        self.assertFalse(janela.itens_do_menu["resumo"].isHidden())
        self.assertTrue(janela.itens_do_menu["auditoria"].isHidden())
        self.assertTrue(janela.itens_do_menu["contas"].isHidden())

    def test_sem_sessao_nao_varre(self):
        janela = self._janela(user=None)
        analise = self._patch("TrabalhoDeAnalise")
        janela.varrer(DISPOSITIVO)
        analise.assert_not_called()

    def test_operador_nao_gera_relatorio_da_cadeia(self):
        janela = self._janela_analisada(user=OPERADOR)
        gerar = self._patch("report.generate_report")

        janela.gerar_relatorio()

        gerar.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "erro")


class AnaliseTest(JanelaBase):
    def test_analise_arranca_com_o_metodo_escolhido(self):
        janela = self._com_analise(self._janela(ADMIN))
        cartao = self._cartao(janela, "disco", 1)
        cartao.escolhido.emit(cartao.dados)
        janela.devices_page.definir_metodo(METODO_CARVING)

        janela.devices_page.painel.botao_accao.click()

        trabalho = main_window.TrabalhoDeAnalise.ultima
        self.assertEqual(trabalho.device_path, r"\\.\PhysicalDrive1")
        self.assertEqual(trabalho.metodo, METODO_CARVING)

    def test_resultados_aparecem_e_o_estado_fica_concluido(self):
        janela = self._janela_analisada()

        self.assertEqual(janela.painel_actual(), "resultados")
        self.assertEqual(janela.results_page.tabela.rowCount(), 2)
        self.assertEqual(janela.estado.estado, CONCLUIDO)
        self.assertIn("2 ficheiros encontrados", janela.estado.detalhe.text())
        self.assertEqual(janela.banner.property("tipo"), "sucesso")

    def test_progresso_chega_a_barra(self):
        janela = self._janela_analisada()
        self.assertEqual(janela.estado.percentagem(), 100)  # concluido

    def test_varrimento_regista_o_evento(self):
        self._janela_analisada()
        eventos = self.log.get_events()
        self.assertEqual([e["action"] for e in eventos], ["scan"])
        self.assertEqual(eventos[0]["app_user"], "admin")

    def test_analise_falhada_mostra_o_erro(self):
        janela = self._com_analise(self._janela(ADMIN), erro="Acesso negado a X")
        janela.varrer(DISPOSITIVO)

        self.assertEqual(janela.estado.estado, ERRO)
        self.assertEqual(janela.banner.property("tipo"), "erro")
        self.assertTrue(janela.botao_elevar.isVisibleTo(janela))
        self.assertEqual(self.log.get_events(), [])

    def test_sem_resultados_explica_o_que_foi_analisado(self):
        janela = self._com_analise(self._janela(ADMIN), entradas=[])
        janela.varrer(DISPOSITIVO)

        self.assertEqual(janela.banner.property("tipo"), "info")
        self.assertIn("5000 registos", janela.banner.text())

    def test_sem_resultados_no_carving(self):
        janela = self._com_analise(
            self._janela(ADMIN), entradas=[],
            diagnostico={"metodo": METODO_CARVING, "tipos": ["jpeg", "pdf"]},
        )
        janela.varrer(DISPOSITIVO, METODO_CARVING)

        self.assertIn("Nenhuma assinatura", janela.banner.text())
        self.assertIn("jpeg, pdf", janela.banner.text())

    def test_sem_dispositivo(self):
        janela = self._com_analise(self._janela(ADMIN))
        analise = self._patch("TrabalhoDeAnalise")
        janela.varrer("")
        analise.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")


class RecuperacaoTest(JanelaBase):
    def test_recupera_e_regista_a_operacao(self):
        janela = self._janela_analisada()
        self._com_recuperacao([resultado(), resultado("foto.jpg", ESTADO_FALHADO,
                                                      "entrada sem clusters")])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectAll()

        janela.results_page.painel.botao_accao.click()

        # operacao guardada no historico
        operacoes = self.log.get_operations()
        self.assertEqual(len(operacoes), 1)
        operacao = operacoes[0]
        self.assertEqual(operacao["metodo"], METODO_METADADOS)
        self.assertEqual(operacao["device_path"], DISPOSITIVO)
        self.assertEqual(operacao["encontrados"], 2)
        self.assertEqual(operacao["seleccionados"], 2)
        self.assertEqual(operacao["recuperados"], 1)
        self.assertEqual(operacao["nao_recuperados"], 1)
        self.assertEqual(operacao["pasta_destino"], self.tmp)
        self.assertEqual(operacao["app_user"], "admin")
        self.assertIn("entrada sem clusters", operacao["observacoes"])
        self.assertEqual(operacao["device_type"], "Disco fisico")

        # ficheiros processados guardados
        ficheiros = self.log.get_operation_files(operacao["id"])
        self.assertEqual([f["nome"] for f in ficheiros], ["relatorio.docx", "foto.jpg"])

    def test_resultados_aparecem_nos_cartoes(self):
        janela = self._janela_analisada()
        self._com_recuperacao([resultado(), resultado("foto.jpg", ESTADO_FALHADO)])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectAll()

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(janela.painel_actual(), "resumo")
        self.assertEqual(janela.summary_page.cartoes["encontrados"].valor(), "2")
        self.assertEqual(janela.summary_page.cartoes["recuperados"].valor(), "1")
        self.assertEqual(janela.summary_page.cartoes["nao_recuperados"].valor(), "1")
        self.assertEqual(janela.summary_page.tabela.rowCount(), 2)
        self.assertEqual(janela.estado.estado, CONCLUIDO)

    def test_eventos_de_auditoria_por_ficheiro(self):
        janela = self._janela_analisada()
        self._com_recuperacao([resultado(), resultado("foto.jpg", ESTADO_FALHADO)])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectAll()

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(
            self._accoes(),
            ["scan", "recover", "verify_ok", "recover", "verify_falhou"],
        )

    def test_carving_regista_a_accao_propria(self):
        janela = self._janela_analisada(metodo=METODO_CARVING)
        self._com_recuperacao([resultado()])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(self._accoes(), ["scan", "carving", "verify_ok"])
        self.assertEqual(self.log.get_operations()[0]["metodo"], METODO_CARVING)

    def test_destino_no_dispositivo_analisado_e_recusado(self):
        janela = self._janela_analisada()
        recuperacao = self._patch("TrabalhoDeRecuperacao")
        self._patch("MainWindow.escolher_pasta", return_value=r"D:\Recuperados")
        self._patch("operacao.validar_destino",
                    side_effect=ValueError("destroi a prova"))
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        recuperacao.assert_not_called()
        self.assertEqual(janela.estado.estado, ERRO)
        self.assertIn("destroi a prova", janela.banner.text())
        self.assertEqual(self.log.get_operations(), [])

    def test_escolha_de_pasta_cancelada(self):
        janela = self._janela_analisada()
        recuperacao = self._patch("TrabalhoDeRecuperacao")
        self._patch("MainWindow.escolher_pasta", return_value="")
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        recuperacao.assert_not_called()
        self.assertEqual(self.log.get_operations(), [])

    def test_sem_seleccao(self):
        janela = self._janela_analisada()
        escolher = self._patch("MainWindow.escolher_pasta")
        janela.recuperar([])
        escolher.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")

    def test_recuperacao_falhada(self):
        janela = self._janela_analisada()
        self._com_recuperacao(erro="disco desligado")
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(janela.estado.estado, ERRO)
        self.assertIn("disco desligado", janela.banner.text())
        self.assertEqual(self.log.get_operations(), [])


class RelatorioDaOperacaoTest(JanelaBase):
    def _operacao_concluida(self):
        janela = self._janela_analisada()
        self._com_recuperacao([resultado()])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)
        janela.results_page.painel.botao_accao.click()
        return janela

    def test_gera_o_relatorio_da_operacao(self):
        janela = self._operacao_concluida()
        destino = os.path.join(self.tmp, "op.pdf")
        gerar = self._patch("report.generate_operation_report")
        self._patch("MainWindow.escolher_ficheiro_de_destino", return_value=destino)
        abrir = self._patch("os.startfile", create=True)

        janela.summary_page.painel.botao_accao.click()

        gerar.assert_called_once()
        operacao_passada, ficheiros, caminho = gerar.call_args[0]
        self.assertEqual(caminho, destino)
        self.assertEqual(operacao_passada["metodo"], METODO_METADADOS)
        self.assertEqual([f["nome"] for f in ficheiros], ["relatorio.docx"])
        abrir.assert_called_once_with(destino)
        self.assertIn("report", self._accoes())

    def test_sem_operacao_nao_ha_relatorio(self):
        janela = self._janela(ADMIN)
        gerar = self._patch("report.generate_operation_report")

        janela.gerar_relatorio_da_operacao()

        gerar.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")

    def test_relatorio_cancelado(self):
        janela = self._operacao_concluida()
        gerar = self._patch("report.generate_operation_report")
        self._patch("MainWindow.escolher_ficheiro_de_destino", return_value="")

        janela.summary_page.painel.botao_accao.click()

        gerar.assert_not_called()

    def test_relatorio_falhado(self):
        janela = self._operacao_concluida()
        self._patch("report.generate_operation_report",
                    side_effect=IOError("disco cheio"))
        self._patch("MainWindow.escolher_ficheiro_de_destino",
                    return_value=os.path.join(self.tmp, "op.pdf"))
        abrir = self._patch("os.startfile", create=True)

        janela.summary_page.painel.botao_accao.click()

        self.assertEqual(janela.banner.property("tipo"), "erro")
        abrir.assert_not_called()


class HistoricoTest(JanelaBase):
    def _com_operacao(self):
        janela = self._janela_analisada()
        self._com_recuperacao([resultado()])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)
        janela.results_page.painel.botao_accao.click()
        return janela

    def test_painel_mostra_o_historico(self):
        janela = self._com_operacao()
        janela.ir_para("auditoria")
        self.assertEqual(janela.audit_page.tabela_de_operacoes.rowCount(), 1)

    def test_relatorio_de_operacao_antiga(self):
        janela = self._com_operacao()
        janela.ir_para("auditoria")
        gerar = self._patch("report.generate_operation_report")
        self._patch("MainWindow.escolher_ficheiro_de_destino",
                    return_value=os.path.join(self.tmp, "antiga.pdf"))
        self._patch("os.startfile", create=True)

        janela.audit_page.tabela_de_operacoes.selectRow(0)
        janela.audit_page.botao_relatorio_da_operacao.click()

        gerar.assert_called_once()
        operacao_passada, ficheiros, _caminho = gerar.call_args[0]
        self.assertEqual(operacao_passada["id"], 1)
        self.assertEqual([f["nome"] for f in ficheiros], ["relatorio.docx"])

    def test_operacao_inexistente(self):
        janela = self._janela(ADMIN)
        gerar = self._patch("report.generate_operation_report")

        janela.gerar_relatorio_de_operacao_antiga(99)

        gerar.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")


class ElevacaoTest(JanelaBase):
    def test_botao_visivel_sem_privilegios(self):
        janela = self._janela(ADMIN)
        self.assertTrue(janela.botao_elevar.isVisibleTo(janela))

    def test_botao_escondido_com_privilegios(self):
        self._patch("device_reader.is_admin", return_value=True)
        janela = self._janela(ADMIN)
        self.assertFalse(janela.botao_elevar.isVisibleTo(janela))

    def test_clique_relanca_a_aplicacao(self):
        janela = self._janela(ADMIN)
        relancar = self._patch("device_reader.relaunch_as_admin", return_value=True)
        sair = self._patch("QApplication.quit")

        janela.botao_elevar.click()

        relancar.assert_called_once_with()
        sair.assert_called_once_with()

    def test_elevacao_recusada(self):
        janela = self._janela(ADMIN)
        self._patch("device_reader.relaunch_as_admin", return_value=False)
        sair = self._patch("QApplication.quit")

        janela.botao_elevar.click()

        sair.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")


class ArranqueTest(JanelaBase):
    """A elevacao e pedida no arranque, antes de existir qualquer janela."""

    def _patch_arranque(self):
        aplicacao = self._patch("QApplication")
        aplicacao.return_value.exec.return_value = 0
        self._patch("AuthStore")
        self._patch("MainWindow")
        return aplicacao

    def test_pede_elevacao_antes_de_abrir_a_janela(self):
        relancar = self._patch("device_reader.relaunch_as_admin", return_value=True)
        aplicacao = self._patch_arranque()

        self.assertEqual(main_window.main([]), 0)

        relancar.assert_called_once_with()
        aplicacao.assert_not_called()

    def test_abre_em_modo_limitado_se_a_elevacao_for_recusada(self):
        self._patch("device_reader.relaunch_as_admin", return_value=False)
        aplicacao = self._patch_arranque()

        main_window.main([])

        aplicacao.assert_called_once()

    def test_argumento_salta_o_pedido_de_elevacao(self):
        relancar = self._patch("device_reader.relaunch_as_admin")
        self._patch_arranque()

        main_window.main([main_window.ARGUMENTO_SEM_ELEVACAO])

        relancar.assert_not_called()


class ImagemDeDiscoTest(JanelaBase):
    def test_escolher_imagem(self):
        janela = self._janela(ADMIN)
        caminho = os.path.join(self.tmp, "caso1.dd")
        self._patch("QFileDialog.getOpenFileName", return_value=(caminho, ""))

        janela.escolher_imagem()

        self.assertEqual(janela.devices_page.dispositivo_selecionado(), caminho)

    def test_analisar_a_imagem_escolhida(self):
        janela = self._com_analise(self._janela(ADMIN), entradas=[])
        caminho = os.path.join(self.tmp, "caso1.dd")
        self._patch("QFileDialog.getOpenFileName", return_value=(caminho, ""))

        janela.escolher_imagem()
        janela.devices_page.painel.botao_accao.click()

        self.assertEqual(main_window.TrabalhoDeAnalise.ultima.device_path, caminho)


class EstadoTest(JanelaBase):
    def test_aviso_de_privilegios(self):
        janela = self._janela(ADMIN)
        self.assertEqual(janela.etiqueta_privilegios.text(), main_window.AVISO_ADMIN)

    def test_notificar_actualiza_banner_e_barra_de_estado(self):
        janela = self._janela(ADMIN)
        janela.notificar("tudo certo", "sucesso")
        self.assertEqual(janela.banner.text(), "tudo certo")
        self.assertEqual(janela.statusBar().currentMessage(), "tudo certo")

    def test_conta_criada_notifica(self):
        janela = self._janela(ADMIN)
        janela.ir_para("contas")
        janela.accounts_page.campo_utilizador.setText("perito3")
        janela.accounts_page.campo_password.setText("pass")
        janela.accounts_page.campo_confirmacao.setText("pass")

        janela.accounts_page.botao_criar.click()

        self.assertIn("perito3", janela.banner.text())


if __name__ == "__main__":
    unittest.main()
