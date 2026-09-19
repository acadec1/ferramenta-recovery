# FRDA — Ferramenta de Recuperação de Dados Apagados

Ferramenta local de recuperação de ficheiros apagados em dispositivos de
armazenamento (NTFS, FAT32, exFAT), com recuperação por metadados e por
assinaturas (file carving), verificação de integridade SHA-256, histórico das
operações e relatórios em PDF.

## Requisitos

- Python 3.11
- Windows (acesso a `\\.\PhysicalDriveN` requer privilégios de **Administrador**)
- Dependências: ver `requirements.txt`

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No Windows o `pytsk3` instala-se a partir de wheel (cp311), sem compilador. Só é
necessário para o varrimento do sistema de ficheiros — o carving, a verificação de
integridade, a auditoria e os relatórios funcionam sem ele.

**Privilégios:** o Windows recusa a leitura de disco em bruto sem elevação, e não
permite elevar um processo já em execução — o UAC só concede privilégios a um
processo novo. Por isso a aplicação pede a elevação **no arranque, antes de mostrar
qualquer janela**: aceita-se o UAC e a aplicação abre já com privilégios, sem
reinício visível. Se o pedido for recusado, a aplicação abre à mesma em modo
limitado, com o aviso na barra de estado e o botão **Reiniciar como Administrador**
para pedir de novo. Para arrancar sem o pedido:

```
py -3.11 -m src.gui.main_window --sem-elevacao
```

## Estrutura

```
src/
  auth.py               Contas, perfis de acesso e autenticação (PBKDF2-SHA256)
  device_reader.py      Enumeração de discos físicos (\\.\PhysicalDriveN)
  filesystem_parser.py  Varrimento de entradas apagadas via pytsk3
                        (directorias + $OrphanFiles + registos da MFT)
  recovery.py           Reconstrução de ficheiros a partir dos clusters/sectores
  carving.py            Carving por assinatura binária (JPEG, PDF, DOCX)
  integrity.py          Hash SHA-256 e verificação de integridade
  historico.py          Histórico das operações realizadas (sqlite3)
  operacao.py           Execução de uma operação (análise + recuperação)
  report.py             Relatório PDF da operação
  gui/main_window.py    Janela única: barra lateral, painéis e orquestração
  gui/theme.py          Tema visual (claro institucional)
  gui/icons.py          Ícones SVG desenhados no próprio código
  gui/widgets.py        Componentes partilhados (cartões, banner, detalhes)
  gui/pages/login.py    Autenticação
  gui/pages/devices.py  Discos físicos e volumes lógicos
  gui/pages/results.py  Ficheiros encontrados e recuperação
  gui/pages/summary.py  Resultados: cartões de estatísticas e tabela final
  gui/pages/history.py  Histórico das operações e reemissão de relatórios
  gui/workers.py        Análise e recuperação em segundo plano
  gui/pages/accounts.py Contas de acesso (só administrador)
tests/                  Testes unitários (mocks de pytsk3/hardware)
tests/test_integracao.py  Teste com pytsk3 real sobre uma imagem FAT16 gerada
tests/fat16.py            Construtor dessa imagem (ficheiro apagado incluído)
```

## Execução

```
py -3.11 -m src.gui.main_window
```

Executar a partir de uma consola elevada (Administrador) para acesso a disco bruto.

## Fluxo de trabalho

A interface segue a ordem do processo pericial, numerada na barra lateral:

```
1. Dispositivo e método  ->  2. Ficheiros encontrados  ->  3. Resultados
```

1. **Seleccionar o dispositivo** — disco físico, volume local, unidade externa
   (pen ou disco USB) ou imagem `.dd`/`.img`.
2. **Escolher o método** — *recuperação baseada em metadados* (lê as estruturas
   do sistema de ficheiros e devolve nomes e caminhos originais) ou *recuperação
   por assinaturas / File Carving* (procura cabeçalhos e rodapés nos dados em
   bruto, sem depender do sistema de ficheiros).
3. **A análise arranca sozinha e abre logo o painel dos ficheiros** — não é um
   passo separado. A barra de progresso aparece nesse painel e a lista
   **preenche-se em tempo real**, ficheiro a ficheiro, à medida que são
   encontrados; não é preciso esperar pelo fim do varrimento.
4. **Escolher os ficheiros** — a tabela mostra nome, tipo/extensão, tamanho,
   caminho original e data de modificação.
5. **Recuperar** — a pasta de destino é pedida nesta altura e **tem de ser
   diferente do dispositivo analisado**; a aplicação recusa e explica porquê se
   for a mesma ou outro volume do mesmo disco físico.
6. **Resultados** — quatro cartões de estatísticas (encontrados, seleccionados,
   recuperados, não recuperados) e a tabela com o estado de cada ficheiro.
7. **Relatório PDF** — gerado a partir da operação, com identificação, data e
   hora, dispositivo, tipo e capacidade, sistema de ficheiros, método, totais,
   lista de ficheiros processados, pasta de destino e observações ou erros.

### Estado da operação

O estado aparece sempre no topo, com um ponto colorido e a barra de progresso:

| Estado | Cor | Significado |
|---|---|---|
| Aguardando | cinzento | operação ainda não iniciada |
| Em análise | amarelo | dispositivo a ser analisado |
| Em recuperação | amarelo | ficheiros seleccionados a serem recuperados |
| Concluído | verde | operação terminada com sucesso |
| Interrompido | cinzento | parada pelo utilizador; fica o que já foi feito |
| Erro | vermelho | ocorreu uma falha durante a operação |

A barra mostra sempre a percentagem. Enquanto a operação decorre há um botão
**Parar operação** ao lado da lista: a análise devolve os ficheiros já
encontrados (que podem ser recuperados à mesma) e a recuperação guarda os
ficheiros já gravados, registando a operação com a observação de que foi
interrompida.

### Histórico das operações

Cada operação fica registada em SQLite (`frda_historico.db`), nas tabelas
`operacoes` e `operacao_ficheiros`: dispositivo, tipo e capacidade, sistema de
ficheiros, método, totais, pasta de destino, observações e a lista de ficheiros
processados com o respectivo estado e SHA-256. **Os ficheiros recuperados não
são guardados na base de dados** — ficam apenas na pasta de destino escolhida. O
painel *Histórico de operações* lista o que já foi feito, mostra os ficheiros de
cada operação e permite voltar a gerar o respectivo relatório PDF.

A ferramenta é de **recuperação de dados**, não de análise forense: não mantém
cadeia de custódia nem regista acção a acção. O que guarda é o registo da
operação, para saber o que foi feito e poder reemitir o relatório.

## Interface

Aplicação de desktop numa **janela única**: a autenticação, os dispositivos, os
ficheiros encontrados, os resultados, o histórico e as contas são painéis que se
substituem no mesmo espaço — não há diálogos nem janelas secundárias (as únicas
excepções são os selectores de pasta e de ficheiro do próprio Windows).

```
+---------------------------------------------------------------+
| FRDA                              admin • administrador  [Sair]|
+----------------------+----------------------------------------+
|                      | (o) Em análise   \.\G: • metadados    |
| Recuperação de dados | [=========------------------]  38%     |
|  > 1. Dispositivo    | Discos físicos (2)                     |
|    2. Ficheiros      | [#] Disco 0     [#] Disco 1     +-----+|
|    3. Resultados     | Unidades externas (1)           |Deta-||
| Ferramentas          | [#] PEN FORENSE (G:) ###-----   |lhes ||
|    Cadeia de custódia| Método de recuperação (2)       |[Ini-||
|    Contas de acesso  | [*] Metadados   [ ] Assinaturas |ciar]||
+----------------------+----------------------------------------+
| mensagem                     Sem privilégios de Administrador  |
+---------------------------------------------------------------+
```

Barra lateral com as secções, tabela central com os dados e painel de detalhes à
direita com a acção principal. Os avisos aparecem numa faixa colorida no topo do
painel (verde para sucesso, âmbar para aviso, vermelho para erro), e a barra de
estado mostra permanentemente se a aplicação tem privilégios de Administrador.

Ao arrancar, a aplicação pede autenticação. As contas iniciais são criadas na
primeira execução:

| Utilizador | Password      | Perfil        |
|------------|---------------|---------------|
| `admin`    | `admin123`    | administrador |
| `operador` | `operador123` | operador      |

## Como o varrimento encontra os ficheiros

Apagar um ficheiro não apaga os dados: liberta o espaço e marca os metadados como
não alocados. O que muda entre sistemas de ficheiros é *onde* fica esse rasto, e
por isso o varrimento combina três fontes:

1. **Entradas de directoria** — em FAT/exFAT a entrada permanece com o primeiro
   byte do nome substituído por `0xE5`. É aqui que aparecem quase todos os
   apagados numa pen ou cartão de memória.
2. **`$OrphanFiles`** — a directoria virtual onde o Sleuth Kit reúne os ficheiros
   cujo registo sobreviveu mas já não tem entrada de directoria, com o nome
   recuperado dos metadados.
3. **Registos não alocados (MFT)** — em NTFS a eliminação retira a entrada do
   índice da directoria e marca o registo da MFT como livre. Um percurso pelas
   directorias não os encontra; é preciso percorrer os registos. Sem nome
   recuperável, a entrada aparece como `registo_<número>`.

As repetições são eliminadas pelo número de inode, e cada entrada traz o campo
`origem` (`directorio` ou `registo`). O varrimento de registos está limitado a
`MAX_REGISTOS` (500 000 por partição) para não ser ilimitado em discos grandes.

Quando não encontra nada, a aplicação diz porquê: quantas partições viu, quantos
sistemas de ficheiros conseguiu abrir e quantos registos examinou — o que
distingue "não há nada apagado" de "não consegui ler este disco".

## Contas e perfis de acesso

| Ação                          | administrador | operador |
|-------------------------------|:-------------:|:--------:|
| Analisar (metadados e carving)| sim           | sim      |
| Recuperar ficheiros           | sim           | sim      |
| Relatório PDF da operação     | sim           | sim      |
| Histórico de operações        | sim           | não      |
| Criar contas                  | sim           | não      |

O operador não vê sequer as entradas de relatório e de contas na barra lateral
(a secção "Ferramentas" desaparece por completo). Podem criar-se mais
contas no painel **Contas de acesso**, disponível apenas ao administrador.

As passwords são guardadas com PBKDF2-HMAC-SHA256 (200 000 iterações e salt
aleatório por conta) na tabela `users` do ficheiro `frda_historico.db` — nunca em
claro. As passwords iniciais são públicas por estarem aqui documentadas: devem
ser substituídas por contas próprias antes de qualquer uso real.

O utilizador autenticado fica registado em cada operação (coluna `app_user`) e
aparece no relatório PDF, ao lado do utilizador do sistema operativo.

## Como testar

### 1. Testes automáticos (sem hardware, sem privilégios)

```
py -3.11 -m unittest discover -s tests -t . -v      # suite completa
py -3.11 -m unittest tests.test_carving -v          # um módulo isolado
```

291 testes. A maioria usa mocks de `pytsk3` e do `kernel32`, e imagens de disco
sintéticas criadas em ficheiros temporários — nenhum dispositivo físico é tocado. Os
testes da GUI correm com Qt em modo *offscreen* e ficam em `skipped` se o PySide6 não
estiver instalado; os de `report.py` ficam em `skipped` sem o ReportLab.

`tests/test_integracao.py` é a excepção e não usa mocks: constrói uma imagem **FAT16
real** com um ficheiro apagado (nome marcado com `0xE5` e cadeia da FAT libertada) e
corre o `pytsk3` verdadeiro — varrimento, reconstrução a partir dos clusters, carving
e SHA-256 — sem hardware nem elevação. Foi este teste que apanhou constantes do
Sleuth Kit com valores errados que os mocks não detetavam.

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
4. Autenticar-se com `admin` / `admin123` (o perfil `operador` chega para os passos
   5 e 6, mas não gera o relatório do passo 7).
5. Em **1. Dispositivo e método**, escolher a pen e o método, e carregar em
   **Iniciar análise**. A análise arranca de imediato, com o estado a amarelo e a
   barra de progresso a avançar.
6. Em **2. Ficheiros encontrados**, seleccionar as linhas e carregar em
   **Recuperar seleccionados**, escolhendo uma pasta **noutro disco**. Regra
   forense: nunca gravar no dispositivo em análise — a aplicação recusa-o.
7. Em **3. Resultados**, confirmar os cartões de estatísticas e a tabela, e
   carregar em **Gerar relatório PDF**.
8. Confirmar a integridade comparando o SHA-256 registado no histórico com o do
   ficheiro recuperado:

```
py -3.11 -c "from src.integrity import verify_integrity; print(verify_integrity('<hash do relatorio>', r'D:\saida\ficheiro.jpg'))"
```

O histórico fica em `frda_historico.db` (SQLite) na pasta de trabalho e pode ser
consultado a qualquer momento:

```
py -3.11 -c "from src.historico import Historico; [print(o) for o in Historico('frda_historico.db').get_operations()]"
```
