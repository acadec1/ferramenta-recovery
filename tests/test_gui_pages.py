"""Testes dos paineis da interface, isolados (Qt em modo offscreen)."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QLineEdit

    from src.gui import theme
    from src.gui.pages.accounts import ERRO_CONFIRMACAO, AccountsPage
    from src.gui.pages.audit import AuditPage
    from src.gui.pages.carving import CarvingPage
    from src.gui.pages.devices import DevicesPage
    from src.gui.pages.login import ERRO_CREDENCIAIS, LoginPage
    from src.gui.pages.results import ResultsPage
    from src.gui.widgets import Banner, PainelDeDetalhes, formatar_tamanho
except ImportError:  # pragma: no cover - depende do ambiente
    LoginPage = None

from src import auth
from src.audit_log import ACTION_RECOVER, ACTION_SCAN, ACTION_VERIFY_OK
from src.auth import ROLE_ADMIN, ROLE_OPERATOR, AuthStore

DISCOS = [
    {"index": 0, "path": r"\\.\PhysicalDrive0", "size_bytes": 500107862016},
    {"index": 1, "path": r"\\.\PhysicalDrive1", "size_bytes": 128035676160},
]

VOLUMES = [
    {"letter": "C", "root": "C:\\", "path": r"\\.\C:", "label": "",
     "filesystem": "NTFS", "size_bytes": 126_400_000_000, "free_bytes": 20_000_000_000,
     "drive_type": "Fixo", "disk_index": 1},
    {"letter": "D", "root": "D:\\", "path": r"\\.\D:", "label": "Mamboza Jr.",
     "filesystem": "NTFS", "size_bytes": 500_000_000_000, "free_bytes": 195_000_000_000,
     "drive_type": "Fixo", "disk_index": 0},
    {"letter": "G", "root": "G:\\", "path": r"\\.\G:", "label": "SD Card",
     "filesystem": "exFAT", "size_bytes": 58_300_000_000, "free_bytes": 1_000_000,
     "drive_type": "Removivel", "disk_index": None},
]

ENTRADAS = [
    {"name": "relatorio.docx", "path": "/Documentos/relatorio.docx", "size": 15000,
     "mtime_iso": "2026-08-14T22:13:20+00:00", "crtime_iso": None,
     "fs_type": "TSK_FS_TYPE_NTFS", "resident": False,
     "runs": [{"block": 100, "count": 4}]},
    {"name": "foto.jpg", "path": "/Imagens/foto.jpg", "size": 4096,
     "mtime_iso": None, "runs": [{"block": 300, "count": 1}]},
]


@unittest.skipIf(LoginPage is None, "PySide6 nao esta instalado")
class PainelBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def registar(self, widget):
        self.addCleanup(widget.deleteLater)
        return widget

    def capturar(self, sinal):
        recebidos = []
        sinal.connect(lambda *args: recebidos.append(args[0] if args else True))
        return recebidos


class LoginPageTest(PainelBase):
    def setUp(self):
        patcher = mock.patch.object(auth, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = AuthStore(":memory:")
        self.store.ensure_default_accounts()
        self.addCleanup(self.store.close)
        self.pagina = self.registar(LoginPage(self.store))

    def test_autenticacao_com_sucesso(self):
        contas = self.capturar(self.pagina.autenticado)
        self.pagina.campo_utilizador.setText("admin")
        self.pagina.campo_password.setText("admin123")

        self.pagina.botao_entrar.click()

        self.assertEqual(contas[0]["username"], "admin")
        self.assertEqual(contas[0]["role"], ROLE_ADMIN)
        self.assertEqual(self.pagina.etiqueta_erro.text(), "")

    def test_operador(self):
        contas = self.capturar(self.pagina.autenticado)
        self.pagina.campo_utilizador.setText("operador")
        self.pagina.campo_password.setText("operador123")
        self.pagina.botao_entrar.click()
        self.assertEqual(contas[0]["role"], ROLE_OPERATOR)

    def test_credenciais_erradas(self):
        contas = self.capturar(self.pagina.autenticado)
        self.pagina.campo_utilizador.setText("admin")
        self.pagina.campo_password.setText("errada")

        self.pagina.botao_entrar.click()

        self.assertEqual(contas, [])
        self.assertIsNone(self.pagina.user)
        self.assertEqual(self.pagina.etiqueta_erro.text(), ERRO_CREDENCIAIS)
        self.assertEqual(self.pagina.campo_password.text(), "")

    def test_enter_autentica(self):
        contas = self.capturar(self.pagina.autenticado)
        self.pagina.campo_utilizador.setText("admin")
        self.pagina.campo_password.setText("admin123")
        self.pagina.campo_password.returnPressed.emit()
        self.assertEqual(len(contas), 1)

    def test_preparar_limpa_o_formulario(self):
        self.pagina.campo_utilizador.setText("admin")
        self.pagina.campo_password.setText("x")
        self.pagina.etiqueta_erro.setText("erro")

        self.pagina.preparar()

        self.assertEqual(self.pagina.campo_utilizador.text(), "")
        self.assertEqual(self.pagina.campo_password.text(), "")
        self.assertEqual(self.pagina.etiqueta_erro.text(), "")

    def test_password_escondida(self):
        self.assertEqual(self.pagina.campo_password.echoMode(), QLineEdit.Password)


class DevicesPageTest(PainelBase):
    def setUp(self):
        for nome, valor in (("list_physical_drives", DISCOS),
                            ("list_logical_volumes", VOLUMES)):
            patcher = mock.patch(
                "src.gui.pages.devices.device_reader." + nome, return_value=list(valor)
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        self.pagina = self.registar(DevicesPage())
        self.pagina.carregar()

    def test_discos_no_primeiro_nivel(self):
        self.assertEqual(self.pagina.arvore.topLevelItemCount(), 3)  # 2 discos + G:
        self.assertEqual(self.pagina.arvore.topLevelItem(0).text(0), "Disco fisico 0")
        self.assertEqual(self.pagina.arvore.topLevelItem(0).text(3), "465.8 GB")

    def test_volumes_aninhados_no_disco(self):
        disco0 = self.pagina.arvore.topLevelItem(0)
        disco1 = self.pagina.arvore.topLevelItem(1)
        self.assertEqual(disco0.childCount(), 1)
        self.assertEqual(disco0.child(0).text(0), "Mamboza Jr. (D:)")
        self.assertEqual(disco0.child(0).text(2), "NTFS")
        self.assertEqual(disco1.child(0).text(0), "Volume local (C:)")

    def test_volume_sem_disco_fica_no_primeiro_nivel(self):
        solto = self.pagina.arvore.topLevelItem(2)
        self.assertEqual(solto.text(0), "SD Card (G:)")
        self.assertEqual(solto.text(2), "exFAT")

    def test_contagem_de_elementos(self):
        self.assertEqual(self.pagina.etiqueta_contagem.text(), "5 elementos")

    def test_detalhes_do_disco(self):
        self.pagina.arvore.setCurrentItem(self.pagina.arvore.topLevelItem(0))
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "Disco fisico 0")
        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Caminho:"], r"\\.\PhysicalDrive0")
        self.assertEqual(valores["Capacidade:"], "465.8 GB")
        self.assertTrue(self.pagina.painel.botao_accao.isEnabled())

    def test_detalhes_do_volume(self):
        disco0 = self.pagina.arvore.topLevelItem(0)
        self.pagina.arvore.setCurrentItem(disco0.child(0))
        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Sistema de ficheiros:"], "NTFS")
        self.assertEqual(valores["Caminho:"], r"\\.\D:")
        self.assertEqual(valores["Disco fisico:"], "0")
        self.assertEqual(self.pagina.dispositivo_selecionado(), r"\\.\D:")

    def test_pedido_de_varrimento(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        self.pagina.arvore.setCurrentItem(self.pagina.arvore.topLevelItem(1))

        self.pagina.painel.botao_accao.click()

        self.assertEqual(pedidos, [r"\\.\PhysicalDrive1"])

    def test_sem_seleccao_nao_pede_varrimento(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        self.pagina.arvore.clearSelection()
        self.pagina.painel.botao_accao.click()
        self.assertEqual(pedidos, [])

    def test_sem_dispositivos(self):
        with mock.patch("src.gui.pages.devices.device_reader.list_physical_drives",
                        return_value=[]), \
             mock.patch("src.gui.pages.devices.device_reader.list_logical_volumes",
                        return_value=[]):
            self.pagina.carregar()
        self.assertEqual(self.pagina.arvore.topLevelItemCount(), 0)
        self.assertEqual(self.pagina.etiqueta_contagem.text(), "0 elementos")


class ResultsPageTest(PainelBase):
    def setUp(self):
        self.pagina = self.registar(ResultsPage())
        self.pagina.mostrar_entradas(ENTRADAS, r"\\.\D:")

    def test_tabela_preenchida(self):
        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(self.pagina.tabela.item(0, 0).text(), "relatorio.docx")
        self.assertEqual(self.pagina.tabela.item(0, 1).text(), "/Documentos/relatorio.docx")
        self.assertEqual(self.pagina.tabela.item(0, 2).text(), "14.6 KB")
        self.assertEqual(self.pagina.tabela.item(1, 3).text(), "-")
        self.assertIn("2 entradas apagadas", self.pagina.etiqueta_contagem.text())
        self.assertIn(r"\\.\D:", self.pagina.etiqueta_contagem.text())

    def test_detalhes_de_uma_entrada(self):
        self.pagina.tabela.selectRow(0)
        valores = self.pagina.painel.valores()
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "relatorio.docx")
        self.assertEqual(valores["Caminho:"], "/Documentos/relatorio.docx")
        self.assertEqual(valores["Clusters:"], "4")
        self.assertEqual(valores["Dados residentes:"], "nao")

    def test_detalhes_de_varias_entradas(self):
        self.pagina.tabela.selectAll()
        self.assertEqual(
            self.pagina.painel.etiqueta_titulo.text(), "2 entradas seleccionadas"
        )
        self.assertEqual(self.pagina.painel.valores()["Entradas:"], "2")

    def test_pedido_de_recuperacao(self):
        pedidos = self.capturar(self.pagina.recuperacao_pedida)
        self.pagina.tabela.selectRow(1)

        self.pagina.painel.botao_accao.click()

        self.assertEqual(len(pedidos), 1)
        self.assertEqual([e["name"] for e in pedidos[0]], ["foto.jpg"])

    def test_sem_seleccao_nao_pede_recuperacao(self):
        pedidos = self.capturar(self.pagina.recuperacao_pedida)
        self.pagina.tabela.clearSelection()
        self.pagina.painel.botao_accao.click()
        self.assertEqual(pedidos, [])

    def test_seleccionar_tudo(self):
        self.pagina.tabela.clearSelection()
        self.pagina.botao_selecionar_tudo.click()
        self.assertEqual(len(self.pagina.entradas_selecionadas()), 2)

    def test_lista_vazia(self):
        self.pagina.mostrar_entradas([])
        self.assertEqual(self.pagina.tabela.rowCount(), 0)
        self.assertFalse(self.pagina.botao_selecionar_tudo.isEnabled())


class CarvingPageTest(PainelBase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pagina = self.registar(CarvingPage())

    def test_tipos_suportados(self):
        tipos = [
            self.pagina.combo_tipo.itemData(i)
            for i in range(self.pagina.combo_tipo.count())
        ]
        self.assertEqual(tipos, ["docx", "jpeg", "pdf"])
        self.assertEqual(self.pagina.combo_tipo.itemText(0), "DOCX")

    def test_dispositivo_no_painel(self):
        self.pagina.mostrar_dispositivo(r"\\.\PhysicalDrive0")
        self.assertEqual(
            self.pagina.painel.valores()["Dispositivo:"], r"\\.\PhysicalDrive0"
        )
        self.assertTrue(self.pagina.painel.botao_accao.isEnabled())

    def test_sem_dispositivo_desactiva_a_accao(self):
        self.pagina.mostrar_dispositivo(None)
        self.assertFalse(self.pagina.painel.botao_accao.isEnabled())

    def test_pedido_de_carving_com_o_tipo_escolhido(self):
        pedidos = self.capturar(self.pagina.carving_pedido)
        self.pagina.mostrar_dispositivo(r"\\.\PhysicalDrive0")
        self.pagina.combo_tipo.setCurrentIndex(2)  # pdf

        self.pagina.painel.botao_accao.click()

        self.assertEqual(pedidos, ["pdf"])

    def test_resultados_com_tamanhos(self):
        caminho = os.path.join(self.tmp, "jpeg_00001_offset_4096.jpg")
        with open(caminho, "wb") as ficheiro:
            ficheiro.write(b"x" * 2048)

        self.pagina.mostrar_resultados([caminho, os.path.join(self.tmp, "nao_existe")])

        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(self.pagina.tabela.item(0, 1).text(), "2.0 KB")
        self.assertEqual(self.pagina.tabela.item(1, 1).text(), "-")
        self.assertEqual(self.pagina.etiqueta_contagem.text(), "2 ficheiros extraidos")


class AuditPageTest(PainelBase):
    def setUp(self):
        self.pagina = self.registar(AuditPage())
        self.eventos = [
            {"timestamp": "2026-09-06T10:00:00+00:00", "device_path": r"\\.\D:",
             "action": ACTION_SCAN, "file_path": None, "file_hash": None,
             "app_user": "admin"},
            {"timestamp": "2026-09-06T10:01:00+00:00", "device_path": r"\\.\D:",
             "action": ACTION_RECOVER, "file_path": "D:/saida/foto.jpg",
             "file_hash": "a" * 64, "app_user": "operador"},
            {"timestamp": "2026-09-06T10:01:01+00:00", "device_path": r"\\.\D:",
             "action": ACTION_VERIFY_OK, "file_path": "D:/saida/foto.jpg",
             "file_hash": "a" * 64, "app_user": "operador"},
        ]

    def test_tabela_e_resumo(self):
        self.pagina.mostrar_eventos(self.eventos)
        self.assertEqual(self.pagina.tabela.rowCount(), 3)
        self.assertEqual(self.pagina.tabela.item(1, 2).text(), ACTION_RECOVER)
        self.assertEqual(self.pagina.tabela.item(1, 5).text(), "operador")
        self.assertEqual(self.pagina.etiqueta_contagem.text(), "3 eventos")

        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Ficheiros recuperados:"], "1")
        self.assertEqual(valores["Verificados com sucesso:"], "1")
        self.assertEqual(valores["Verificacoes falhadas:"], "0")
        self.assertEqual(valores["Peritos:"], "admin, operador")

    def test_sem_eventos_desactiva_o_relatorio(self):
        self.pagina.mostrar_eventos([])
        self.assertEqual(self.pagina.tabela.rowCount(), 0)
        self.assertFalse(self.pagina.painel.botao_accao.isEnabled())

    def test_pedido_de_relatorio(self):
        pedidos = self.capturar(self.pagina.relatorio_pedido)
        self.pagina.mostrar_eventos(self.eventos)
        self.pagina.painel.botao_accao.click()
        self.assertEqual(len(pedidos), 1)


class AccountsPageTest(PainelBase):
    def setUp(self):
        patcher = mock.patch.object(auth, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = AuthStore(":memory:")
        self.store.ensure_default_accounts()
        self.addCleanup(self.store.close)
        self.pagina = self.registar(AccountsPage(self.store))
        self.pagina.carregar()

    def test_lista_contas(self):
        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(self.pagina.tabela.item(0, 0).text(), "admin")
        self.assertEqual(self.pagina.tabela.item(0, 1).text(), ROLE_ADMIN)

    def test_criar_conta(self):
        criadas = self.capturar(self.pagina.conta_criada)
        self.pagina.campo_utilizador.setText("perito3")
        self.pagina.campo_password.setText("pass-forte")
        self.pagina.campo_confirmacao.setText("pass-forte")
        self.pagina.combo_perfil.setCurrentText(ROLE_OPERATOR)

        self.pagina.botao_criar.click()

        self.assertEqual(criadas, ["perito3"])
        self.assertEqual(self.pagina.tabela.rowCount(), 3)
        self.assertEqual(self.pagina.campo_utilizador.text(), "")
        conta = self.store.authenticate("perito3", "pass-forte")
        self.assertEqual(conta["role"], ROLE_OPERATOR)

    def test_passwords_diferentes(self):
        criadas = self.capturar(self.pagina.conta_criada)
        self.pagina.campo_utilizador.setText("perito4")
        self.pagina.campo_password.setText("uma")
        self.pagina.campo_confirmacao.setText("outra")

        self.pagina.botao_criar.click()

        self.assertEqual(criadas, [])
        self.assertEqual(self.pagina.etiqueta_erro.text(), ERRO_CONFIRMACAO)

    def test_nome_duplicado(self):
        criadas = self.capturar(self.pagina.conta_criada)
        self.pagina.campo_utilizador.setText("admin")
        self.pagina.campo_password.setText("x")
        self.pagina.campo_confirmacao.setText("x")

        self.pagina.botao_criar.click()

        self.assertEqual(criadas, [])
        self.assertIn("admin", self.pagina.etiqueta_erro.text())


class WidgetsETemaTest(PainelBase):
    def test_formatar_tamanho(self):
        self.assertEqual(formatar_tamanho(512), "512.0 B")
        self.assertEqual(formatar_tamanho(1536), "1.5 KB")
        self.assertEqual(formatar_tamanho(500107862016), "465.8 GB")
        self.assertEqual(formatar_tamanho(None), "-")

    def test_banner(self):
        banner = self.registar(Banner())
        self.assertFalse(banner.isVisible())

        banner.mostrar("recuperado", "sucesso")
        self.assertEqual(banner.text(), "recuperado")
        self.assertEqual(banner.property("tipo"), "sucesso")

        banner.limpar()
        self.assertEqual(banner.text(), "")

    def test_painel_de_detalhes_substitui_os_campos(self):
        painel = self.registar(PainelDeDetalhes("Accao"))
        self.assertFalse(painel.botao_accao.isEnabled())

        painel.mostrar("Titulo", "Subtitulo", [("A:", 1), ("B:", 2)])
        self.assertEqual(painel.valores(), {"A:": "1", "B:": "2"})
        self.assertTrue(painel.botao_accao.isEnabled())

        painel.mostrar("Outro", "", [("C:", 3)])
        self.assertEqual(painel.valores(), {"C:": "3"})

        painel.limpar()
        self.assertEqual(painel.valores(), {})
        self.assertFalse(painel.botao_accao.isEnabled())

    def test_stylesheet_usa_a_paleta(self):
        self.assertIn(theme.CORES["primaria"], theme.STYLESHEET)
        self.assertIn("QListWidget#" + theme.MENU_LATERAL, theme.STYLESHEET)
        self.assertIn("QPushButton#" + theme.BOTAO_PRIMARIO, theme.STYLESHEET)
        self.assertIn('QLabel#banner[tipo="erro"]', theme.STYLESHEET)

    def test_stylesheet_sem_marcadores_por_substituir(self):
        for chave in theme.CORES:
            self.assertNotIn("{%s}" % chave, theme.STYLESHEET)
        self.assertNotIn("{botao_primario}", theme.STYLESHEET)
        self.assertNotIn("}}", theme.STYLESHEET)


if __name__ == "__main__":
    unittest.main()
