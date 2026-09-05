"""Testes da GUI (src/gui/main_window.py) com Qt em modo offscreen.

Todas as chamadas a hardware e aos modulos de recuperacao sao substituidas por
mocks; nenhum dispositivo fisico e tocado.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from src.gui import main_window
except ImportError:  # pragma: no cover - depende do ambiente
    main_window = None

from src.audit_log import AuditLog

DISPOSITIVOS = [
    {"index": 0, "path": r"\\.\PhysicalDrive0", "size_bytes": 500107862016},
    {"index": 1, "path": r"\\.\PhysicalDrive1", "size_bytes": 128035676160},
]

ENTRADAS = [
    {
        "name": "relatorio.docx",
        "path": "/Documentos/relatorio.docx",
        "size": 15000,
        "mtime_iso": "2023-11-14T22:13:20+00:00",
        "runs": [{"block": 100, "count": 4}],
    },
    {
        "name": "foto.jpg",
        "path": "/Imagens/foto.jpg",
        "size": 4096,
        "mtime_iso": None,
        "runs": [{"block": 300, "count": 1}],
    },
]


@unittest.skipIf(main_window is None, "PySide6 nao esta instalado")
class MainWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = AuditLog(":memory:")
        self._patch("device_reader.list_physical_drives", return_value=list(DISPOSITIVOS))
        self._patch("device_reader.is_admin", return_value=False)

    def _patch(self, alvo, **kwargs):
        patcher = mock.patch("src.gui.main_window." + alvo, **kwargs)
        substituto = patcher.start()
        self.addCleanup(patcher.stop)
        return substituto

    def _janela(self):
        janela = main_window.MainWindow(audit_log=self.log)
        self.addCleanup(janela.close)
        return janela

    def _janela_com_entradas(self, entradas=ENTRADAS):
        janela = self._janela()
        self._patch("filesystem_parser.scan_deleted_entries", return_value=list(entradas))
        janela.botao_escanear.click()
        return janela

    # ------------------------------------------------------- dispositivos

    def test_combo_preenchida_com_dispositivos(self):
        janela = self._janela()
        self.assertEqual(janela.combo_dispositivos.count(), 2)
        self.assertEqual(janela.combo_dispositivos.itemData(0), r"\\.\PhysicalDrive0")
        self.assertIn("PhysicalDrive0", janela.combo_dispositivos.itemText(0))
        self.assertIn("465.8 GB", janela.combo_dispositivos.itemText(0))

    def test_sem_dispositivos(self):
        self._patch("device_reader.list_physical_drives", return_value=[])
        janela = self._janela()
        self.assertEqual(janela.combo_dispositivos.count(), 1)
        self.assertIsNone(janela.combo_dispositivos.itemData(0))

    def test_aviso_de_privilegios_na_barra_de_estado(self):
        janela = self._janela()
        self.assertEqual(janela.statusBar().currentMessage(), main_window.AVISO_ADMIN)

    def test_sem_aviso_quando_e_administrador(self):
        self._patch("device_reader.is_admin", return_value=True)
        janela = self._janela()
        self.assertNotIn("AVISO", janela.statusBar().currentMessage())

    # ----------------------------------------------------------- escanear

    def test_escanear_preenche_tabela(self):
        janela = self._janela_com_entradas()
        self.assertEqual(janela.tabela.rowCount(), 2)
        self.assertEqual(janela.tabela.item(0, 0).text(), "relatorio.docx")
        self.assertEqual(janela.tabela.item(0, 1).text(), "15000")
        self.assertEqual(janela.tabela.item(0, 2).text(), "2023-11-14T22:13:20+00:00")
        self.assertEqual(janela.tabela.item(1, 2).text(), "-")
        self.assertTrue(janela.botao_recuperar.isEnabled())

    def test_escanear_usa_dispositivo_selecionado(self):
        janela = self._janela()
        janela.combo_dispositivos.setCurrentIndex(1)
        scan = self._patch("filesystem_parser.scan_deleted_entries", return_value=[])
        janela.botao_escanear.click()
        scan.assert_called_once_with(r"\\.\PhysicalDrive1")

    def test_escanear_regista_evento_de_auditoria(self):
        self._janela_com_entradas()
        eventos = self.log.get_events()
        self.assertEqual([e["action"] for e in eventos], ["scan"])
        self.assertEqual(eventos[0]["device_path"], r"\\.\PhysicalDrive0")

    def test_escanear_sem_dispositivo(self):
        self._patch("device_reader.list_physical_drives", return_value=[])
        aviso = self._patch("QMessageBox.warning")
        scan = self._patch("filesystem_parser.scan_deleted_entries")
        janela = self._janela()
        janela.botao_escanear.click()
        scan.assert_not_called()
        aviso.assert_called_once()

    def test_escanear_com_erro_mostra_mensagem(self):
        janela = self._janela()
        self._patch(
            "filesystem_parser.scan_deleted_entries",
            side_effect=RuntimeError("pytsk3 nao esta instalado"),
        )
        critico = self._patch("QMessageBox.critical")
        janela.botao_escanear.click()
        critico.assert_called_once()
        self.assertEqual(janela.tabela.rowCount(), 0)
        self.assertEqual(self.log.get_events(), [])

    # ---------------------------------------------------------- recuperar

    def _fake_recover(self, conteudo=b"conteudo recuperado"):
        def recover_file(device_path, entry, output_dir):
            os.makedirs(output_dir, exist_ok=True)
            caminho = os.path.join(output_dir, entry["name"])
            with open(caminho, "wb") as handle:
                handle.write(conteudo)
            return caminho

        return self._patch("recovery.recover_file", side_effect=recover_file)

    def test_recuperar_selecionados(self):
        janela = self._janela_com_entradas()
        recover = self._fake_recover()
        self._patch("QFileDialog.getExistingDirectory", return_value=self.tmp)
        self._patch("QMessageBox.information")
        janela.tabela.selectRow(0)

        janela.botao_recuperar.click()

        self.assertEqual(recover.call_count, 1)
        argumentos = recover.call_args[0]
        self.assertEqual(argumentos[0], r"\\.\PhysicalDrive0")
        self.assertEqual(argumentos[1]["name"], "relatorio.docx")
        self.assertEqual(argumentos[2], self.tmp)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "relatorio.docx")))

    def test_recuperar_regista_hash_e_verificacao(self):
        janela = self._janela_com_entradas()
        self._fake_recover()
        self._patch("QFileDialog.getExistingDirectory", return_value=self.tmp)
        self._patch("QMessageBox.information")
        janela.tabela.selectAll()

        janela.botao_recuperar.click()

        accoes = [e["action"] for e in self.log.get_events()]
        self.assertEqual(accoes, ["scan", "recover", "verify_ok", "recover", "verify_ok"])
        hashes = {e["file_hash"] for e in self.log.get_events() if e["file_hash"]}
        self.assertEqual(len(hashes), 1)  # mesmo conteudo, mesmo SHA-256
        self.assertEqual(len(next(iter(hashes))), 64)

    def test_recuperar_sem_selecao(self):
        janela = self._janela_com_entradas()
        recover = self._fake_recover()
        informacao = self._patch("QMessageBox.information")
        dialogo = self._patch("QFileDialog.getExistingDirectory")
        janela.tabela.clearSelection()

        janela.botao_recuperar.click()

        recover.assert_not_called()
        dialogo.assert_not_called()
        informacao.assert_called_once()

    def test_recuperar_com_dialogo_cancelado(self):
        janela = self._janela_com_entradas()
        recover = self._fake_recover()
        self._patch("QFileDialog.getExistingDirectory", return_value="")
        janela.tabela.selectRow(0)

        janela.botao_recuperar.click()

        recover.assert_not_called()

    def test_recuperar_com_falha_numa_entrada(self):
        janela = self._janela_com_entradas()
        self._patch(
            "recovery.recover_file", side_effect=ValueError("entrada sem clusters")
        )
        self._patch("QFileDialog.getExistingDirectory", return_value=self.tmp)
        aviso = self._patch("QMessageBox.warning")
        janela.tabela.selectRow(0)

        janela.botao_recuperar.click()

        aviso.assert_called_once()
        self.assertIn("entrada sem clusters", aviso.call_args[0][2])
        self.assertEqual([e["action"] for e in self.log.get_events()], ["scan"])

    def test_botao_recuperar_desativado_antes_do_varrimento(self):
        janela = self._janela()
        self.assertFalse(janela.botao_recuperar.isEnabled())

    def test_entrada_completa_guardada_na_tabela(self):
        janela = self._janela_com_entradas()
        entrada = janela.tabela.item(0, 0).data(Qt.UserRole)
        self.assertEqual(entrada, ENTRADAS[0])
        self.assertEqual(janela.tabela.item(0, 0).toolTip(), "/Documentos/relatorio.docx")

    # ---------------------------------------------------------- relatorio

    def test_gerar_relatorio(self):
        janela = self._janela_com_entradas()
        destino = os.path.join(self.tmp, "relatorio.pdf")
        gerar = self._patch("report.generate_report")
        self._patch("QFileDialog.getSaveFileName", return_value=(destino, "PDF (*.pdf)"))
        abrir = self._patch("os.startfile", create=True)

        janela.botao_relatorio.click()

        gerar.assert_called_once()
        eventos_passados, caminho = gerar.call_args[0]
        self.assertEqual(caminho, destino)
        self.assertEqual([e["action"] for e in eventos_passados], ["scan"])
        abrir.assert_called_once_with(destino)
        self.assertEqual(
            [e["action"] for e in self.log.get_events()], ["scan", "report"]
        )

    def test_gerar_relatorio_sem_eventos(self):
        janela = self._janela()
        gerar = self._patch("report.generate_report")
        informacao = self._patch("QMessageBox.information")

        janela.botao_relatorio.click()

        gerar.assert_not_called()
        informacao.assert_called_once()

    def test_gerar_relatorio_com_dialogo_cancelado(self):
        janela = self._janela_com_entradas()
        gerar = self._patch("report.generate_report")
        self._patch("QFileDialog.getSaveFileName", return_value=("", ""))

        janela.botao_relatorio.click()

        gerar.assert_not_called()
        self.assertEqual([e["action"] for e in self.log.get_events()], ["scan"])

    def test_gerar_relatorio_com_erro(self):
        janela = self._janela_com_entradas()
        self._patch("report.generate_report", side_effect=IOError("disco cheio"))
        self._patch(
            "QFileDialog.getSaveFileName",
            return_value=(os.path.join(self.tmp, "relatorio.pdf"), "PDF (*.pdf)"),
        )
        critico = self._patch("QMessageBox.critical")
        abrir = self._patch("os.startfile", create=True)

        janela.botao_relatorio.click()

        critico.assert_called_once()
        abrir.assert_not_called()
        self.assertEqual([e["action"] for e in self.log.get_events()], ["scan"])

    def test_formatar_tamanho(self):
        self.assertEqual(main_window._formatar_tamanho(512), "512.0 B")
        self.assertEqual(main_window._formatar_tamanho(1536), "1.5 KB")
        self.assertEqual(main_window._formatar_tamanho(500107862016), "465.8 GB")


if __name__ == "__main__":
    unittest.main()
