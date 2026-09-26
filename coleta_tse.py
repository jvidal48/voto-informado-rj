#!/usr/bin/env python3
"""
Fase 2 - Coleta TSE (candidatos + bens) para o app de eleitores do RJ.

Fonte oficial: Portal de Dados Abertos do TSE
  https://dadosabertos.tse.jus.br/dataset/candidatos-2026
Arquivos (URLs listadas no proprio portal):
  https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_<ANO>.zip
  https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_<ANO>.zip

Uso (rode na SUA maquina, com internet):
  python coleta_tse.py --cargo GOV                     # 2026, RJ, governador
  python coleta_tse.py --cargo GOV --anos 2026 2022 2018   # inclui historico
  python coleta_tse.py --cargo GOV --zip-dir ./zips    # usa zips ja baixados (sem rede)

Principios (regras do projeto):
  * NUNCA inventa: se uma coluna esperada nao existe, o script PARA e mostra o cabecalho real.
  * Toda linha grava fonte + url + data_consulta + status_coleta.
  * Vinculo entre eleicoes so e 'confirmado_cpf' se o CPF vier completo (11 digitos).
    Caso contrario a pessoa e tratada como NAO confirmada (risco de homonimo).
"""
import argparse, csv, io, re, sqlite3, sys, zipfile, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
CARGOS = {  # codigo do schema -> texto do TSE (DS_CARGO)
    "PRES": "PRESIDENTE", "GOV": "GOVERNADOR", "SEN": "SENADOR",
    "DEP_FED": "DEPUTADO FEDERAL", "DEP_EST": "DEPUTADO ESTADUAL",
}
NULOS = {"#NULO", "#NULO#", "#NE", "#NE#", "", "-1", "-3"}

# Colunas obrigatorias (nome oficial do layout do TSE). Se faltar, aborta.
COLS_CAND = ["SQ_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "DS_CARGO", "SG_UF",
             "NR_CANDIDATO", "SG_PARTIDO", "DS_SITUACAO_CANDIDATURA"]
COLS_CAND_OPC = ["NR_CPF_CANDIDATO", "DT_NASCIMENTO", "NR_PARTIDO", "NM_PARTIDO",
                 "NM_COLIGACAO", "DS_SIT_TOT_TURNO", "NR_TURNO"]
# bens: aceita variacoes de nome entre eleicoes
BEM_ALT = {
    "SQ_CANDIDATO": ["SQ_CANDIDATO"],
    "ORDEM": ["NR_ORDEM_CANDIDATO", "NR_ORDEM_BEM_CANDIDATO"],
    "TIPO": ["DS_TIPO_BEM_CANDIDATO"],
    "DESC": ["DS_BEM_CANDIDATO"],
    "VALOR": ["VR_BEM_CANDIDATO"],
}


def agora():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def limpa(v):
    v = (v or "").strip()
    return None if v.upper() in NULOS else v


def baixar(nome, ano, pasta):
    """Baixa <nome>_<ano>.zip (ou usa o que ja esta em `pasta`). Retorna (Path, url)."""
    url = f"{BASE}/{nome}/{nome}_{ano}.zip"
    destino = pasta / f"{nome}_{ano}.zip"
    if not destino.exists():
        print(f"  baixando {url}")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
            f.write(r.read())
    return destino, url


def abrir_csv(zip_path, uf):
    """Devolve (nome_do_csv, DictReader) do arquivo da UF (ou BRASIL p/ presidente)."""
    z = zipfile.ZipFile(zip_path)
    csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
    alvo = [n for n in csvs if re.search(rf"_{uf}\.csv$", n, re.I)]
    if not alvo:  # alguns anos publicam um unico CSV nacional
        alvo = [n for n in csvs if re.search(r"_(BRASIL|BR)\.csv$", n, re.I)] or csvs
    nome = alvo[0]
    txt = io.TextIOWrapper(z.open(nome), encoding="latin-1", newline="")
    return nome, csv.DictReader(txt, delimiter=";", quotechar='"')


def exige_colunas(reader, obrigatorias, arquivo):
    falta = [c for c in obrigatorias if c not in (reader.fieldnames or [])]
    if falta:
        sys.exit(f"ERRO: colunas ausentes em {arquivo}: {falta}\n"
                 f"Cabecalho real do arquivo: {reader.fieldnames}\n"
                 f"Nao vou adivinhar. Ajuste COLS_CAND/BEM_ALT apos conferir o layout oficial.")


def cpf_valido(v):
    d = re.sub(r"\D", "", v or "")
    return d if (len(d) == 11 and "*" not in (v or "")) else None


def num(v):
    v = limpa(v)
    if v is None:
        return None
    try:
        return float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
    except ValueError:
        return None


def achar_pessoa(db, nome, nasc, cpf):
    """Ligacao entre eleicoes: por CPF completo; senao nome+nascimento (NAO confirmado)."""
    if cpf:
        r = db.execute("SELECT id FROM pessoa WHERE cpf=?", (cpf,)).fetchone()
        if r: return r[0]
        db.execute("INSERT INTO pessoa(nome_completo,cpf,data_nascimento,vinculo_confianca) "
                   "VALUES(?,?,?,'confirmado_cpf')", (nome, cpf, nasc))
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = db.execute("SELECT id FROM pessoa WHERE cpf IS NULL AND nome_completo=? "
                   "AND IFNULL(data_nascimento,'')=IFNULL(?,'')", (nome, nasc)).fetchone()
    if r: return r[0]
    db.execute("INSERT INTO pessoa(nome_completo,data_nascimento,vinculo_confianca) "
               "VALUES(?,?,'nao_confirmado')", (nome, nasc))
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def coleta_ano(db, ano, cargo, uf, pasta, fonte_id):
    ds_cargo = CARGOS[cargo]
    uf_alvo = "BR" if cargo == "PRES" else uf
    print(f"[{ano}] {ds_cargo} / {uf_alvo}")
    zc, url_c = baixar("consulta_cand", ano, pasta)
    nome_c, rd = abrir_csv(zc, "BRASIL" if cargo == "PRES" else uf)
    exige_colunas(rd, COLS_CAND, nome_c)
    tem = lambda c: c in rd.fieldnames
    db.execute("INSERT OR IGNORE INTO eleicao(ano,turno) VALUES(?,1)", (ano,))
    eleicao_id = db.execute("SELECT id FROM eleicao WHERE ano=? AND turno=1", (ano,)).fetchone()[0]
    data = agora()
    mapa_sq, n = {}, 0
    for row in rd:
        if (row["DS_CARGO"] or "").strip().upper() != ds_cargo:
            continue
        if cargo != "PRES" and (row["SG_UF"] or "").strip().upper() != uf_alvo:
            continue
        cpf = cpf_valido(row.get("NR_CPF_CANDIDATO")) if tem("NR_CPF_CANDIDATO") else None
        nome = limpa(row["NM_CANDIDATO"])
        nasc = limpa(row.get("DT_NASCIMENTO")) if tem("DT_NASCIMENTO") else None
        pid = achar_pessoa(db, nome, nasc, cpf)
        db.execute("UPDATE pessoa SET nome_urna=? WHERE id=?", (limpa(row["NM_URNA_CANDIDATO"]), pid))
        sg = limpa(row["SG_PARTIDO"])
        if sg:
            db.execute("INSERT OR IGNORE INTO partido(sigla,numero,nome) VALUES(?,?,?)",
                       (sg, limpa(row.get("NR_PARTIDO")), limpa(row.get("NM_PARTIDO"))))
        sq = limpa(row["SQ_CANDIDATO"])
        # upsert (nao "INSERT OR REPLACE"): precisa preservar o id da candidatura
        # entre execucoes, porque patrimonio_bem ja referencia esse id via FK -
        # REPLACE apaga+recria a linha com id novo e quebra essa referencia.
        db.execute("""INSERT INTO candidatura
            (pessoa_id,eleicao_id,cargo_codigo,uf,sq_candidato,numero,partido_sigla,coligacao,
             situacao,resultado,fonte_id,url_origem,data_consulta,status_coleta)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'encontrado')
            ON CONFLICT(eleicao_id,sq_candidato) DO UPDATE SET
                pessoa_id=excluded.pessoa_id, cargo_codigo=excluded.cargo_codigo, uf=excluded.uf,
                numero=excluded.numero, partido_sigla=excluded.partido_sigla,
                coligacao=excluded.coligacao, situacao=excluded.situacao,
                resultado=excluded.resultado, fonte_id=excluded.fonte_id,
                url_origem=excluded.url_origem, data_consulta=excluded.data_consulta,
                status_coleta=excluded.status_coleta""",
            (pid, eleicao_id, cargo, uf_alvo, sq, limpa(row["NR_CANDIDATO"]), sg,
             limpa(row.get("NM_COLIGACAO")), limpa(row["DS_SITUACAO_CANDIDATURA"]),
             limpa(row.get("DS_SIT_TOT_TURNO")), fonte_id, url_c, data))
        mapa_sq[sq] = db.execute("SELECT id FROM candidatura WHERE eleicao_id=? AND sq_candidato=?",
                                 (eleicao_id, sq)).fetchone()[0]
        n += 1
    db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
               (fonte_id, "candidatura", data, "encontrado" if n else "nao_encontrado",
                f"{ano} {cargo} {uf_alvo}: {n} candidaturas em {nome_c}"))
    print(f"  candidaturas: {n}")
    if not n:
        return

    # ---- situacao de julgamento da candidatura (arquivo complementar) ----
    # DS_SITUACAO_CANDIDATURA do arquivo principal costuma vir '#NE' antes da
    # eleicao terminar; DS_SITUACAO_CANDIDATO_TOT do complementar traz o status
    # real (DEFERIDO / INDEFERIDO ...), conferido manualmente contra o
    # DivulgaCandContas. So preenche quando o valor principal esta vazio.
    try:
        zs, url_s = baixar("consulta_cand_complementar", ano, pasta)
    except Exception as e:
        db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
                   (fonte_id, "situacao_candidatura", data, "erro", f"{ano}: {e}"))
        print(f"  AVISO: situacao de candidatura {ano} nao verificada ({e})")
    else:
        nome_s, rs = abrir_csv(zs, "BRASIL" if cargo == "PRES" else uf)
        exige_colunas(rs, ["SQ_CANDIDATO", "DS_SITUACAO_CANDIDATO_TOT"], nome_s)
        atualizados = 0
        for row in rs:
            sq = limpa(row["SQ_CANDIDATO"])
            if sq not in mapa_sq:
                continue
            sit = limpa(row["DS_SITUACAO_CANDIDATO_TOT"])
            if sit:
                atualizados += db.execute("UPDATE candidatura SET situacao=? WHERE id=? AND situacao IS NULL",
                                           (sit, mapa_sq[sq])).rowcount
        db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
                   (fonte_id, "situacao_candidatura", data, "encontrado" if atualizados else "nao_encontrado",
                    f"{ano}: {atualizados} candidaturas com situacao preenchida via {nome_s}"))
        print(f"  situacao de candidatura preenchida: {atualizados}/{len(mapa_sq)}")

    # ---- bens ----
    try:
        zb, url_b = baixar("bem_candidato", ano, pasta)
    except Exception as e:  # sem rede / arquivo inexistente => 'nao_verificado', nunca 'zero'
        db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
                   (fonte_id, "patrimonio", data, "erro", f"{ano}: {e}"))
        print(f"  AVISO: bens {ano} nao verificados ({e})")
        return
    nome_b, rb = abrir_csv(zb, "BRASIL" if cargo == "PRES" else uf)
    # limpa bens de execucoes anteriores destas candidaturas (senao reexecutar
    # o script duplica cada bem a cada rodada)
    db.executemany("DELETE FROM patrimonio_bem WHERE candidatura_id=?",
                    [(cid,) for cid in mapa_sq.values()])
    col = {}
    for k, alts in BEM_ALT.items():
        achada = next((a for a in alts if a in (rb.fieldnames or [])), None)
        if achada is None and k in ("SQ_CANDIDATO", "VALOR"):
            exige_colunas(rb, alts, nome_b)
        col[k] = achada
    com_bem = set()
    for row in rb:
        sq = limpa(row[col["SQ_CANDIDATO"]])
        if sq not in mapa_sq:
            continue
        com_bem.add(sq)
        db.execute("""INSERT INTO patrimonio_bem(candidatura_id,ordem,tipo_bem,descricao,valor_reais,
                      fonte_id,url_origem,data_consulta,status_coleta) VALUES(?,?,?,?,?,?,?,?,'encontrado')""",
                   (mapa_sq[sq], limpa(row[col["ORDEM"]]) if col["ORDEM"] else None,
                    limpa(row[col["TIPO"]]) if col["TIPO"] else None,
                    limpa(row[col["DESC"]]) if col["DESC"] else None,
                    num(row[col["VALOR"]]), fonte_id, url_b, data))
    # Arquivo lido com sucesso e candidato sem linhas => 'nao_encontrado' (NAO e o mesmo que R$ 0)
    for sq, cid in mapa_sq.items():
        if sq not in com_bem:
            db.execute("""INSERT INTO patrimonio_bem(candidatura_id,fonte_id,url_origem,data_consulta,status_coleta)
                          VALUES(?,?,?,?,'nao_encontrado')""", (cid, fonte_id, url_b, data))
    db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
               (fonte_id, "patrimonio", data, "encontrado",
                f"{ano}: {len(com_bem)} de {len(mapa_sq)} candidatos com bens declarados"))
    print(f"  candidatos com bens declarados: {len(com_bem)}/{len(mapa_sq)}")

    # ---- motivo de indeferimento/cassacao do registro (NAO e historico criminal -
    # e sobre o registro da candidatura em si; ver comentario no schema.sql) ----
    try:
        zm, url_m = baixar("motivo_cassacao", ano, pasta)
    except Exception as e:
        db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
                   (fonte_id, "motivo_indeferimento", data, "erro", f"{ano}: {e}"))
        print(f"  AVISO: motivo de indeferimento {ano} nao verificado ({e})")
    else:
        nome_m, rm = abrir_csv(zm, "BRASIL" if cargo == "PRES" else uf)
        exige_colunas(rm, ["SQ_CANDIDATO", "DS_TP_MOTIVO", "DS_MOTIVO"], nome_m)
        db.executemany("DELETE FROM motivo_indeferimento WHERE candidatura_id=?",
                        [(cid,) for cid in mapa_sq.values()])
        n_motivos = 0
        for row in rm:
            sq = limpa(row["SQ_CANDIDATO"])
            if sq not in mapa_sq:
                continue
            db.execute("""INSERT INTO motivo_indeferimento(candidatura_id,nr_processo,tipo_motivo,motivo,
                          fonte_id,url_origem,data_consulta) VALUES(?,?,?,?,?,?,?)""",
                       (mapa_sq[sq], limpa(row.get("NR_PROCESSO")), limpa(row["DS_TP_MOTIVO"]),
                        limpa(row["DS_MOTIVO"]), fonte_id, url_m, data))
            n_motivos += 1
        db.execute("INSERT INTO log_coleta(fonte_id,bloco,data_consulta,resultado,detalhe) VALUES(?,?,?,?,?)",
                   (fonte_id, "motivo_indeferimento", data, "encontrado" if n_motivos else "nao_encontrado",
                    f"{ano}: {n_motivos} motivos de indeferimento/cassacao em {nome_m}"))
        print(f"  motivos de indeferimento/cassacao: {n_motivos}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cargo", required=True, choices=CARGOS)
    ap.add_argument("--uf", default="RJ")
    ap.add_argument("--anos", nargs="+", type=int, default=[2026])
    ap.add_argument("--db", default="voto.db")
    ap.add_argument("--schema", default="schema.sql")
    ap.add_argument("--zip-dir", default="zips")
    a = ap.parse_args()

    pasta = Path(a.zip_dir); pasta.mkdir(exist_ok=True)
    db = sqlite3.connect(a.db)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='fonte'").fetchone():
        db.executescript(Path(a.schema).read_text(encoding="utf-8"))
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""INSERT OR IGNORE INTO fonte(sigla,nome,url_base,onde_verificar) VALUES
        ('TSE','Tribunal Superior Eleitoral - Dados Abertos','https://dadosabertos.tse.jus.br',
         'Confira em https://divulgacandcontas.tse.jus.br (DivulgaCandContas)')""")
    fonte_id = db.execute("SELECT id FROM fonte WHERE sigla='TSE'").fetchone()[0]
    for ano in a.anos:
        coleta_ano(db, ano, a.cargo, a.uf, pasta, fonte_id)
        db.commit()
    db.close()
    print("Concluido. CONFIRA manualmente uma amostra no DivulgaCandContas antes de usar.")


if __name__ == "__main__":
    main()
