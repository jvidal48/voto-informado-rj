# Relatório — Voto Informado RJ 2026 (piloto: Governador)

Gerado em 26/09/2026. Fonte de todos os dados: Portal de Dados Abertos do TSE
(https://dadosabertos.tse.jus.br), arquivos baixados de `cdn.tse.jus.br`.

## 0. Arquivos e pré-requisitos

- **schema.sql estava ausente da pasta** no início desta sessão. Foi recriado pelo
  assistente, com autorização explícita do usuário, extraindo cada tabela/coluna
  diretamente do SQL usado em `coleta_tse.py`, `exportar_json.py` e
  `validar_amostra.py` — nenhum dado de candidato foi inventado, apenas a
  estrutura e a tabela de referência estática `cargo` (nomes de cargo).
- `index_1.html` encontrado na pasta é idêntico a `index.html` (não é um
  conflito, parece um backup/cópia).
- Python 3.14.3 confirmado (`python` e `py`).

## 1. Bloqueio de download (Akamai) — resolvido

`coleta_tse.py` falhou com `HTTP 403 Forbidden` ao baixar de `cdn.tse.jus.br`,
tanto neste ambiente quanto na máquina real do usuário (mesmo em rede
doméstica). Diagnóstico: a Akamai (proteção do TSE) bloqueava o User-Agent
não padrão do script (`voto-informado-rj/0.1`), confirmado porque a mesma URL
abriu normalmente em um navegador comum. Ação tomada (autorizada pelo
usuário): trocada apenas a string de User-Agent no `coleta_tse.py` (linha do
`baixar()`) por um valor de navegador padrão — nenhuma lógica de dados foi
alterada.

Mesmo assim, o download programático continuou bloqueado (provável
verificação mais profunda da Akamai, tipo fingerprint de TLS/HTTP). Não foi
tentado nenhum contorno adicional (isso seria burlar bot-detection). Caminho
usado: o usuário baixou manualmente os 6 arquivos `.zip` pelo navegador e o
script rodou localmente com `--zip-dir zips`, sem precisar de rede.

## 2. Coleta executada

```
python coleta_tse.py --cargo GOV --anos 2026 --zip-dir zips
python coleta_tse.py --cargo GOV --anos 2022 2018 --zip-dir zips
```

| Ano  | Candidaturas (após dedupe) | Com bens declarados |
|------|------------------------------|----------------------|
| 2026 | 9                             | 7 / 9                |
| 2022 | 9                             | 8 / 9                |
| 2018 | 12                             | 11 / 12               |

Nota: o script imprimiu "candidaturas: 14" para 2018 durante a coleta — eram
2 linhas duplicadas no CSV oficial para o mesmo `sq_candidato`, corretamente
substituídas pela constraint `UNIQUE(eleicao_id, sq_candidato)` do schema.
Resultado final no banco: 12 candidaturas únicas (confirmado por consulta).

## 3. Consultas no voto.db (GOV, 2026)

**a) Total de candidaturas:** 9

**b) Pessoas com CPF completo:** 24 de 24 (100%) — todas com
`vinculo_confianca='confirmado_cpf'`. Nenhum CPF mascarado encontrado nesta
amostra (11 dígitos completos em todos os casos, incluindo candidaturas
anteriores ligadas por CPF).

**c) Lista de candidatos a Governador do RJ — 2026:**

| Nome (urna) | Nº | Partido | Situação | Total de bens | Itens |
|---|---|---|---|---|---|
| André Marinho | 30 | NOVO | *não informada* | R$ 407.503,55 | 6 |
| Coronel Busnello | 14 | MISSÃO | *não informada* | R$ 950.000,00 | 2 |
| Cyro Garcia | 16 | PSTU | *não informada* | R$ 385.400,00 | 2 |
| Douglas Ruas | 22 | PL | *não informada* | R$ 1.467.687,88 | 18 |
| Eduardo Paes | 55 | PSD | *não informada* | R$ 189.210,63 | 7 |
| Garotinho | 10 | REPUBLICANOS | *não informada* | R$ 167.585,05 | 8 |
| Juliete | 80 | UP | *não informada* | não encontrado | 0 |
| Luan Monteiro | 29 | PCO | *não informada* | não encontrado | 0 |
| William Siri | 50 | PSOL | *não informada* | R$ 120.000,00 | 1 |

**"Situação" veio em branco para os 9** — não é falha do script: o CSV oficial
`consulta_cand_2026` traz `DS_SITUACAO_CANDIDATURA='#NE'` (não especificado)
para todos os governadores do RJ neste momento, e o script converteu isso
corretamente para `NULL` (regra "nunca inventa"). **Diferença real** encontrada
ao comparar com o site (seção 4): o DivulgaCandContas mostra "Situação
Candidato: Deferido" / rótulo "Concorrendo" — um dado que não está disponível
no arquivo `consulta_cand` baixado. **Conferir manualmente / decidir:** se vale
a pena buscar esse campo por outra fonte/arquivo do TSE.

**d) Valores estranhos:** nenhum valor absurdo ou zerado por engano. Os dois
"não encontrado" (Juliete, Luan Monteiro) são corretamente `status_coleta=
'nao_encontrado'` (arquivo de bens lido com sucesso, candidato sem linhas) —
não confundidos com patrimônio R$ 0.

## 4. Validação por amostragem (n=3, seed=2026)

Comparado manualmente contra https://divulgacandcontas.tse.jus.br
(Sudeste → RJ → Governador → ficha individual de cada candidato):

| Candidato | Nome completo | CPF | Nº | Partido | Coligação | Bens (nosso banco) | Bens (site) |
|---|---|---|---|---|---|---|---|
| Garotinho | Anthony William Garotinho Matheus de Oliveira | 698.397.277-53 | 10 | Republicanos | Coragem Para Mudar | R$ 167.585,05 (8 itens) | R$ 167.585,05 (8 itens) ✓ |
| Douglas Ruas | Douglas Ruas dos Santos | 122.727.497-12 | 22 | PL | Rio Real | R$ 1.467.687,88 | R$ 1.467.687,88 ✓ |
| Cyro Garcia | Cyro Garcia | 333.183.527-72 | 16 | PSTU (isolado) | — | R$ 385.400,00 | R$ 385.400,00 ✓ |

**Todos os campos batem.** Única diferença: campo "Situação" (ver item 3c).

**Importante:** esta comparação foi feita pelo assistente abrindo o site
oficial; o comando `validar_amostra.py ok --sq ... --por "SEU NOME"` **não foi
executado** — conforme a regra do projeto, o registro formal de validação
humana fica para você decidir e rodar.

Observação à parte: durante a navegação, a seção "Prestações de Contas" do
próprio site do TSE mostrou, uma vez, dados de outro candidato (parecia
cache/estado da SPA não atualizado ao trocar de página via URL direta) — um
comportamento do site, não relacionado aos nossos dados. Após recarregar a
página do zero, os valores corrigiram e bateram normalmente.

## 5. Exportação e teste do site

```
python exportar_json.py --db voto.db --cargo GOV --ano 2026 --saida data.json
python -m http.server 8000
```

Testado em `http://localhost:8000`:
- **Lista**: carrega os 9 candidatos reais.
- **Busca**: filtra corretamente por nome/número (testado com "paes").
- **Ficha**: testada com Eduardo Paes (candidatura anterior 2018/DEM/não
  eleito, patrimônio comparado entre 2018 e 2026, expansão da lista de bens) e
  com Juliete (mostra "não encontrado" para 2026, distinto do valor real de
  2022 — R$ 203,99).
- **Processos**: exibe corretamente "Não coletado nesta versão" com o aviso
  de que ausência não significa inexistência — nenhum dado de processo foi
  inventado (esse bloco da coleta ainda não foi implementado).

Não foi possível salvar os screenshots como arquivos nesta sessão (o
navegador usado é interno à ferramenta); a verificação visual foi feita e
confirmada, mas sem arquivo de imagem anexado.

## 5b. Campo "Situação" resolvido (2026)

Investigado a pedido do usuário. Achado: o TSE publica um segundo arquivo
aberto, `consulta_cand_complementar_<ano>.zip` (mesmo domínio
`cdn.tse.jus.br`, mesmo dataset `candidatos-<ano>` no Portal de Dados
Abertos), com o campo `DS_SITUACAO_CANDIDATO_TOT` — que reflete exatamente o
que o DivulgaCandContas mostra como "Situação Candidato" (conferido nos 9
candidatos de 2026, incluindo o caso do Garotinho: "Indeferido em prazo
recursal ou com recurso", batendo 100% com o site).

`coleta_tse.py` foi alterado para baixar esse arquivo complementar e
preencher `candidatura.situacao` **somente quando o campo original vier vazio**
(nunca sobrescreve um valor real já existente — 2018/2022 já tinham
situação real vinda do arquivo principal, `APTO`/`INAPTO`, e não foram
tocados). Resultado após reprocessar 2026:

| Candidato | Situação |
|---|---|
| André Marinho, Coronel Busnello, Cyro Garcia, Douglas Ruas, Juliete, Luan Monteiro, William Siri | DEFERIDO |
| Eduardo Paes | DEFERIDO COM RECURSO |
| Garotinho | INDEFERIDO EM PRAZO RECURSAL OU COM RECURSO |

## 5c. Dois bugs de idempotência encontrados e corrigidos

Ao reprocessar 2026 para pegar a situação, o script quebrou — o que revelou
dois bugs reais que afetariam qualquer atualização futura dos dados:

1. **`INSERT OR REPLACE` em `candidatura` quebrava a FK de `patrimonio_bem`.**
   O SQLite apaga e recria a linha (id novo) em vez de atualizar no lugar, o
   que órfã os bens já salvos e derruba com `FOREIGN KEY constraint failed`.
   Trocado por um upsert de verdade (`INSERT ... ON CONFLICT DO UPDATE`), que
   preserva o id e não mexe em `validado_por`/`validado_em`.
2. **Bens duplicavam a cada reexecução.** A seção de bens só fazia `INSERT`,
   sem limpar dados de rodadas anteriores — isso **chegou a duplicar os
   valores de patrimônio de 2026 no banco** (ex: André Marinho apareceu com
   R$ 815 mil, o dobro do real R$ 407 mil) antes de eu notar e corrigir.
   Adicionado um `DELETE` dos bens da candidatura antes de reinserir.

Após as correções, reprocessei 2026 do zero e conferi que os valores voltaram
a bater exatamente com os da seção 3c/4 deste relatório (nenhum dado de
2018/2022 foi afetado, só 2026 tinha sido reexecutado). `data.json` e o teste
local do site (seção 5) foram refeitos depois da correção.

## 6. Conferir manualmente (lista)

1. ~~Situação vazia em 2026~~ — resolvido na seção 5b.
2. As 2 linhas duplicadas no CSV de 2018 (mesmo `sq_candidato`) — conferir se
   é normal (ex: substituição de candidatura) ou se há retificação a
   considerar. Não afeta o banco (dedupe automático via `UNIQUE`).
3. Nenhum outro valor suspeito encontrado na amostra revisada, mas a validação
   humana formal (`validar_amostra.py ok`) ainda não foi registrada — falta
   você rodar esse comando após conferir por conta própria, se concordar com
   a comparação acima.
4. Campo `resultado` (DS_SIT_TOT_TURNO) ainda vem `NULL` para 2026 — é o
   resultado da eleição (eleito/não eleito), que só existe depois do pleito
   ocorrer em outubro. Nada a fazer antes disso.

## 5d. Expansão para Senador e Presidente (pós-publicação)

A pedido do usuário, expandido além do piloto (só Governador). Reaproveitado
o mesmo zip nacional já baixado (`consulta_cand_2026.zip` já trazia os CSVs
de todas as UFs e o nacional `_BRASIL.csv`), sem precisar de novo download:

```
python coleta_tse.py --cargo SEN --uf RJ --anos 2026 --zip-dir zips
python coleta_tse.py --cargo PRES --anos 2026 --zip-dir zips
```

| Cargo | Candidaturas | Bate com o site oficial (contagem RJ/BR)? |
|---|---|---|
| Senador (RJ) | 17 | Sim — DivulgaCandContas mostra "Senador: 17" para o RJ |
| Presidente | 14 | Sim — home do DivulgaCandContas mostra "Presidente: 14" |

`exportar_json.py` foi generalizado para `--cargos` (aceita vários) e o
`data.json` agora tem a forma `{"cargos": {"GOV":{...}, "SEN":{...}, "PRES":{...}}}`.
`index.html` ganhou abas para trocar de cargo, contagem de resultados na
busca, e um destaque visual (âmbar) neutro para situações que pedem atenção
(indeferido/cassado/renúncia) — sem usar vermelho/verde, para não parecer
julgamento de valor.

Também corrigido um typo (`Republica` sem acento) na tabela `cargo` do
schema, no banco já existente e no seed do schema.sql.

## 5e. Deputado Federal e Deputado Estadual (RJ) adicionados

Mesmo processo, mesmos zips já baixados:

```
python coleta_tse.py --cargo DEP_FED --uf RJ --anos 2026 --zip-dir zips
python coleta_tse.py --cargo DEP_EST --uf RJ --anos 2026 --zip-dir zips
```

| Cargo | Candidaturas | Bate com o DivulgaCandContas? |
|---|---|---|
| Deputado Federal (RJ) | 793 | Sim |
| Deputado Estadual (RJ) | 1.188 | Sim |

`data.json` final (5 cargos): 2,88 MB, exportado em ~1,3s. Testado
localmente sem travar.

Ajustes de escala no `index.html`:
- Abas de cargo agora rolam horizontalmente (não quebram o layout).
- Cargos com mais de 60 candidatos (`LIMIAR_BUSCA`) não renderizam a lista
  inteira de cara — pedem para digitar algo antes (evita travar o
  navegador/relayout com ~800-1200 cards de uma vez e também é melhor UX,
  já que ninguém rola manualmente 1000 candidatos).
- Busca com debounce (150 ms) nesses cargos grandes.
- Resultado limitado a 200 cards por vez, com aviso para refinar a busca se
  passar disso.

Testado: busca "silva" em Deputado Federal retornou 137 resultados
corretamente; ficha de candidato individual (ex: Alaide Melo, nº 7004,
AVANTE) abriu normalmente com patrimônio e aviso de "não coletado" para
processos, igual aos outros cargos.

## 5f. Investigação de "processos e condenações" — concluída, com decisão

Investigadas 3 fontes possíveis do TSE:

1. **Dataset "Motivo da Cassação"** (`motivo_cassacao_<ano>.zip`, nacional,
   CSV estruturado) — mas é sobre o **motivo de indeferimento/cassação do
   REGISTRO da candidatura** perante a Justiça Eleitoral (ex: "ausência de
   condição de elegibilidade"), quase sempre com `NR_PROCESSO=-1` — **não é**
   histórico criminal nem condenação da pessoa.
2. **Dataset "Certidão Criminal" por UF** (`certidao_criminal_2026_RJ.zip`)
   — inspecionado e é **10.693 arquivos PDF individuais (1,66 GB)**, sem
   dado estruturado. Extrair "status" disso exigiria OCR + interpretação
   jurídica automática, o que decidi **não fazer**: um erro de leitura
   poderia rotular alguém como condenado incorretamente — exatamente o
   risco que a regra "processo não é condenação" existe para evitar.
3. A aba "Processos" do próprio DivulgaCandContas (testada ao vivo) mostra
   **processos eleitorais da candidatura** (registro, prestação de contas,
   DRAP) — não histórico criminal/condenações da pessoa.

**Conclusão: não existe fonte oficial em lote, estruturada e segura, para
"processos e condenações" como o app promete hoje.** Decisão (do usuário,
após eu apresentar as opções): manter a seção "Processos e condenações"
como "não coletado nesta versão" (honesto, sem risco), e em vez disso
**adicionar só o dado 1 (Motivo da Cassação)**, numa seção **separada e
claramente rotulada**, com aviso explícito de que não é histórico criminal.

Implementado: nova tabela `motivo_indeferimento` (schema.sql, separada da
tabela `processo` para não confundir os dois conceitos), coleta via
`coleta_tse.py` (bloco novo, idempotente), exportado em `data.json` e
exibido no `index.html` numa seção própria com aviso âmbar. Contagens após
rodar para os 5 cargos (2026, RJ): Governador 1, Senador 3, Presidente 2,
Dep. Federal 66, Dep. Estadual 98 candidatos com motivo registrado.

O arquivo `certidao_criminal_2026_RJ.zip` (1,66 GB) não tem uso pelo motivo
acima — perguntei ao usuário se posso apagá-lo (não fiz isso sem
autorização, por regra do projeto). Ele optou por manter.

## 5g. Votações no Congresso (Câmara dos Deputados) — nova funcionalidade

A pedido do usuário ("cara votou o que? tipo escala 6x1"), implementado o
registro de **como cada candidato votou em PECs no Congresso**, para quem
já foi/é deputado federal.

**Fonte nova, fora do domínio TSE**: `dadosabertos.camara.leg.br` (API
oficial da Câmara dos Deputados). Expansão de escopo feita a pedido
explícito do usuário — mantém o mesmo princípio de "só fonte oficial".

**Vínculo candidato → deputado**: por CPF (não por nome), verificado
diretamente contra a API (testado com Benedita da Silva: CPF e nome
completo idênticos nas duas fontes). **50 dos nossos candidatos de 2026**
batem com algum deputado federal já eleito nesta legislatura.

**Seleção das ~30 pautas: 100% mecânica**, conforme decidido com o usuário
— nenhuma escolha temática humana:
1. Pega toda PEC apresentada na legislatura atual (57ª, desde 01/02/2023).
2. Para cada uma, procura a **votação de mérito** em Plenário (identificada
   pelo próprio texto oficial da Câmara: *"Aprovada, em primeiro/segundo
   turno, a Proposta de Emenda à Constituição..."*), ignorando votações de
   requerimento processual ("Aprovado o Requerimento...") e de redação
   final.
3. Quando a PEC foi **apensada** a outra (absorvida por uma "PEC
   principal"), segue a cadeia via o campo oficial `despacho` até achar
   onde a votação de mérito realmente aconteceu. Exemplo real encontrado:
   a PEC 8/2025 (jornada de 4 dias) foi desapensada da PEC 221/2019
   (principal) após esta ser aprovada em 27/05/2026 — o voto de cada
   deputado foi coletado na PEC 221/2019, não na 8/2025.

**Resultado**: das 76 PECs apresentadas nesta legislatura, **8 tiveram
votação de mérito registrada em Plenário até agora** (as outras 68 ainda
tramitam ou nunca chegaram ao Plenário — menos que os ~30 estimados
inicialmente, mas é o número real, sem forçar). Entre elas está a
**PEC 221/2019** (fim da escala 6x1 / redução de jornada), aprovada em
27/05/2026 com 461 votos a favor.

**Confirmado com a fonte bruta** (não só pela nossa exportação): o voto do
deputado Carlos Jordy (PL) na PEC 221/2019 foi checado diretamente via
`curl` na API da Câmara e bateu exatamente com o que nosso app mostra
("Sim").

**Números finais**: 50 parlamentares vinculados, 8 pautas, 305 votos
individuais registrados (só dos candidatos da nossa base, não de todos os
513 deputados).

**Limitações registradas na tela** (não escondidas):
- Só PECs (emendas constitucionais), não projetos de lei comuns (PLs) —
  por isso um deputado pode ter votado diferente numa PEC e num PL sobre o
  mesmo tema (ex: a PEC da jornada de trabalho é diferente do PL 1838/26
  que trata dos detalhes da escala 6x1 — só a PEC está coletada).
  Se quiser, dá pra estender a mesma lógica para PLs de alta relevância
  no futuro.
- Só Câmara dos Deputados — Senado Federal não expõe CPF em nenhum
  endpoint público, então não foi incluído (evita risco de homônimo).
- Só cobre quem é/foi deputado federal — não afeta candidatos a
  Governador/Presidente/Estadual que nunca passaram pela Câmara.

Script novo: `coleta_camara.py` (com cache local em `cache_camara/` pra não
bater na API à toa). Tabelas novas no schema: `parlamentar`, `pauta`,
`voto_parlamentar`.

## 7. Erros durante o processo (registrados, não escondidos)

- `HTTP 403 Forbidden` inicial em todo download via `cdn.tse.jus.br` (seção 1).
- Uma tentativa de navegação direta a um `.zip` pelo navegador interno da
  ferramenta falhou ("denied or failed") — não representa erro do site, é uma
  limitação da ferramenta de navegação usada para diagnóstico.
