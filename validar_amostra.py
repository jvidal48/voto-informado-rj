#!/usr/bin/env python3
"""Fase 3 - Validacao por amostragem.
  python validar_amostra.py sortear --n 3            -> gera checklist_validacao.md (sorteio reproduzivel)
  python validar_amostra.py ok --sq 123456 --por "Joao Fernandes"   -> registra validacao humana
  python validar_amostra.py status                   -> quantos foram validados
Nada e marcado como validado sem voce rodar o comando 'ok' depois de conferir na fonte."""
import argparse, random, sqlite3
from datetime import datetime

ap = argparse.ArgumentParser(); ap.add_argument("acao", choices=["sortear", "ok", "status"])
ap.add_argument("--db", default="voto.db"); ap.add_argument("--n", type=int, default=3)
ap.add_argument("--seed", type=int, default=2026); ap.add_argument("--sq"); ap.add_argument("--por")
a = ap.parse_args(); db = sqlite3.connect(a.db)

if a.acao == "sortear":
    rows = db.execute("""SELECT c.sq_candidato, p.nome_completo, p.nome_urna, c.numero, c.partido_sigla,
        c.situacao, c.data_consulta, p.vinculo_confianca,
        (SELECT SUM(valor_reais) FROM patrimonio_bem b WHERE b.candidatura_id=c.id AND b.status_coleta='encontrado'),
        (SELECT COUNT(*) FROM patrimonio_bem b WHERE b.candidatura_id=c.id AND b.status_coleta='encontrado'
            AND IFNULL(b.descricao,'') NOT LIKE 'Candidato declarou nao possuir%')
        FROM candidatura c JOIN pessoa p ON p.id=c.pessoa_id JOIN eleicao e ON e.id=c.eleicao_id
        WHERE e.ano=2026 AND c.validado_por IS NULL ORDER BY c.sq_candidato""").fetchall()
    random.Random(a.seed).shuffle(rows)
    out = [f"# Checklist de validacao (gerado {datetime.now():%Y-%m-%d %H:%M})\n",
           "Fonte para conferir: https://divulgacandcontas.tse.jus.br (busque por nome/numero, ano 2026)\n"]
    for r in rows[:a.n]:
        sq, nome, urna, num, part, sit, dc, vinc, total, nb = r
        out.append(f"""## {nome} ({urna}) - SQ {sq}
- [ ] Nome completo igual ao do site: **{nome}**
- [ ] Numero: **{num}** | Partido: **{part}** | Situacao: **{sit}**
- [ ] Quantidade de bens: **{nb}** | Total nominal: **R$ {total if total is not None else 'nao encontrado'}**
- [ ] Coletado em {dc} (o site pode ter mudado desde entao)
- Vinculo de identidade: `{vinc}`
- Depois de conferir: `python validar_amostra.py ok --sq {sq} --por "SEU NOME"`
""")
    open("checklist_validacao.md", "w", encoding="utf-8").write("\n".join(out))
    print(f"checklist_validacao.md gerado com {min(a.n, len(rows))} candidatos")
elif a.acao == "ok":
    assert a.sq and a.por, "use --sq e --por"
    agora = datetime.now().astimezone().isoformat(timespec="seconds")
    n = db.execute("UPDATE candidatura SET validado_por=?, validado_em=? WHERE sq_candidato=?", (a.por, agora, a.sq)).rowcount
    db.commit(); print(f"{n} candidatura(s) marcada(s) como validada(s)" if n else "SQ nao encontrado")
else:
    t, v = db.execute("SELECT COUNT(*), COUNT(validado_por) FROM candidatura").fetchone()
    print(f"validados: {v} de {t}")
