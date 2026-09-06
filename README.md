# FRDA — Ferramenta de Recuperação de Dados Apagados

Ferramenta forense local para deteção, recuperação e auditoria de ficheiros apagados
em dispositivos de armazenamento (NTFS, FAT32, exFAT), com carving por assinatura,
verificação de integridade SHA-256, registo de cadeia de custódia e relatórios em PDF.

## Requisitos

- Python 3.11
- Windows (acesso a `\\.\PhysicalDriveN` requer privilégios de **Administrador**)
- Dependências: ver `requirements.txt`

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No Windows, o `pytsk3` costuma exigir compilação (Visual C++ Build Tools). Só é
necessário para o varrimento do sistema de ficheiros — o carving, a verificação de
integridade, a auditoria e os relatórios funcionam sem ele.

## Estrutura

```
src/
  device_reader.py      Enumeração de discos físicos (\\.\PhysicalDriveN)
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

## Como testar

### 1. Testes automáticos (sem hardware, sem privilégios)

```
py -3.11 -m unittest discover -s tests -t . -v      # suite completa
py -3.11 -m unittest tests.test_carving -v          # um módulo isolado
```

101 testes. Usam mocks de `pytsk3` e do `kernel32`, e imagens de disco sintéticas
criadas em ficheiros temporários — nenhum dispositivo físico é tocado. Os testes da
GUI correm com Qt em modo *offscreen* e ficam em `skipped` se o PySide6 não estiver
instalado; os de `report.py` ficam em `skipped` sem o ReportLab.

### 2. Teste funcional sobre uma imagem de disco (sem privilégios)

Todos os módulos aceitam o caminho de um ficheiro `.dd`/`.img` no lugar de
`\\.\PhysicalDriveN`, o que permite validar o pipeline sem tocar em discos reais.

Preparar uma imagem com um JPEG rodeado de espaço "não alocado":

```
py -3.11 -c "open('amostra.dd','wb').write(b'\x00'*4096 + open('foto.jpg','rb').read() + b'\x00'*4096)"
```

Recuperar por assinatura e confirmar que o ficheiro extraído é idêntico ao original:

```
py -3.11 -c "from src.carving import carve_by_signature; print(carve_by_signature('amostra.dd','jpeg','saida'))"
py -3.11 -c "from src.integrity import compute_hash; print(compute_hash('foto.jpg'))"
py -3.11 -c "from src.integrity import compute_hash; print(compute_hash('saida/jpeg_00001_offset_4096.jpg'))"
```

Os dois hashes SHA-256 devem coincidir.

### 3. Teste ponta-a-ponta com dispositivo real (requer Administrador e pytsk3)

1. Preparar uma pen USB (FAT32 ou exFAT): copiar alguns ficheiros, apagá-los,
   esvaziar a reciclagem e **não voltar a escrever** na pen.
2. Confirmar o número do disco com `Get-Disk` no PowerShell — a coluna `Number`
   corresponde ao `N` de `\\.\PhysicalDriveN`, e o tamanho confirma que é a pen.
3. Abrir o PowerShell **como Administrador** e lançar `py -3.11 -m src.gui.main_window`.
   Sem elevação a barra de estado mostra o aviso e o acesso a disco bruto falha.
4. Escolher o dispositivo na combo box e carregar em **Escanear**: a tabela lista as
   entradas apagadas com nome, tamanho e data de modificação.
5. Selecionar as linhas e carregar em **Recuperar Selecionados**, escolhendo uma pasta
   **noutro disco**. Regra forense: nunca gravar no dispositivo em análise.
6. Carregar em **Gerar Relatório** para exportar o PDF com a tabela de eventos e o
   resumo (ficheiros recuperados e verificados com sucesso).
7. Confirmar a integridade comparando o SHA-256 registado na auditoria com o do
   ficheiro recuperado:

```
py -3.11 -c "from src.integrity import verify_integrity; print(verify_integrity('<hash do relatorio>', r'D:\saida\ficheiro.jpg'))"
```

O registo de auditoria fica em `frda_audit.db` (SQLite) na pasta de trabalho e pode
ser consultado a qualquer momento:

```
py -3.11 -c "from src.audit_log import AuditLog; [print(e) for e in AuditLog('frda_audit.db').get_events()]"
```
