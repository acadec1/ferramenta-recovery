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
    from src.gui.pages.history import HistoryPage
    from src.gui.pages.devices import DevicesPage
    from src.gui.pages.login import ERRO_CREDENCIAIS, LoginPage
    from src.gui.pages.results import ResultsPage
    from src.gui.pages.summary import SummaryPage
    from src.gui import icons
    from src.gui.widgets import (
        AGUARDANDO,
        CONCLUIDO,
        EM_ANALISE,
        ERRO,
        Banner,
        CartaoDeDispositivo,
        CartaoDeEstatistica,
        CartaoDeMetodo,
        EstadoDaOperacao,
        PainelDeDetalhes,
        TituloDeSeccao,
        formatar_tamanho,
    )
    from src.gui import workers
    from src.gui.workers import TrabalhoDeAnalise, TrabalhoDeRecuperacao
except ImportError:  # pragma: no cover - depende do ambiente
    LoginPage = None

from src import auth
from src.historico import (
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
)
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
    {"nome": "relatorio.docx", "name": "relatorio.docx", "tipo": "DOCX",
     "tamanho": 15000, "size": 15000, "path": "/Documentos/relatorio.docx",
     "mtime_iso": "2026-08-14T22:13:20+00:00", "crtime_iso": None,
     "fs_type": "TSK_FS_TYPE_NTFS", "resident": False,
     "metodo": METODO_METADADOS, "runs": [{"block": 100, "count": 4}]},
    {"nome": "foto.jpg", "name": "foto.jpg", "tipo": "JPG", "tamanho": 4096,
     "size": 4096, "path": "/Imagens/foto.jpg", "mtime_iso": None,
     "metodo": METODO_METADADOS, "runs": [{"block": 300, "count": 1}]},
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
        """Recolhe as emissoes de um sinal: o argumento, a tupla, ou True."""
        recebidos = []

        def registar(*args):
            if not args:
                recebidos.append(True)
            elif len(args) == 1:
                recebidos.append(args[0])
            else:
                recebidos.append(tuple(args))

        sinal.connect(registar)
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

    def _cartoes(self, tipo):
        return [c for c in self.pagina.cartoes if c.dados["tipo"] == tipo]

    def _seccoes(self):
        titulos = []
        for indice in range(self.pagina.seccoes.count()):
            widget = self.pagina.seccoes.itemAt(indice).widget()
            if isinstance(widget, TituloDeSeccao):
                titulos.append(widget.text())
        return titulos

    def test_seccoes_com_contagem(self):
        self.assertEqual(
            self._seccoes(),
            [
                "Discos fisicos (2)",
                "Volumes locais (2)",
                "Unidades externas (1)",
                "Acesso rapido (1)",
            ],
        )

    def test_um_cartao_por_dispositivo(self):
        self.assertEqual(len(self._cartoes("disco")), 2)
        self.assertEqual(len(self._cartoes("volume")), 3)
        self.assertEqual(len(self._cartoes("imagem")), 1)

    def test_cartao_de_disco(self):
        cartao = self._cartoes("disco")[0]
        self.assertEqual(cartao.etiqueta_nome.text(), "Disco fisico 0")
        self.assertEqual(cartao.etiqueta_detalhe.text(), "Acesso bruto • 465.8 GB")
        self.assertFalse(cartao.barra.isVisible())

    def test_cartao_de_volume_mostra_ocupacao(self):
        cartao = next(c for c in self._cartoes("volume")
                      if c.dados["dados"]["letter"] == "D")
        self.assertEqual(cartao.etiqueta_nome.text(), "Mamboza Jr. (D:)")
        self.assertEqual(cartao.etiqueta_detalhe.text(), "NTFS • Fixo")
        self.assertEqual(cartao.barra.value(), 61)  # 305 GB usados de 500 GB
        self.assertIn("livres de", cartao.etiqueta_capacidade.text())

    def test_unidade_externa_numa_seccao_propria(self):
        externo = next(c for c in self._cartoes("volume")
                       if c.dados["dados"]["letter"] == "G")
        self.assertEqual(externo.etiqueta_detalhe.text(), "exFAT • Removivel")

    def test_seleccionar_cartao(self):
        cartao = self._cartoes("disco")[1]
        cartao.escolhido.emit(cartao.dados)

        self.assertTrue(cartao.esta_seleccionado())
        self.assertFalse(self._cartoes("disco")[0].esta_seleccionado())
        self.assertEqual(self.pagina.dispositivo_selecionado(), r"\\.\PhysicalDrive1")
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "Disco fisico 1")

    def test_detalhes_do_volume(self):
        cartao = next(c for c in self._cartoes("volume")
                      if c.dados["dados"]["letter"] == "D")
        cartao.escolhido.emit(cartao.dados)

        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Sistema de ficheiros:"], "NTFS")
        self.assertEqual(valores["Caminho:"], r"\\.\D:")
        self.assertEqual(valores["Disco fisico:"], "0")

    def test_pedido_de_varrimento_leva_o_metodo(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        cartao = self._cartoes("disco")[1]
        cartao.escolhido.emit(cartao.dados)

        self.pagina.painel.botao_accao.click()

        self.assertEqual(pedidos, [(r"\\.\PhysicalDrive1", METODO_METADADOS)])

    def test_duplo_clique_varre_logo(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        cartao = self._cartoes("disco")[0]

        cartao.activado.emit(cartao.dados)

        self.assertEqual(pedidos, [(r"\\.\PhysicalDrive0", METODO_METADADOS)])

    def test_metodos_disponiveis(self):
        metodos = [c.metodo for c in self.pagina.cartoes_de_metodo]
        self.assertEqual(metodos, [METODO_METADADOS, METODO_CARVING])
        self.assertTrue(self.pagina.cartoes_de_metodo[0].esta_seleccionado())

    def test_escolher_o_metodo_de_carving(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        self.pagina.cartoes_de_metodo[1].escolhido.emit(METODO_CARVING)
        cartao = self._cartoes("disco")[0]
        cartao.escolhido.emit(cartao.dados)

        self.pagina.painel.botao_accao.click()

        self.assertEqual(self.pagina.metodo, METODO_CARVING)
        self.assertFalse(self.pagina.cartoes_de_metodo[0].esta_seleccionado())
        self.assertEqual(pedidos, [(r"\\.\PhysicalDrive0", METODO_CARVING)])

    def test_metodo_aparece_nos_detalhes(self):
        cartao = self._cartoes("disco")[0]
        cartao.escolhido.emit(cartao.dados)
        self.assertEqual(
            self.pagina.painel.valores()["Metodo:"],
            "Recuperacao baseada em metadados",
        )

    def test_informacao_do_dispositivo_para_o_historico(self):
        cartao = next(c for c in self._cartoes("volume")
                      if c.dados["dados"]["letter"] == "D")
        cartao.escolhido.emit(cartao.dados)
        self.assertEqual(
            self.pagina.informacao_do_dispositivo(),
            {"device_type": "Fixo", "device_size": 500_000_000_000,
             "filesystem": "NTFS"},
        )

    def test_informacao_sem_seleccao(self):
        self.assertEqual(self.pagina.informacao_do_dispositivo(), {})

    def test_sem_seleccao_nao_pede_varrimento(self):
        pedidos = self.capturar(self.pagina.varrimento_pedido)
        self.pagina.painel.botao_accao.click()
        self.assertEqual(pedidos, [])

    def test_cartao_de_imagem_pede_ficheiro(self):
        pedidos = self.capturar(self.pagina.imagem_pedida)
        cartao = self._cartoes("imagem")[0]

        cartao.escolhido.emit(cartao.dados)

        self.assertEqual(len(pedidos), 1)
        self.assertIsNone(self.pagina.dispositivo_selecionado())

    def test_definir_imagem_selecciona_o_cartao(self):
        self.pagina.definir_imagem(r"D:\provas\caso1.dd")

        cartao = self._cartoes("imagem")[0]
        self.assertTrue(cartao.esta_seleccionado())
        self.assertEqual(self.pagina.dispositivo_selecionado(), r"D:\provas\caso1.dd")
        self.assertEqual(cartao.etiqueta_detalhe.text(), r"D:\provas\caso1.dd")

    def test_sem_dispositivos(self):
        with mock.patch("src.gui.pages.devices.device_reader.list_physical_drives",
                        return_value=[]), \
             mock.patch("src.gui.pages.devices.device_reader.list_logical_volumes",
                        return_value=[]):
            self.pagina.carregar()
        self.assertEqual(len(self._cartoes("disco")), 0)
        self.assertEqual(self._seccoes()[0], "Discos fisicos (0)")


class IconesTest(PainelBase):
    def test_desenha_pixmap_quadrado(self):
        imagem = icons.pixmap("disco", 20)
        self.assertFalse(imagem.isNull())
        self.assertEqual(imagem.width(), imagem.height())

    def test_reutiliza_o_mesmo_desenho(self):
        icons.limpar_cache()
        primeiro = icons.pixmap("volume", 18, "#123456")
        segundo = icons.pixmap("volume", 18, "#123456")
        self.assertIs(primeiro, segundo)

    def test_chip_colorido(self):
        imagem = icons.chip("disco", "verde", 44)
        self.assertFalse(imagem.isNull())
        self.assertEqual(imagem.width() / imagem.devicePixelRatio(), 44)

    def test_todos_os_icones_desenham(self):
        for nome in icons.DESENHOS:
            self.assertFalse(icons.pixmap(nome, 16).isNull(), nome)

    def test_icone_desconhecido(self):
        with self.assertRaises(KeyError):
            icons.pixmap("inexistente")

    def test_icone_para_botoes(self):
        self.assertFalse(icons.icone("lupa", 16).isNull())


class ResultsPageTest(PainelBase):
    def setUp(self):
        self.pagina = self.registar(ResultsPage())
        self.pagina.mostrar_entradas(ENTRADAS, r"\\.\D:")

    def test_tabela_preenchida(self):
        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(
            [self.pagina.tabela.horizontalHeaderItem(i).text() for i in range(5)],
            ["Nome", "Tipo", "Tamanho", "Caminho original", "Data de modificacao"],
        )
        self.assertEqual(self.pagina.tabela.item(0, 0).text(), "relatorio.docx")
        self.assertEqual(self.pagina.tabela.item(0, 1).text(), "DOCX")
        self.assertEqual(self.pagina.tabela.item(0, 2).text(), "14.6 KB")
        self.assertIn("2 ficheiros encontrados", self.pagina.etiqueta_contagem.text())

    def test_barra_so_aparece_com_a_analise(self):
        pagina = self.registar(ResultsPage())
        self.assertFalse(pagina.estado.isVisibleTo(pagina))

        pagina.iniciar_analise(r"\\.\D:", METODO_METADADOS)

        self.assertTrue(pagina.estado.isVisibleTo(pagina))
        self.assertEqual(pagina.estado.estado, EM_ANALISE)
        self.assertIn("metadados", pagina.estado.detalhe.text())
        self.assertEqual(pagina.tabela.rowCount(), 0)
        self.assertEqual(pagina.etiqueta_contagem.text(), "0 ficheiros encontrados")

    def test_lista_preenche_se_durante_a_analise(self):
        pagina = self.registar(ResultsPage())
        pagina.iniciar_analise(r"\\.\D:", METODO_METADADOS)

        pagina.acrescentar_entradas([ENTRADAS[0]])
        self.assertEqual(pagina.tabela.rowCount(), 1)
        self.assertEqual(pagina.etiqueta_contagem.text(), "1 ficheiros encontrados")
        self.assertTrue(pagina.botao_selecionar_tudo.isEnabled())

        pagina.acrescentar_entradas([ENTRADAS[1]])
        self.assertEqual(pagina.tabela.rowCount(), 2)
        self.assertEqual([e["nome"] for e in pagina.entradas],
                         ["relatorio.docx", "foto.jpg"])

    def test_progresso_e_fim_da_analise(self):
        pagina = self.registar(ResultsPage())
        pagina.iniciar_analise(r"\\.\D:", METODO_METADADOS)
        pagina.definir_progresso(30, 60)
        self.assertEqual(pagina.estado.percentagem(), 50)

        pagina.acrescentar_entradas(ENTRADAS)
        pagina.terminar_analise(r"\\.\D:")

        self.assertEqual(pagina.estado.estado, CONCLUIDO)
        self.assertIn("2 ficheiros encontrados", pagina.etiqueta_contagem.text())

    def test_recuperacao_usa_a_mesma_barra(self):
        self.pagina.iniciar_recuperacao(3, r"D:\Recuperados")
        self.assertTrue(self.pagina.estado.isVisibleTo(self.pagina))
        self.assertIn("3 ficheiros", self.pagina.estado.detalhe.text())

    def test_erro_aparece_na_pagina(self):
        self.pagina.falhar("Acesso negado")
        self.assertEqual(self.pagina.estado.estado, ERRO)
        self.assertIn("Acesso negado", self.pagina.estado.detalhe.text())

    def test_detalhes_de_uma_entrada_de_metadados(self):
        self.pagina.tabela.selectRow(0)
        valores = self.pagina.painel.valores()
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "relatorio.docx")
        self.assertEqual(valores["Tipo:"], "DOCX")
        self.assertEqual(valores["Encontrado por:"], "metadados")
        self.assertEqual(valores["Clusters:"], "4")

    def test_detalhes_de_um_candidato_de_carving(self):
        self.pagina.mostrar_entradas([
            {"nome": "jpeg_00001_offset_4096.jpg", "tipo": "JPG", "tamanho": 3009,
             "offset": 4096, "metodo": METODO_CARVING},
        ])
        self.pagina.tabela.selectRow(0)
        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Encontrado por:"], "assinatura binaria")
        self.assertEqual(valores["Posicao no disco:"], "4096")

    def test_detalhes_de_varias_entradas(self):
        self.pagina.tabela.selectAll()
        self.assertEqual(
            self.pagina.painel.etiqueta_titulo.text(), "2 ficheiros seleccionados"
        )

    def test_pedido_de_recuperacao(self):
        pedidos = self.capturar(self.pagina.recuperacao_pedida)
        self.pagina.tabela.selectRow(1)

        self.pagina.painel.botao_accao.click()

        self.assertEqual(len(pedidos), 1)
        self.assertEqual([e["nome"] for e in pedidos[0]], ["foto.jpg"])

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
        self.assertFalse(self.pagina.estado.isVisibleTo(self.pagina))


class SummaryPageTest(PainelBase):
    OPERACAO = {
        "id": 3,
        "metodo": METODO_CARVING,
        "device_path": r"\\.\PhysicalDrive1",
        "filesystem": "exFAT",
        "pasta_destino": r"D:\Recuperados",
        "inicio": "2026-09-19T10:00:00+00:00",
        "fim": "2026-09-19T10:04:00+00:00",
        "app_user": "admin",
        "encontrados": 92,
        "seleccionados": 15,
        "recuperados": 13,
        "nao_recuperados": 2,
    }
    FICHEIROS = [
        {"nome": "foto.jpg", "tipo": "JPG", "tamanho": 2048,
         "estado": ESTADO_RECUPERADO, "caminho": r"D:\Recuperados\foto.jpg"},
        {"nome": "nota.txt", "tipo": "TXT", "tamanho": 100,
         "estado": ESTADO_FALHADO, "erro": "entrada sem clusters"},
    ]

    def setUp(self):
        self.pagina = self.registar(SummaryPage())

    def test_cartoes_de_estatisticas(self):
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.assertEqual(self.pagina.cartoes["encontrados"].valor(), "92")
        self.assertEqual(self.pagina.cartoes["seleccionados"].valor(), "15")
        self.assertEqual(self.pagina.cartoes["recuperados"].valor(), "13")
        self.assertEqual(self.pagina.cartoes["nao_recuperados"].valor(), "2")

    def test_tabela_dos_ficheiros_processados(self):
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(
            [self.pagina.tabela.horizontalHeaderItem(i).text() for i in range(5)],
            ["Nome", "Tipo", "Tamanho", "Estado", "Observacao"],
        )
        self.assertEqual(self.pagina.tabela.item(0, 3).text(), ESTADO_RECUPERADO)
        self.assertEqual(self.pagina.tabela.item(1, 3).text(), ESTADO_FALHADO)
        self.assertEqual(self.pagina.tabela.item(1, 4).text(), "entrada sem clusters")

    def test_resumo_no_painel(self):
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "Operacao #3")
        valores = self.pagina.painel.valores()
        self.assertEqual(valores["Sistema de ficheiros:"], "exFAT")
        self.assertEqual(valores["Pasta de destino:"], r"D:\Recuperados")
        self.assertIn("13 de 15", self.pagina.etiqueta_estado.text())

    def test_ficheiros_recuperados(self):
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.assertEqual(
            [f["nome"] for f in self.pagina.ficheiros_recuperados()], ["foto.jpg"]
        )

    def test_pedido_de_relatorio(self):
        pedidos = self.capturar(self.pagina.relatorio_pedido)
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.pagina.painel.botao_accao.click()
        self.assertEqual(len(pedidos), 1)

    def test_sem_operacao_nao_gera_relatorio(self):
        pedidos = self.capturar(self.pagina.relatorio_pedido)
        self.pagina.painel.botao_accao.click()
        self.assertEqual(pedidos, [])
        self.assertEqual(self.pagina.cartoes["encontrados"].valor(), "0")

    def test_limpar(self):
        self.pagina.mostrar_operacao(self.OPERACAO, self.FICHEIROS)
        self.pagina.limpar()
        self.assertEqual(self.pagina.tabela.rowCount(), 0)
        self.assertEqual(self.pagina.cartoes["recuperados"].valor(), "0")
        self.assertEqual(self.pagina.operacao, {})


class EstadoDaOperacaoTest(PainelBase):
    def setUp(self):
        self.widget = self.registar(EstadoDaOperacao())

    def test_comeca_em_aguardando(self):
        self.assertEqual(self.widget.estado, AGUARDANDO)
        self.assertEqual(self.widget.etiqueta.text(), "Aguardando")
        self.assertEqual(self.widget.percentagem(), 0)

    def test_estados_e_rotulos(self):
        for estado, rotulo in (
            (EM_ANALISE, "Em analise"),
            (CONCLUIDO, "Concluido"),
            (ERRO, "Erro"),
        ):
            self.widget.definir_estado(estado, "detalhe")
            self.assertEqual(self.widget.etiqueta.text(), rotulo)
            self.assertEqual(self.widget.ponto.property("estado"), estado)
            self.assertEqual(self.widget.detalhe.text(), "detalhe")

    def test_concluido_enche_a_barra(self):
        self.widget.definir_estado(CONCLUIDO)
        self.assertEqual(self.widget.percentagem(), 100)

    def test_progresso(self):
        self.widget.definir_estado(EM_ANALISE)
        self.widget.definir_progresso(25, 100)
        self.assertEqual(self.widget.percentagem(), 25)
        self.widget.definir_progresso(3, 4)
        self.assertEqual(self.widget.percentagem(), 75)

    def test_progresso_sem_total_fica_indeterminado(self):
        self.widget.definir_progresso(10, 0)
        self.assertEqual(self.widget.barra.maximum(), 0)

    def test_estado_desconhecido_volta_a_aguardando(self):
        self.widget.definir_estado("inventado")
        self.assertEqual(self.widget.estado, AGUARDANDO)


class CartaoDeEstatisticaTest(PainelBase):
    def test_valor_e_legenda(self):
        cartao = self.registar(CartaoDeEstatistica("Recuperados", "verde"))
        self.assertEqual(cartao.valor(), "0")
        cartao.definir_valor(13)
        self.assertEqual(cartao.valor(), "13")
        self.assertEqual(cartao.etiqueta_legenda.text(), "Recuperados")
        self.assertEqual(cartao.etiqueta_valor.property("cor"), "verde")


class CartaoDeMetodoTest(PainelBase):
    def test_seleccao_e_sinal(self):
        cartao = self.registar(
            CartaoDeMetodo(METODO_CARVING, "Carving", "descricao", "carving")
        )
        escolhas = self.capturar(cartao.escolhido)

        self.assertFalse(cartao.esta_seleccionado())
        cartao.definir_seleccionado(True)
        self.assertTrue(cartao.esta_seleccionado())

        cartao.escolhido.emit(cartao.metodo)
        self.assertEqual(escolhas, [METODO_CARVING])


class TrabalhosTest(PainelBase):
    """Os trabalhos correm a logica de src/operacao.py e comunicam por sinais."""

    def test_analise_com_sucesso(self):
        trabalho = TrabalhoDeAnalise(r"\\.\D:", METODO_METADADOS)
        concluidos = self.capturar(trabalho.concluido)
        progressos = self.capturar(trabalho.progresso)

        def analisar(device_path, metodo, progresso=None, ao_encontrar=None):
            progresso(5, 10)
            return [{"nome": "x.bin"}], {"metodo": metodo}

        with mock.patch("src.gui.workers.operacao.analisar", side_effect=analisar):
            trabalho.run()

        self.assertEqual(progressos, [(5, 10)])
        self.assertEqual(concluidos[0], ([{"nome": "x.bin"}], {"metodo": "metadados"}))

    def test_entradas_sao_enviadas_em_lotes_durante_a_analise(self):
        trabalho = TrabalhoDeAnalise(r"\\.\D:", METODO_METADADOS)
        lotes = self.capturar(trabalho.encontrados)

        def analisar(device_path, metodo, progresso=None, ao_encontrar=None):
            for numero in range(3):
                ao_encontrar({"nome": "f%d.bin" % numero})
            return [], {}

        with mock.patch.object(workers, "TAMANHO_DO_LOTE", 2), \
             mock.patch("src.gui.workers.operacao.analisar", side_effect=analisar):
            trabalho.run()

        # dois no primeiro lote, o terceiro no lote final
        self.assertEqual([len(lote) for lote in lotes], [2, 1])
        self.assertEqual(lotes[0][0]["nome"], "f0.bin")

    def test_analise_falhada(self):
        trabalho = TrabalhoDeAnalise(r"\\.\D:", METODO_METADADOS)
        falhas = self.capturar(trabalho.falhou)

        with mock.patch("src.gui.workers.operacao.analisar",
                        side_effect=PermissionError("Acesso negado")):
            trabalho.run()

        self.assertEqual(falhas, ["Acesso negado"])

    def test_recuperacao_com_sucesso(self):
        trabalho = TrabalhoDeRecuperacao(r"\\.\D:", [{"nome": "x"}], "D:/saida")
        concluidos = self.capturar(trabalho.concluido)

        with mock.patch("src.gui.workers.operacao.recuperar",
                        return_value=[{"estado": ESTADO_RECUPERADO}]) as recuperar:
            trabalho.run()

        recuperar.assert_called_once()
        self.assertEqual(concluidos[0], [{"estado": ESTADO_RECUPERADO}])

    def test_recuperacao_falhada(self):
        trabalho = TrabalhoDeRecuperacao(r"\\.\D:", [], "D:/saida")
        falhas = self.capturar(trabalho.falhou)

        with mock.patch("src.gui.workers.operacao.recuperar",
                        side_effect=ValueError("destino no mesmo disco")):
            trabalho.run()

        self.assertEqual(falhas, ["destino no mesmo disco"])


class HistoryPageTest(PainelBase):
    OPERACOES = [
        {"id": 2, "inicio": "2026-09-19T11:00:00+00:00", "device_path": r"\\.\D:",
         "metodo": METODO_CARVING, "encontrados": 92, "recuperados": 13,
         "nao_recuperados": 2, "filesystem": "exFAT",
         "pasta_destino": r"D:\Recuperados", "app_user": "admin"},
        {"id": 1, "inicio": "2026-09-19T10:00:00+00:00", "device_path": r"\\.\C:",
         "metodo": METODO_METADADOS, "encontrados": 5, "recuperados": 5,
         "nao_recuperados": 0},
    ]

    def setUp(self):
        self.pagina = self.registar(HistoryPage())

    def test_lista_as_operacoes(self):
        self.pagina.mostrar_operacoes(self.OPERACOES)

        self.assertEqual(self.pagina.tabela.rowCount(), 2)
        self.assertEqual(self.pagina.tabela.item(0, 0).text(), "2")
        self.assertEqual(self.pagina.tabela.item(0, 1).text(), "2026-09-19 11:00:00")
        self.assertIn("File Carving", self.pagina.tabela.item(0, 3).text())
        self.assertEqual(self.pagina.tabela.item(0, 5).text(), "13")
        self.assertEqual(self.pagina.etiqueta_contagem.text(), "2 operacoes")

    def test_sem_operacoes(self):
        self.pagina.mostrar_operacoes([])
        self.assertEqual(self.pagina.tabela.rowCount(), 0)
        self.assertIsNone(self.pagina.operacao_seleccionada())
        self.assertFalse(self.pagina.painel.botao_accao.isEnabled())

    def test_seleccionar_mostra_detalhes_e_pede_ficheiros(self):
        pedidos = self.capturar(self.pagina.ficheiros_pedidos)
        self.pagina.mostrar_operacoes(self.OPERACOES)

        self.pagina.tabela.selectRow(0)

        self.assertEqual(pedidos, [2])
        self.assertEqual(self.pagina.painel.etiqueta_titulo.text(), "Operacao #2")
        self.assertEqual(self.pagina.painel.valores()["Recuperados:"], "13")

    def test_ficheiros_da_operacao(self):
        self.pagina.mostrar_ficheiros([
            {"nome": "foto.jpg", "tipo": "JPG", "tamanho": 2048,
             "estado": ESTADO_RECUPERADO},
            {"nome": "nota.txt", "tipo": "TXT", "tamanho": 100,
             "estado": ESTADO_FALHADO},
        ])
        self.assertEqual(self.pagina.tabela_de_ficheiros.rowCount(), 2)
        self.assertEqual(self.pagina.tabela_de_ficheiros.item(0, 2).text(), "2.0 KB")
        self.assertEqual(
            self.pagina.tabela_de_ficheiros.item(1, 3).text(), ESTADO_FALHADO
        )

    def test_pedido_de_relatorio(self):
        pedidos = self.capturar(self.pagina.relatorio_pedido)
        self.pagina.mostrar_operacoes(self.OPERACOES)
        self.pagina.tabela.selectRow(1)

        self.pagina.painel.botao_accao.click()

        self.assertEqual(pedidos, [1])


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
