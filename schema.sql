-- schema.sql - Voto Informado RJ 2026
-- Reconstruido a partir do uso real em coleta_tse.py, exportar_json.py,
-- validar_amostra.py e index.html (nenhum dado de candidato aqui, so
-- estrutura + tabela de referencia estatica "cargo").
--
-- Principios do projeto: fonte sempre TSE; processo != condenacao;
-- vinculo entre eleicoes so "confirmado_cpf" com CPF completo.

PRAGMA foreign_keys = ON;

-- Fontes oficiais usadas na coleta (hoje so o TSE).
CREATE TABLE fonte (
    id              INTEGER PRIMARY KEY,
    sigla           TEXT NOT NULL UNIQUE,
    nome            TEXT NOT NULL,
    url_base        TEXT NOT NULL,
    onde_verificar  TEXT
);

-- Tabela de referencia estatica (nomes de cargo para exibicao).
-- Codigos identicos ao dict CARGOS em coleta_tse.py.
CREATE TABLE cargo (
    codigo  TEXT PRIMARY KEY,
    nome    TEXT NOT NULL
);
INSERT INTO cargo (codigo, nome) VALUES
    ('PRES',    'Presidente da Republica'),
    ('GOV',     'Governador'),
    ('SEN',     'Senador'),
    ('DEP_FED', 'Deputado Federal'),
    ('DEP_EST', 'Deputado Estadual');

-- Uma linha por (ano, turno).
CREATE TABLE eleicao (
    id      INTEGER PRIMARY KEY,
    ano     INTEGER NOT NULL,
    turno   INTEGER NOT NULL DEFAULT 1,
    UNIQUE (ano, turno)
);

-- Pessoa fisica. Pode aparecer em varias candidaturas/eleicoes.
-- Vinculo entre candidaturas de anos diferentes so e "confirmado_cpf"
-- quando o CPF veio completo (11 digitos); senao "nao_confirmado"
-- (risco de homonimo - ver achar_pessoa() em coleta_tse.py).
CREATE TABLE pessoa (
    id                  INTEGER PRIMARY KEY,
    nome_completo       TEXT NOT NULL,
    nome_urna           TEXT,
    cpf                 TEXT UNIQUE,
    data_nascimento     TEXT,
    vinculo_confianca   TEXT NOT NULL CHECK (vinculo_confianca IN ('confirmado_cpf','nao_confirmado'))
);

-- Partidos (sigla e a chave natural usada no INSERT OR IGNORE).
CREATE TABLE partido (
    sigla   TEXT PRIMARY KEY,
    numero  TEXT,
    nome    TEXT
);

-- Uma candidatura = uma pessoa concorrendo a um cargo numa eleicao.
CREATE TABLE candidatura (
    id              INTEGER PRIMARY KEY,
    pessoa_id       INTEGER NOT NULL REFERENCES pessoa(id),
    eleicao_id      INTEGER NOT NULL REFERENCES eleicao(id),
    cargo_codigo    TEXT NOT NULL REFERENCES cargo(codigo),
    uf              TEXT NOT NULL,
    sq_candidato    TEXT NOT NULL,
    numero          TEXT,
    partido_sigla   TEXT REFERENCES partido(sigla),
    coligacao       TEXT,
    situacao        TEXT,
    resultado       TEXT,
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    url_origem      TEXT NOT NULL,
    data_consulta   TEXT NOT NULL,
    status_coleta   TEXT NOT NULL CHECK (status_coleta IN ('encontrado','nao_encontrado')),
    validado_por    TEXT,
    validado_em     TEXT,
    UNIQUE (eleicao_id, sq_candidato)
);
CREATE INDEX idx_candidatura_pessoa ON candidatura(pessoa_id);
CREATE INDEX idx_candidatura_cargo_uf ON candidatura(cargo_codigo, uf);

-- Bens declarados por candidatura. Uma linha "nao_encontrado" (sem valor)
-- e gravada quando o arquivo de bens foi lido com sucesso mas o candidato
-- nao tinha linhas - isso NAO deve ser confundido com patrimonio R$ 0.
CREATE TABLE patrimonio_bem (
    id              INTEGER PRIMARY KEY,
    candidatura_id  INTEGER NOT NULL REFERENCES candidatura(id),
    ordem           TEXT,
    tipo_bem        TEXT,
    descricao       TEXT,
    valor_reais     REAL,
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    url_origem      TEXT NOT NULL,
    data_consulta   TEXT NOT NULL,
    status_coleta   TEXT NOT NULL CHECK (status_coleta IN ('encontrado','nao_encontrado'))
);
CREATE INDEX idx_patrimonio_candidatura ON patrimonio_bem(candidatura_id);

-- Processos judiciais. So exportados para o site quando publicavel=1
-- (checagem humana), conforme exportar_json.py. Processo NAO e condenacao:
-- os valores de status_atual espelham exatamente o que index.html sabe exibir.
CREATE TABLE processo (
    id                          INTEGER PRIMARY KEY,
    pessoa_id                   INTEGER NOT NULL REFERENCES pessoa(id),
    numero_cnj                  TEXT,
    tribunal                    TEXT,
    natureza                    TEXT,
    status_atual                TEXT NOT NULL CHECK (status_atual IN (
                                    'em_andamento',
                                    'condenacao_1a_instancia',
                                    'condenacao_colegiada',
                                    'transitado_em_julgado_condenacao',
                                    'absolvicao',
                                    'arquivamento',
                                    'extincao_punibilidade',
                                    'status_desconhecido'
                                )),
    resultado_descricao         TEXT,
    data_ultima_movimentacao    TEXT,
    url_origem                  TEXT NOT NULL,
    data_consulta               TEXT NOT NULL,
    publicavel                  INTEGER NOT NULL DEFAULT 0 CHECK (publicavel IN (0,1))
);
CREATE INDEX idx_processo_pessoa ON processo(pessoa_id);

-- Log de cada rodada de coleta (por bloco: candidatura / patrimonio / processo).
-- pessoa_id fica NULL nos blocos de candidatura/patrimonio (coleta em lote);
-- e preenchido quando a coleta de processos, por pessoa, existir.
CREATE TABLE log_coleta (
    id              INTEGER PRIMARY KEY,
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    pessoa_id       INTEGER REFERENCES pessoa(id),
    bloco           TEXT NOT NULL,
    data_consulta   TEXT NOT NULL,
    resultado       TEXT NOT NULL,
    detalhe         TEXT
);
CREATE INDEX idx_log_coleta_bloco_pessoa ON log_coleta(bloco, pessoa_id);
