# Requisitos do sistema FRDA

Requisitos da Ferramenta de Recuperação de Dados Apagados, derivados da
implementação existente. Oito requisitos funcionais e oito não funcionais; onde
havia mais candidatos, os afins foram reunidos no mesmo requisito.

## Requisitos funcionais

| # | Requisito | Descrição | Onde está implementado |
|---|---|---|---|
| RF1 | Autenticação e perfis de acesso | O sistema autentica o perito antes de dar acesso a qualquer função. Suporta várias contas e dois perfis: **administrador** (todas as funções) e **operador** (apenas varrimento e recuperação). O administrador pode criar contas. | `src/auth.py`, `src/gui/pages/login.py`, `src/gui/pages/accounts.py` |
| RF2 | Seleção do dispositivo a analisar | Lista os discos físicos e os volumes lógicos ligados à máquina — internos e externos — com capacidade, sistema de ficheiros e ocupação. Permite ainda analisar uma imagem de disco (`.dd`, `.img`, `.raw`). | `src/device_reader.py`, `src/gui/pages/devices.py` |
| RF3 | Varrimento de ficheiros apagados | Identifica as entradas não alocadas em NTFS, FAT32 e exFAT, combinando as entradas de diretoria, os ficheiros órfãos (`$OrphanFiles`) e os registos não alocados da MFT. De cada entrada apresenta nome, caminho original, tamanho e datas. | `src/filesystem_parser.py` |
| RF4 | Recuperação dos ficheiros selecionados | Reconstrói cada ficheiro a partir dos clusters/setores indicados pela entrada e grava-o numa pasta de destino escolhida pelo utilizador. | `src/recovery.py` |
| RF5 | Recuperação por assinatura (carving) | Extrai ficheiros JPEG, PDF e DOCX pelo cabeçalho e rodapé, sem depender do sistema de ficheiros, permitindo recuperar dados sem entrada de diretoria. | `src/carving.py`, `src/gui/pages/carving.py` |
| RF6 | Verificação de integridade | Calcula o SHA-256 de cada ficheiro recuperado e confirma que o ficheiro gravado corresponde a esse valor, registando o resultado da verificação. | `src/integrity.py` |
| RF7 | Registo da cadeia de custódia | Regista de forma persistente cada ação (varrimento, recuperação, carving, verificação, relatório) com data/hora, dispositivo, ficheiro, hash SHA-256, utilizador do sistema operativo e perito autenticado. O registo é consultável na aplicação. | `src/audit_log.py`, `src/gui/pages/audit.py` |
| RF8 | Exportação do relatório pericial | Gera um relatório em PDF com a tabela de eventos e o resumo do exame: ficheiros recuperados, verificados com sucesso, verificações falhadas, dispositivos analisados e peritos intervenientes. | `src/report.py` |

## Requisitos não funcionais

| # | Requisito | Critério | Como é garantido |
|---|---|---|---|
| RNF1 | Preservação da prova | O dispositivo em análise nunca é modificado: é aberto apenas para leitura e os ficheiros recuperados são gravados noutro destino, indicado pelo utilizador. | Abertura em modo `rb` em `recovery.py` e `carving.py`; destino escolhido em diálogo próprio |
| RNF2 | Segurança das credenciais | As passwords são guardadas com PBKDF2-HMAC-SHA256, 200 000 iterações e salt aleatório por conta — nunca em claro. Todas as consultas à base de dados são parametrizadas. | `src/auth.py`, `src/audit_log.py` |
| RNF3 | Gestão de privilégios | A leitura de disco em bruto exige privilégios de Administrador. A elevação é pedida no arranque, antes de existir interface; sem privilégios a aplicação abre à mesma, explica a limitação e oferece nova tentativa. | `device_reader.relaunch_as_admin()`, `main_window.main()` |
| RNF4 | Operação local e offline | Todo o processamento decorre na máquina do perito, sem rede, serviços externos ou envio de dados. | Sem dependências de rede em todo o código |
| RNF5 | Usabilidade | Interface em português, numa única janela: os ecrãs substituem-se no mesmo espaço, sem janelas secundárias. As mensagens aparecem em linha (sucesso, aviso, erro) e o estado de privilégios está sempre visível. | `src/gui/` |
| RNF6 | Desempenho previsível | As leituras são feitas por blocos e alinhadas ao setor, como o Windows exige em disco bruto. O varrimento de registos está limitado a 500 000 por partição, para que o tempo não seja ilimitado em discos grandes. | `recovery._read_aligned`, `carving.CHUNK_SIZE`, `filesystem_parser.MAX_REGISTOS` |
| RNF7 | Dependências e portabilidade | Python 3.11 em Windows, com um conjunto fechado de dependências (`pytsk3`, `PySide6`, `pywin32`, `reportlab`). A auditoria usa SQLite da biblioteca padrão, sem servidor. | `requirements.txt` |
| RNF8 | Testabilidade e manutenção | 238 testes automáticos, que correm sem hardware nem privilégios: mocks de `pytsk3` e do `kernel32`, mais um teste de integração sobre uma imagem FAT16 real. Os módulos são independentes e a interface não contém lógica de negócio. | `tests/`, `tests/test_integracao.py` |

## Notas de rastreabilidade

- RF3 combina três técnicas porque o rasto de um ficheiro apagado fica em sítios
  diferentes conforme o sistema de ficheiros: a entrada permanece na diretoria em
  FAT/exFAT, mas em NTFS sai do índice e resta apenas o registo da MFT.
- RF6 e RF7 sustentam-se mutuamente: o hash sem registo não prova nada, e o
  registo sem hash não permite demonstrar que o ficheiro não foi alterado.
- RNF1 e RNF3 são os requisitos com maior peso pericial: sem preservação da prova
  e sem controlo de privilégios, o resultado não é admissível como evidência.
