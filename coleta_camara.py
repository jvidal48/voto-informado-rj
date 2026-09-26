#!/usr/bin/env python3
"""
Fase 4 - Coleta de votacoes nominais da Camara dos Deputados (dados abertos).

Fonte oficial: https://dadosabertos.camara.leg.br (dominio DIFERENTE do TSE -
usado aqui a pedido explicito do usuario, para a funcionalidade de "como o
candidato votou no Congresso"). So cobre quem JA FOI ou E deputado federal
(vinculo por CPF, confirmado contra o registro do TSE - nunca por nome).

Selecao das "pautas": 100% MECANICA. Pega toda PEC apresentada na legislatura
atual que tenha uma votacao de MERITO registrada em Plenario (identificada
pelo texto oficial da propria Camara: "Aprovada, em primeiro/segundo turno,
a Proposta de Emenda a Constituicao..."), resolvendo apensacao quando a PEC
foi absorvida por outra (campo "despacho"). NAO ha escolha tematica humana -
isso e proposital, para nao correr risco de parecer viesado.

Uso:
  python coleta_camara.py                 # roda tudo (deputados + pautas + votos)
  python coleta_camara.py --so-cache-deputados   # so atualiza cache de deputados/CPF

Cache local em cache_camara/ (JSON por chamada) para nao bater na API toda
hora sem necessidade - apague a pasta se quiser forcar atualizacao total.
"""
import argparse, json, re, sqlite3, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://dadosabertos.camara.leg.br/api/v2"
UA = {"User-Agent": "voto-informado-rj/0.1 (contato: projeto de transparencia eleitoral RJ)"}
CACHE = Path("cache_camara")


def agora():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get(url, cache_key=None):
    """GET json com cache local em disco (nunca reinventa dado: se a API falhar
    e nao houver cache, propaga o erro real)."""
    if cache_key:
        f = CACHE / f"{cache_key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if cache_key:
        CACHE.mkdir(exist_ok=True)
        (CACHE / f"{cache_key}.json").write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.12)  # nao martelar a API publica
    return data


def legislatura_atual():
    d = get(f"{BASE}/legislaturas?itens=1&ordem=DESC&ordenarPor=id", "legislatura_atual")
    leg = d["dados"][0]
    return leg["id"], leg["dataInicio"]


PADRAO_MERITO = re.compile(r"Proposta de Emenda [aà] Constitui[çc][ãa]o", re.I)
PADRAO_REQUERIMENTO = re.compile(r"^(Aprovad|Rejeitad)[oa] (o|a) [Rr]equerimento", re.I)
PADRAO_REDACAO_FINAL = re.compile(r"Reda[çc][ãa]o Final", re.I)
PADRAO_TURNO = re.compile(r"em (primeiro|segundo) turno", re.I)
PADRAO_DESAPENSACAO = re.compile(r"PEC n[ºo°]\s*(\d+),?\s*de\s*(\d{4}),?\s*principal", re.I)


def votacao_de_merito(votacoes):
    """De uma lista de votacoes de uma proposicao, acha a votacao de MERITO
    (nao processual). Prefere 2o turno > 1o turno > qualquer uma que bata
    no padrao (para proposicoes que so precisam de 1 votacao)."""
    candidatas = [v for v in votacoes
                  if PADRAO_MERITO.search(v.get("descricao", ""))
                  and not PADRAO_REQUERIMENTO.match(v.get("descricao", ""))
                  and not PADRAO_REDACAO_FINAL.search(v.get("descricao", ""))]
    if not candidatas:
        return None
    segundo = [v for v in candidatas if re.search(r"segundo turno", v["descricao"], re.I)]
    if segundo:
        return segundo[0]
    primeiro = [v for v in candidatas if re.search(r"primeiro turno", v["descricao"], re.I)]
    if primeiro:
        return primeiro[0]
    return candidatas[0]


def resolver_pec(prop_id, visitados=None):
    """Segue a cadeia de apensacao (via despacho) ate achar a PEC que
    realmente teve a votacao de merito, ou None se nenhuma foi encontrada."""
    visitados = visitados or set()
    if prop_id in visitados:
        return None
    visitados.add(prop_id)
    prop = get(f"{BASE}/proposicoes/{prop_id}", f"prop_{prop_id}")["dados"]
    votacoes = get(f"{BASE}/proposicoes/{prop_id}/votacoes", f"votacoes_{prop_id}")["dados"]
    v = votacao_de_merito(votacoes)
    if v:
        return prop, v
    despacho = (prop.get("statusProposicao") or {}).get("despacho", "") or ""
    m = PADRAO_DESAPENSACAO.search(despacho)
    if m:
        numero_principal, ano_principal = m.group(1), m.group(2)
        busca = get(f"{BASE}/proposicoes?siglaTipo=PEC&numero={numero_principal}&ano={ano_principal}",
                    f"busca_pec_{numero_principal}_{ano_principal}")["dados"]
        if busca:
            return resolver_pec(busca[0]["id"], visitados)
    return None


def coletar_pautas(db, fonte_id):
    leg_id, leg_inicio = legislatura_atual()
    print(f"Legislatura atual: {leg_id} (desde {leg_inicio})")
    pecs = get(f"{BASE}/proposicoes?siglaTipo=PEC&itens=100&ordem=DESC&ordenarPor=id"
               f"&dataApresentacaoInicio={leg_inicio}", "pecs_legislatura_atual")["dados"]
    print(f"PECs apresentadas na legislatura: {len(pecs)}")
    resolvidas = {}  # id_votacao -> (prop, votacao)
    for i, p in enumerate(pecs, 1):
        print(f"  [{i}/{len(pecs)}] PEC {p['numero']}/{p['ano']}...", end=" ")
        try:
            r = resolver_pec(p["id"])
        except urllib.error.HTTPError as e:
            print(f"ERRO: {e}"); continue
        if r:
            prop, v = r
            resolvidas.setdefault(v["id"], (prop, v))
            print(f"-> votacao de merito {v['id']} ({v.get('data')})")
        else:
            print("sem votacao de merito (ainda em tramitacao ou nunca foi a plenario)")
    print(f"\nPautas distintas com votacao de merito: {len(resolvidas)}")

    data = agora()
    ids_pauta = {}
    for votacao_id, (prop, v) in resolvidas.items():
        turno = "2" if re.search(r"segundo turno", v["descricao"], re.I) else \
                ("1" if re.search(r"primeiro turno", v["descricao"], re.I) else None)
        placar = None
        m = re.search(r"Sim:\s*(\d+);\s*N[ãa]o:\s*(\d+)", v["descricao"])
        if m:
            placar = f"Sim: {m.group(1)} / Não: {m.group(2)}"
        cur = db.execute("""INSERT INTO pauta(casa,tipo,numero,ano,ementa,turno,id_votacao_externo,
            data_votacao,aprovada,placar,fonte_id,url_origem,data_consulta)
            VALUES('camara','PEC',?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(casa,id_votacao_externo) DO UPDATE SET
                ementa=excluded.ementa, turno=excluded.turno, data_votacao=excluded.data_votacao,
                aprovada=excluded.aprovada, placar=excluded.placar, data_consulta=excluded.data_consulta
            RETURNING id""",
            (prop["numero"], prop["ano"], prop["ementa"], turno, votacao_id, v.get("data"),
             v.get("aprovacao"), placar, fonte_id, prop["uri"], data))
        ids_pauta[votacao_id] = cur.fetchone()[0]
    db.commit()
    return ids_pauta


def coletar_deputados_cpf(fonte_id, forcar=False):
    """Retorna {cpf: {'id':..,'nome_civil':..}} de todos os deputados que ja
    passaram pela Camara na legislatura atual (atuais + afastados/suplentes)."""
    leg_id, _ = legislatura_atual()
    lista = get(f"{BASE}/deputados?idLegislatura={leg_id}&itens=100", f"deputados_leg_{leg_id}")["dados"]
    pagina = 2
    while True:
        d = get(f"{BASE}/deputados?idLegislatura={leg_id}&itens=100&pagina={pagina}",
                f"deputados_leg_{leg_id}_p{pagina}")["dados"]
        if not d:
            break
        lista.extend(d)
        pagina += 1
    print(f"Deputados na legislatura {leg_id}: {len(lista)}")
    cpf_map = {}
    for i, dep in enumerate(lista, 1):
        det = get(f"{BASE}/deputados/{dep['id']}", f"deputado_{dep['id']}")["dados"]
        cpf = re.sub(r"\D", "", det.get("cpf") or "")
        if len(cpf) == 11:
            cpf_map[cpf] = {"id": dep["id"], "nome_civil": det.get("nomeCivil") or dep["nome"]}
        if i % 100 == 0:
            print(f"  ...{i}/{len(lista)} deputados consultados")
    print(f"Deputados com CPF valido: {len(cpf_map)}")
    return cpf_map


def vincular_parlamentares(db, cpf_map, fonte_id):
    data = agora()
    vinculados = {}
    for row in db.execute("SELECT id, cpf FROM pessoa WHERE cpf IS NOT NULL"):
        pessoa_id, cpf = row
        dep = cpf_map.get(cpf)
        if not dep:
            continue
        cur = db.execute("""INSERT INTO parlamentar(pessoa_id,casa,id_externo,nome_civil,fonte_id,url_origem,data_consulta)
            VALUES(?,'camara',?,?,?,?,?)
            ON CONFLICT(pessoa_id) DO UPDATE SET id_externo=excluded.id_externo,
                nome_civil=excluded.nome_civil, data_consulta=excluded.data_consulta
            RETURNING id""",
            (pessoa_id, dep["id"], dep["nome_civil"], fonte_id,
             f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep['id']}", data))
        vinculados[dep["id"]] = cur.fetchone()[0]
    db.commit()
    print(f"Candidatos vinculados a deputados federais (por CPF): {len(vinculados)}")
    return vinculados


def coletar_votos(db, ids_pauta, vinculados, fonte_id):
    data = agora()
    total = 0
    for votacao_id, pauta_id in ids_pauta.items():
        votos = get(f"{BASE}/votacoes/{votacao_id}/votos", f"votos_{votacao_id}")["dados"]
        db.execute("DELETE FROM voto_parlamentar WHERE pauta_id=?", (pauta_id,))
        for vt in votos:
            id_dep = vt["deputado_"]["id"]
            parlamentar_id = vinculados.get(id_dep)
            if not parlamentar_id:
                continue
            db.execute("""INSERT INTO voto_parlamentar(parlamentar_id,pauta_id,voto,fonte_id,url_origem,data_consulta)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(parlamentar_id,pauta_id) DO UPDATE SET voto=excluded.voto, data_consulta=excluded.data_consulta""",
                (parlamentar_id, pauta_id, vt["tipoVoto"], fonte_id,
                 f"https://dadosabertos.camara.leg.br/api/v2/votacoes/{votacao_id}/votos", data))
            total += 1
    db.commit()
    print(f"Votos registrados (so de candidatos da nossa base): {total}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="voto.db")
    ap.add_argument("--so-cache-deputados", action="store_true")
    a = ap.parse_args()

    db = sqlite3.connect(a.db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""INSERT OR IGNORE INTO fonte(sigla,nome,url_base,onde_verificar) VALUES
        ('CAMARA','Camara dos Deputados - Dados Abertos','https://dadosabertos.camara.leg.br',
         'Confira em https://www.camara.leg.br (pagina do deputado / da proposicao)')""")
    fonte_id = db.execute("SELECT id FROM fonte WHERE sigla='CAMARA'").fetchone()[0]

    cpf_map = coletar_deputados_cpf(fonte_id)
    if a.so_cache_deputados:
        db.close(); return
    vinculados = vincular_parlamentares(db, cpf_map, fonte_id)
    if not vinculados:
        print("Nenhum candidato da base bate por CPF com deputados federais. Nada a fazer.")
        db.close(); return
    ids_pauta = coletar_pautas(db, fonte_id)
    coletar_votos(db, ids_pauta, vinculados, fonte_id)
    db.close()
    print("Concluido.")


if __name__ == "__main__":
    main()
