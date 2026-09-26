#!/usr/bin/env python3
"""Exporta o SQLite para data.json (o app le so este arquivo).
Uso: python exportar_json.py --db voto.db --cargos GOV SEN PRES --ano 2026 --saida data.json
Regras: so exporta o que existe no banco; processos NUNCA sao exportados sem publicavel=1."""
import argparse, json, sqlite3
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="voto.db")
ap.add_argument("--cargos", nargs="+", default=["GOV"])
ap.add_argument("--ano", type=int, default=2026); ap.add_argument("--saida", default="data.json")
a = ap.parse_args()
db = sqlite3.connect(a.db); db.row_factory = sqlite3.Row
q = lambda s, p=(): [dict(r) for r in db.execute(s, p)]

cargos_out = {}
for cargo in a.cargos:
    nome_cargo = db.execute("SELECT nome FROM cargo WHERE codigo=?", (cargo,)).fetchone()
    cands = q("""SELECT c.id cid, p.id pid, p.nome_completo, p.nome_urna, p.vinculo_confianca,
                 c.numero, c.partido_sigla partido, c.coligacao, c.situacao, c.sq_candidato,
                 c.url_origem, c.data_consulta, c.validado_por, c.validado_em
                 FROM candidatura c JOIN pessoa p ON p.id=c.pessoa_id
                 JOIN eleicao e ON e.id=c.eleicao_id
                 WHERE c.cargo_codigo=? AND e.ano=? ORDER BY p.nome_urna""", (cargo, a.ano))
    for c in cands:
        c["candidaturas_anteriores"] = q("""SELECT e.ano, cg.nome cargo, x.partido_sigla partido, x.resultado, x.situacao,
            x.data_consulta FROM candidatura x JOIN eleicao e ON e.id=x.eleicao_id JOIN cargo cg ON cg.codigo=x.cargo_codigo
            WHERE x.pessoa_id=? AND e.ano<>? ORDER BY e.ano DESC""", (c["pid"], a.ano))
        c["patrimonio"] = q("""SELECT e.ano, SUM(b.valor_reais) total_nominal,
            SUM(b.status_coleta='encontrado' AND IFNULL(b.descricao,'') NOT LIKE 'Candidato declarou nao possuir%') n_bens, MAX(b.status_coleta) status_coleta,
            MAX(b.url_origem) url_origem, MAX(b.data_consulta) data_consulta
            FROM patrimonio_bem b JOIN candidatura x ON x.id=b.candidatura_id JOIN eleicao e ON e.id=x.eleicao_id
            WHERE x.pessoa_id=? GROUP BY e.ano ORDER BY e.ano""", (c["pid"],))
        c["bens"] = q("""SELECT tipo_bem, descricao, valor_reais FROM patrimonio_bem
            WHERE candidatura_id=? AND status_coleta='encontrado' ORDER BY valor_reais DESC""", (c["cid"],))
        # processos: so os publicaveis (vinculo confirmado + validado por humano)
        c["processos"] = q("""SELECT numero_cnj, tribunal, natureza, status_atual, resultado_descricao,
            data_ultima_movimentacao, url_origem, data_consulta FROM processo
            WHERE pessoa_id=? AND publicavel=1""", (c["pid"],))
        c["processos_coletados"] = bool(q("SELECT 1 FROM log_coleta WHERE bloco='processo' AND pessoa_id=? LIMIT 1", (c["pid"],)))
        del c["cid"], c["pid"]
    cargos_out[cargo] = {"nome": nome_cargo[0] if nome_cargo else cargo, "candidatos": cands}
    print(f"{cargo}: {len(cands)} candidatos exportados")

json.dump({"gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
           "ano": a.ano, "cargos": cargos_out},
          open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"total exportado para {a.saida}")
