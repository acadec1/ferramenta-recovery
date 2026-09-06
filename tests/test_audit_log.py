"""Testes de src/audit_log.py."""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from src.audit_log import AuditLog

DISPOSITIVO = r"\\.\PhysicalDrive0"


class AuditLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "auditoria.db")
        self.log = AuditLog(self.db_path)
        self.addCleanup(self.log.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_tabela_criada(self):
        tabelas = [
            row[0]
            for row in self.log.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        self.assertIn("events", tabelas)

    def test_log_event_devolve_identificador(self):
        primeiro = self.log.log_event(action="scan", device_path=DISPOSITIVO)
        segundo = self.log.log_event(action="scan", device_path=DISPOSITIVO)
        self.assertEqual([primeiro, segundo], [1, 2])

    def test_campos_registados(self):
        self.log.log_event(
            timestamp="2026-09-05T10:00:00+00:00",
            device_path=DISPOSITIVO,
            action="recover",
            file_path=r"D:\saida\foto.jpg",
            file_hash="a" * 64,
            os_user="mambo",
            app_user="admin",
        )
        evento = self.log.get_events()[0]
        self.assertEqual(
            evento,
            {
                "id": 1,
                "timestamp": "2026-09-05T10:00:00+00:00",
                "device_path": DISPOSITIVO,
                "action": "recover",
                "file_path": r"D:\saida\foto.jpg",
                "file_hash": "a" * 64,
                "os_user": "mambo",
                "app_user": "admin",
            },
        )

    def test_timestamp_e_utilizador_por_omissao(self):
        with mock.patch("getpass.getuser", return_value="perito"):
            self.log.log_event(action="scan", device_path=DISPOSITIVO)
        evento = self.log.get_events()[0]
        self.assertEqual(evento["os_user"], "perito")
        self.assertTrue(evento["timestamp"].startswith("20"))
        self.assertIn("T", evento["timestamp"])

    def test_campos_opcionais_ficam_nulos(self):
        self.log.log_event(action="scan")
        evento = self.log.get_events()[0]
        self.assertIsNone(evento["device_path"])
        self.assertIsNone(evento["file_path"])
        self.assertIsNone(evento["file_hash"])
        self.assertIsNone(evento["app_user"])

    def test_accao_obrigatoria(self):
        with self.assertRaises(ValueError):
            self.log.log_event(device_path=DISPOSITIVO)
        with self.assertRaises(ValueError):
            self.log.log_event(action="", device_path=DISPOSITIVO)

    def test_campo_desconhecido_e_rejeitado(self):
        with self.assertRaises(ValueError):
            self.log.log_event(action="scan", observacoes="nota")

    def test_get_events_filtra_por_dispositivo(self):
        self.log.log_event(action="scan", device_path=DISPOSITIVO)
        self.log.log_event(action="scan", device_path=r"\\.\PhysicalDrive1")
        self.log.log_event(action="recover", device_path=DISPOSITIVO)

        eventos = self.log.get_events(device_path=DISPOSITIVO)
        self.assertEqual([e["action"] for e in eventos], ["scan", "recover"])
        self.assertEqual(len(self.log.get_events()), 3)

    def test_get_events_sem_correspondencia(self):
        self.log.log_event(action="scan", device_path=DISPOSITIVO)
        self.assertEqual(self.log.get_events(device_path=r"\\.\PhysicalDrive9"), [])

    def test_ordem_cronologica(self):
        for indice in range(5):
            self.log.log_event(action="acao_%d" % indice, device_path=DISPOSITIVO)
        eventos = self.log.get_events()
        self.assertEqual([e["action"] for e in eventos],
                         ["acao_%d" % i for i in range(5)])

    def test_persistencia_entre_sessoes(self):
        self.log.log_event(action="scan", device_path=DISPOSITIVO)
        self.log.close()
        with AuditLog(self.db_path) as nova_sessao:
            nova_sessao.log_event(action="recover", device_path=DISPOSITIVO)
            self.assertEqual(len(nova_sessao.get_events()), 2)

    def test_base_de_dados_em_memoria(self):
        with AuditLog(":memory:") as memoria:
            memoria.log_event(action="scan")
            self.assertEqual(len(memoria.get_events()), 1)

    def test_injeccao_sql_e_tratada_como_dados(self):
        self.log.log_event(action="scan", device_path="'; DROP TABLE events; --")
        self.assertEqual(len(self.log.get_events()), 1)
        self.assertEqual(
            self.log.get_events(device_path="'; DROP TABLE events; --")[0]["action"],
            "scan",
        )

    def test_migracao_de_base_de_dados_antiga(self):
        antiga = os.path.join(self.tmp, "antiga.db")
        ligacao = sqlite3.connect(antiga)
        with ligacao:
            ligacao.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " timestamp TEXT NOT NULL, device_path TEXT, action TEXT NOT NULL,"
                " file_path TEXT, file_hash TEXT, os_user TEXT)"
            )
            ligacao.execute(
                "INSERT INTO events (timestamp, action) VALUES ('2026-01-01', 'scan')"
            )
        ligacao.close()

        with AuditLog(antiga) as log:
            log.log_event(action="recover", app_user="admin")
            eventos = log.get_events()
        self.assertEqual([e["action"] for e in eventos], ["scan", "recover"])
        self.assertIsNone(eventos[0]["app_user"])  # evento anterior a migracao
        self.assertEqual(eventos[1]["app_user"], "admin")

    def test_ligacao_fechada(self):
        self.log.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.log.get_events()


if __name__ == "__main__":
    unittest.main()
