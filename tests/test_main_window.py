"""Testes da janela principal: navegacao, permissoes e orquestracao dos modulos.

Qt corre em modo offscreen e todo o acesso a hardware esta substituido por
mocks; nenhum dispositivo fisico e tocado.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from src.gui import main_window
except ImportError:  # pragma: no cover - depende do ambiente
    main_window = None

from src import auth
from src.audit_log import AuditLog
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
    {"name": "relatorio.docx", "path": "/Documentos/relatorio.docx", "size": 15000,
     "mtime_iso": "2026-08-14T22:13:20+00:00", "runs": [{"block": 100, "count": 4}]},
    {"name": "foto.jpg", "path": "/Imagens/foto.jpg", "size": 4096,
     "mtime_iso": None, "runs": [{"block": 300, "count": 1}]},
]

DISPOSITIVO = r"\\.\PhysicalDrive0"


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

    def _janela_com_resultados(self, user=ADMIN, entradas=ENTRADAS):
        janela = self._janela(user)
        self._patch("filesystem_parser.scan_deleted_entries",
                    return_value=list(entradas))
        janela.varrer(DISPOSITIVO)
        return janela

    def _fake_recover(self, conteudo=b"conteudo recuperado"):
        def recover_file(device_path, entry, output_dir):
            os.makedirs(output_dir, exist_ok=True)
            caminho = os.path.join(output_dir, entry["name"])
            with open(caminho, "wb") as handle:
                handle.write(conteudo)
            return caminho

        return self._patch("recovery.recover_file", side_effect=recover_file)

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
        self.assertEqual(janela.user["username"], "admin")
        self.assertEqual(janela.painel_actual(), "dispositivos")
        self.assertEqual(janela.devices_page.arvore.topLevelItemCount(), 2)

    def test_login_falhado_fica_no_mesmo_painel(self):
        janela = self._janela(user=None)
        janela.login_page.campo_utilizador.setText("admin")
        janela.login_page.campo_password.setText("errada")

        janela.login_page.botao_entrar.click()

        self.assertIs(janela.janela.currentWidget(), janela.login_page)
        self.assertEqual(janela.user, {})

    def test_sessao_identificada_no_cabecalho(self):
        janela = self._janela(ADMIN)
        self.assertEqual(janela.etiqueta_sessao.text(), "admin • administrador")

    def test_terminar_sessao_volta_ao_login(self):
        janela = self._janela_com_resultados()

        janela.botao_terminar_sessao.click()

        self.assertIs(janela.janela.currentWidget(), janela.login_page)
        self.assertEqual(janela.user, {})
        self.assertEqual(janela.results_page.tabela.rowCount(), 0)
        self.assertIsNone(janela.dispositivo_actual)

    def test_uma_so_janela_para_todos_os_paineis(self):
        janela = self._janela(ADMIN)
        for chave in ("dispositivos", "resultados", "carving", "auditoria", "contas"):
            janela.ir_para(chave)
            self.assertEqual(janela.painel_actual(), chave)
            self.assertIs(janela.centralWidget(), janela.janela)


class NavegacaoTest(JanelaBase):
    def test_barra_lateral_tem_seccoes_e_entradas(self):
        janela = self._janela(ADMIN)
        rotulos = [
            janela.menu.item(i).text() for i in range(janela.menu.count())
        ]
        self.assertEqual(
            rotulos,
            [
                "Recuperacao de dados",
                "Dispositivos",
                "Ficheiros apagados",
                "Carving por assinatura",
                "Ferramentas",
                "Cadeia de custodia",
                "Contas de acesso",
            ],
        )

    def test_cabecalhos_de_seccao_nao_sao_seleccionaveis(self):
        janela = self._janela(ADMIN)
        cabecalho = janela.menu.item(0)
        self.assertIsNone(cabecalho.data(main_window.Qt.UserRole))
        self.assertFalse(cabecalho.flags() & main_window.Qt.ItemIsSelectable)

    def test_clique_no_menu_muda_de_painel(self):
        janela = self._janela(ADMIN)
        janela.menu.setCurrentItem(janela.itens_do_menu["carving"])
        self.assertEqual(janela.painel_actual(), "carving")

    def test_painel_de_auditoria_carrega_os_eventos(self):
        janela = self._janela_com_resultados()
        janela.ir_para("auditoria")
        self.assertEqual(janela.audit_page.tabela.rowCount(), 1)
        self.assertEqual(janela.audit_page.etiqueta_contagem.text(), "1 eventos")

    def test_painel_de_contas_carrega_as_contas(self):
        janela = self._janela(ADMIN)
        janela.ir_para("contas")
        self.assertEqual(janela.accounts_page.tabela.rowCount(), 2)

    def test_painel_de_carving_recebe_o_dispositivo(self):
        janela = self._janela_com_resultados()
        janela.ir_para("carving")
        self.assertEqual(
            janela.carving_page.painel.valores()["Dispositivo:"], DISPOSITIVO
        )


class PermissoesTest(JanelaBase):
    def test_administrador_ve_tudo(self):
        janela = self._janela(ADMIN)
        for chave in janela.itens_do_menu:
            self.assertFalse(janela.itens_do_menu[chave].isHidden(), chave)

    def test_operador_nao_ve_auditoria_nem_contas(self):
        janela = self._janela(OPERADOR)
        self.assertFalse(janela.itens_do_menu["dispositivos"].isHidden())
        self.assertFalse(janela.itens_do_menu["resultados"].isHidden())
        self.assertFalse(janela.itens_do_menu["carving"].isHidden())
        self.assertTrue(janela.itens_do_menu["auditoria"].isHidden())
        self.assertTrue(janela.itens_do_menu["contas"].isHidden())

    def test_seccao_sem_entradas_visiveis_fica_escondida(self):
        janela = self._janela(OPERADOR)
        self.assertFalse(janela.cabecalhos_de_seccao["Recuperacao de dados"].isHidden())
        self.assertTrue(janela.cabecalhos_de_seccao["Ferramentas"].isHidden())

    def test_administrador_ve_as_duas_seccoes(self):
        janela = self._janela(ADMIN)
        for cabecalho in janela.cabecalhos_de_seccao.values():
            self.assertFalse(cabecalho.isHidden())

    def test_ir_para_painel_escondido_nao_navega(self):
        janela = self._janela(OPERADOR)
        janela.ir_para("contas")
        self.assertNotEqual(janela.painel_actual(), "contas")

    def test_operador_nao_gera_relatorio(self):
        janela = self._janela_com_resultados(user=OPERADOR)
        gerar = self._patch("report.generate_report")

        janela.gerar_relatorio()

        gerar.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "erro")
        self.assertIn("operador", janela.banner.text())

    def test_sem_sessao_nao_varre(self):
        janela = self._janela(user=None)
        scan = self._patch("filesystem_parser.scan_deleted_entries")
        janela.varrer(DISPOSITIVO)
        scan.assert_not_called()


class VarrimentoTest(JanelaBase):
    def test_varrimento_mostra_resultados(self):
        janela = self._janela_com_resultados()
        self.assertEqual(janela.painel_actual(), "resultados")
        self.assertEqual(janela.results_page.tabela.rowCount(), 2)
        self.assertEqual(janela.dispositivo_actual, DISPOSITIVO)
        self.assertEqual(janela.banner.property("tipo"), "sucesso")

    def test_varrimento_regista_evento_com_o_perito(self):
        self._janela_com_resultados()
        eventos = self.log.get_events()
        self.assertEqual([e["action"] for e in eventos], ["scan"])
        self.assertEqual(eventos[0]["device_path"], DISPOSITIVO)
        self.assertEqual(eventos[0]["app_user"], "admin")

    def test_varrimento_a_partir_do_painel_de_dispositivos(self):
        janela = self._janela(ADMIN)
        scan = self._patch("filesystem_parser.scan_deleted_entries", return_value=[])
        janela.devices_page.arvore.setCurrentItem(
            janela.devices_page.arvore.topLevelItem(1)
        )

        janela.devices_page.painel.botao_accao.click()

        scan.assert_called_once_with(r"\\.\PhysicalDrive1")

    def test_varrimento_falhado(self):
        janela = self._janela(ADMIN)
        self._patch("filesystem_parser.scan_deleted_entries",
                    side_effect=RuntimeError("pytsk3 nao esta instalado"))

        janela.varrer(DISPOSITIVO)

        self.assertEqual(janela.banner.property("tipo"), "erro")
        self.assertIn("pytsk3", janela.banner.text())
        self.assertEqual(self.log.get_events(), [])
        self.assertEqual(janela.painel_actual(), "dispositivos")

    def test_varrimento_sem_dispositivo(self):
        janela = self._janela(ADMIN)
        scan = self._patch("filesystem_parser.scan_deleted_entries")
        janela.varrer("")
        scan.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")


class RecuperacaoTest(JanelaBase):
    def test_recuperacao_com_hash_e_verificacao(self):
        janela = self._janela_com_resultados()
        recover = self._fake_recover()
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectAll()

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(recover.call_count, 2)
        self.assertEqual(
            self._accoes(),
            ["scan", "recover", "verify_ok", "recover", "verify_ok"],
        )
        eventos = self.log.get_events()
        self.assertTrue(all(e["app_user"] == "admin" for e in eventos))
        hashes = {e["file_hash"] for e in eventos if e["file_hash"]}
        self.assertEqual(len(next(iter(hashes))), 64)
        self.assertEqual(janela.banner.property("tipo"), "sucesso")

    def test_recuperacao_usa_o_dispositivo_do_varrimento(self):
        janela = self._janela_com_resultados()
        recover = self._fake_recover()
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        argumentos = recover.call_args[0]
        self.assertEqual(argumentos[0], DISPOSITIVO)
        self.assertEqual(argumentos[1]["name"], "relatorio.docx")
        self.assertEqual(argumentos[2], self.tmp)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "relatorio.docx")))

    def test_recuperacao_cancelada_na_escolha_da_pasta(self):
        janela = self._janela_com_resultados()
        recover = self._fake_recover()
        self._patch("MainWindow.escolher_pasta", return_value="")
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        recover.assert_not_called()
        self.assertEqual(self._accoes(), ["scan"])

    def test_recuperacao_com_entrada_sem_clusters(self):
        janela = self._janela_com_resultados()
        self._patch("recovery.recover_file",
                    side_effect=ValueError("entrada sem clusters"))
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.results_page.tabela.selectRow(0)

        janela.results_page.painel.botao_accao.click()

        self.assertEqual(janela.banner.property("tipo"), "aviso")
        self.assertIn("entrada sem clusters", janela.banner.text())
        self.assertEqual(self._accoes(), ["scan"])

    def test_recuperacao_sem_seleccao(self):
        janela = self._janela_com_resultados()
        escolher = self._patch("MainWindow.escolher_pasta")
        janela.recuperar([])
        escolher.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")


class CarvingTest(JanelaBase):
    def test_carving_extrai_e_regista(self):
        janela = self._janela_com_resultados()
        extraido = os.path.join(self.tmp, "jpeg_00001_offset_4096.jpg")

        def carve(device_path, tipo, destino):
            with open(extraido, "wb") as ficheiro:
                ficheiro.write(b"\xff\xd8\xff" + b"J" * 100 + b"\xff\xd9")
            return [extraido]

        carve_mock = self._patch("carving_module.carve_by_signature", side_effect=carve)
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.ir_para("carving")
        janela.carving_page.combo_tipo.setCurrentIndex(1)  # jpeg

        janela.carving_page.painel.botao_accao.click()

        carve_mock.assert_called_once_with(DISPOSITIVO, "jpeg", self.tmp)
        self.assertEqual(self._accoes(), ["scan", "carving", "verify_ok"])
        self.assertEqual(janela.carving_page.tabela.rowCount(), 1)
        self.assertEqual(janela.banner.property("tipo"), "sucesso")

    def test_carving_sem_dispositivo(self):
        janela = self._janela(ADMIN)
        carve = self._patch("carving_module.carve_by_signature")
        janela.devices_page.arvore.clearSelection()

        janela.executar_carving("pdf")

        carve.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")

    def test_carving_usa_o_dispositivo_seleccionado_sem_varrimento(self):
        janela = self._janela(ADMIN)
        carve = self._patch("carving_module.carve_by_signature", return_value=[])
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)
        janela.devices_page.arvore.setCurrentItem(
            janela.devices_page.arvore.topLevelItem(0)
        )

        janela.executar_carving("pdf")

        carve.assert_called_once_with(DISPOSITIVO, "pdf", self.tmp)

    def test_carving_falhado(self):
        janela = self._janela_com_resultados()
        self._patch("carving_module.carve_by_signature",
                    side_effect=IOError("dispositivo ilegivel"))
        self._patch("MainWindow.escolher_pasta", return_value=self.tmp)

        janela.executar_carving("jpeg")

        self.assertEqual(janela.banner.property("tipo"), "erro")
        self.assertEqual(self._accoes(), ["scan"])


class RelatorioTest(JanelaBase):
    def test_relatorio_gerado(self):
        janela = self._janela_com_resultados()
        destino = os.path.join(self.tmp, "relatorio.pdf")
        gerar = self._patch("report.generate_report")
        self._patch("MainWindow.escolher_ficheiro_de_destino", return_value=destino)
        abrir = self._patch("os.startfile", create=True)

        janela.ir_para("auditoria")
        janela.audit_page.painel.botao_accao.click()

        eventos_passados, caminho = gerar.call_args[0]
        self.assertEqual(caminho, destino)
        self.assertEqual([e["action"] for e in eventos_passados], ["scan"])
        abrir.assert_called_once_with(destino)
        self.assertEqual(self._accoes(), ["scan", "report"])
        self.assertEqual(janela.audit_page.tabela.rowCount(), 2)  # tabela actualizada
        self.assertEqual(janela.banner.property("tipo"), "sucesso")

    def test_relatorio_sem_eventos(self):
        janela = self._janela(ADMIN)
        gerar = self._patch("report.generate_report")

        janela.gerar_relatorio()

        gerar.assert_not_called()
        self.assertEqual(janela.banner.property("tipo"), "aviso")

    def test_relatorio_cancelado(self):
        janela = self._janela_com_resultados()
        gerar = self._patch("report.generate_report")
        self._patch("MainWindow.escolher_ficheiro_de_destino", return_value="")

        janela.gerar_relatorio()

        gerar.assert_not_called()
        self.assertEqual(self._accoes(), ["scan"])

    def test_relatorio_falhado(self):
        janela = self._janela_com_resultados()
        self._patch("report.generate_report", side_effect=IOError("disco cheio"))
        self._patch("MainWindow.escolher_ficheiro_de_destino",
                    return_value=os.path.join(self.tmp, "r.pdf"))
        abrir = self._patch("os.startfile", create=True)

        janela.gerar_relatorio()

        self.assertEqual(janela.banner.property("tipo"), "erro")
        abrir.assert_not_called()
        self.assertEqual(self._accoes(), ["scan"])


class EstadoTest(JanelaBase):
    def test_aviso_de_privilegios(self):
        janela = self._janela(ADMIN)
        self.assertEqual(janela.etiqueta_privilegios.text(), main_window.AVISO_ADMIN)
        self.assertEqual(janela.etiqueta_privilegios.objectName(), "avisoPrivilegios")

    def test_estado_com_privilegios(self):
        self._patch("device_reader.is_admin", return_value=True)
        janela = self._janela(ADMIN)
        self.assertEqual(janela.etiqueta_privilegios.text(), main_window.ESTADO_ADMIN)
        self.assertEqual(janela.etiqueta_privilegios.objectName(), "estadoOk")

    def test_notificar_actualiza_banner_e_barra_de_estado(self):
        janela = self._janela(ADMIN)
        janela.notificar("tudo certo", "sucesso")
        self.assertEqual(janela.banner.text(), "tudo certo")
        self.assertEqual(janela.banner.property("tipo"), "sucesso")
        self.assertEqual(janela.statusBar().currentMessage(), "tudo certo")

    def test_conta_criada_notifica(self):
        janela = self._janela(ADMIN)
        janela.ir_para("contas")
        janela.accounts_page.campo_utilizador.setText("perito3")
        janela.accounts_page.campo_password.setText("pass")
        janela.accounts_page.campo_confirmacao.setText("pass")

        janela.accounts_page.botao_criar.click()

        self.assertIn("perito3", janela.banner.text())
        self.assertEqual(janela.banner.property("tipo"), "sucesso")


if __name__ == "__main__":
    unittest.main()
