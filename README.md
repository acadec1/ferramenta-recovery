# FRDA — Ferramenta de Recuperação de Dados Apagados

Ferramenta forense local para deteção, recuperação e auditoria de ficheiros apagados
em dispositivos de armazenamento (NTFS, FAT32, exFAT), com carving por assinatura,
verificação de integridade SHA-256, registo de cadeia de custódia e relatórios em PDF.

## Requisitos

- Python 3.11
- Windows (acesso a `\.\PhysicalDriveN` requer privilégios de **Administrador**)
- Dependências: ver `requirements.txt`

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Estrutura

```
src/
  device_reader.py      Enumeração de discos físicos (\.\PhysicalDriveN)
  filesystem_parser.py  Varrimento de entradas apagadas via pytsk3
  recovery.py           Reconstrução de ficheiros a partir dos clusters/sectores
  carving.py            Carving por assinatura binária (JPEG, PDF, DOCX)
  integrity.py          Hash SHA-256 e verificação de integridade
  audit_log.py          Registo de auditoria / cadeia de custódia (sqlite3)
  report.py             Relatório PDF (ReportLab)
  gui/main_window.py    Interface PySide6
tests/                  Testes unitários (unittest, com mocks de pytsk3/hardware)
```

## Execução

```
py -3.11 -m src.gui.main_window
```

Executar a partir de uma consola elevada (Administrador) para acesso a disco bruto.

## Testes

```
py -3.11 -m unittest discover -s tests -v
```

Os testes usam mocks de `pytsk3` e do acesso a disco — não requerem dispositivo físico
nem privilégios elevados.
