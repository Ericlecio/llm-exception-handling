"""
Gera as planilhas da avaliação manual por PARES e valida o sorteio (versão 2.2).

Unidade de avaliação: o par (função, modelo), com os dois handlers gerados para
a mesma função pelo mesmo modelo, um com o prompt padrão e outro com o prompt QG.

O que o script faz:
  1. Lê o benchmark (data/balanced_sample.csv) e os handlers extraídos (per_sample.csv).
  2. Define os pares elegíveis: os 6 handlers da função válidos, o handler do
     desenvolvedor localizável no código original, e a função fora do piloto.
  3. Calcula o tamanho mínimo da amostra (Cochran, correção para população finita).
  4. Sorteia, com semente fixa e de forma estratificada proporcional (modelo × grupo
     do Azure SDK), uma amostra completa (padrão: 287 pares) numa ordem aleatória.
     A amostra reduzida (padrão: 120 pares) são os primeiros pares dessa ordem,
     portanto está contida na completa.
  5. Gera, para cada amostra, uma pasta com uma planilha cega por avaliador,
     e um arquivo-chave único.
  6. Valida o sorteio: reprodutibilidade, tamanhos, aninhamento, exclusão do piloto,
     estratificação, cegamento, integridade dos itens e representatividade.

Uso (a partir da raiz do repositório):
    python llm/manual_evaluation/sample_manual_evaluation.py
    python llm/manual_evaluation/sample_manual_evaluation.py --verificar

Saídas (em llm/output/manual_evaluation/main/):
    sample_120_pairs/<avaliador>.xlsx
    sample_287_pairs/<avaliador>.xlsx
    item_key.xlsx        chave item -> modelo/condição, log e validação
    sampling.json                parâmetros, hashes das entradas e pares sorteados
"""

import argparse
import ast
import hashlib
import json
import math
import os
import sys
import textwrap
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

VERSAO = "2.2"
MODELOS = ["claude-haiku-4-5", "gemini-3-flash-preview", "gpt-4o-mini"]
CONDICOES = ["style-default", "style-qg-default"]
MARCA_AZURE = "StreamConsumedError"
PALAVRAS_PROIBIDAS = ["claude", "gemini", "gpt", "style-", "baseline", "qg", "haiku"]

FONTE, FONTE_CODIGO = "Arial", "Courier New"
COR_CABECALHO, COR_PREENCHER, COR_GRUPO = "D9D9D9", "FFF2CC", "F2F2F2"
BORDA = Border(*(Side(style="thin", color="BFBFBF"),) * 4)

REGRAS = [  # regras acordadas na calibração do piloto (texto final)
    ("Regra 1", "1a. Tipo: de onde vem a exceção",
     "Responda Sim quando for possível apontar a instrução do try que pode lançar a exceção capturada, por uma de duas "
     "origens: (a) o próprio código da função (por exemplo, int(v) lança ValueError); ou (b) o comportamento documentado "
     "da biblioteca chamada (por exemplo, Model.objects.get lança DoesNotExist). Se não for possível apontar a instrução "
     "por nenhuma das duas origens, responda Não é possível determinar.",
     "I3329 (origem documentada) e I4196 (origem não identificada)"),
    ("Regra 2", "1b. Reação: relançar",
     "Relançar o erro, ou embrulhá-lo numa nova exceção e relançar, é apropriado quando a função deve propagar o erro "
     "para quem a chamou. É inadequado quando impede uma etapa que o próprio código executaria depois de capturar o erro, "
     "como um mapeamento, um valor padrão ou uma limpeza.",
     "I7822"),
    ("Regra 3", "1b. Reação: erro anunciado pela função",
     "Se a função indica um caso de erro esperado (por exemplo, encerrar com Ctrl-C) e o handler não o cobre, "
     "a reação é inadequada (1b = Não).",
     "I5109"),
    ("Regra 4", "Consistência entre itens",
     "Handlers idênticos da mesma função recebem as mesmas respostas em 1a, 1b e na nota, mesmo que estejam em "
     "grupos diferentes.",
     "I6697 e I8477"),
]


# --------------------------------------------------------------------------- #
# Dados
# --------------------------------------------------------------------------- #
def normalizar(texto):
    return str(texto).replace("\r\n", "\n").replace("\r", "\n")


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def carregar(caminho_base, caminho_per_sample):
    base = pd.read_csv(caminho_base)
    base = base[base["n_try_except"] == 1].reset_index(drop=True)
    base["func_body_n"] = base["func_body"].apply(normalizar)
    base["ref_handler"] = base["str_captures_except"].apply(lambda s: [normalizar(x) for x in ast.literal_eval(s)])
    ps = pd.read_csv(caminho_per_sample)
    erros = []
    for m in MODELOS:
        for c in CONDICOES:
            g = ps[(ps["model"] == m) & (ps["prompt_type"] == c)].sort_values("sample_id")
            if len(g) != len(base):
                erros.append(f"{m}/{c}: {len(g)} linhas, esperado {len(base)}")
            elif not (g["function"].astype(str).values == base["function"].astype(str).values).all():
                erros.append(f"{m}/{c}: funções fora de ordem em relação ao benchmark")
    if erros:
        sys.exit("[ERRO] per_sample.csv não está alinhado ao benchmark:\n  " + "\n  ".join(erros))
    return base, ps


def populacao_de_pares(base, ps, piloto):
    validos = ps.groupby("sample_id")["status"].apply(lambda s: (s == "valido").sum() == len(MODELOS) * len(CONDICOES))
    localizavel = [len(r) == 1 and fb.count(r[0]) == 1 for fb, r in zip(base["func_body_n"], base["ref_handler"])]
    func = pd.DataFrame({
        "sample_id": range(len(base)),
        "seis_validos": validos.reindex(range(len(base))).fillna(False).values,
        "localizavel": localizavel,
        "piloto": [i in set(piloto) for i in range(len(base))],
        "azure": base["str_captures_except"].str.contains(MARCA_AZURE).values,
    })
    func["elegivel"] = func.seis_validos & func.localizavel & ~func.piloto
    pares = pd.DataFrame([{"sample_id": int(r.sample_id), "modelo": m, "azure": bool(r.azure)}
                          for r in func[func.elegivel].itertuples() for m in MODELOS])
    pares["estrato"] = pares.modelo + "|" + np.where(pares.azure, "azure", "outros")
    return func, pares.sort_values(["estrato", "sample_id"]).reset_index(drop=True)


def cochran(N, z=1.96, e=0.05, p=0.5):
    n0 = z * z * p * (1 - p) / (e * e)
    return math.ceil(n0 / (1 + (n0 - 1) / N))


def margem(N, n, z=1.96, p=0.5):
    return z * math.sqrt(p * (1 - p) / n) * math.sqrt((N - n) / (N - 1))


def alocacao(tamanhos, n):
    """Alocação proporcional pelo método dos maiores restos."""
    total = sum(tamanhos.values())
    cotas = {k: n * v / total for k, v in tamanhos.items()}
    base = {k: int(math.floor(c)) for k, c in cotas.items()}
    falta = n - sum(base.values())
    for k in sorted(cotas, key=lambda k: (-(cotas[k] - base[k]), k))[:falta]:
        base[k] += 1
    return base


def sortear(pares, seed, n_completa, n_reduzida):
    rng = np.random.default_rng(seed)
    tamanhos = pares.groupby("estrato").size().to_dict()
    k_comp, k_red = alocacao(tamanhos, n_completa), alocacao(tamanhos, n_reduzida)
    for s in k_red:                       # garante o aninhamento estrato a estrato
        k_red[s] = min(k_red[s], k_comp[s])
    ordem_estrato = {s: rng.permutation(pares.index[pares.estrato == s].to_numpy()) for s in sorted(tamanhos)}
    reduzida = np.concatenate([ordem_estrato[s][:k_red[s]] for s in sorted(tamanhos)])
    resto = np.concatenate([ordem_estrato[s][k_red[s]:k_comp[s]] for s in sorted(tamanhos)])
    ordem = np.concatenate([rng.permutation(reduzida), rng.permutation(resto)])
    sel = pares.loc[ordem].reset_index(drop=True)
    sel["par"] = range(1, len(sel) + 1)
    sel["na_amostra_reduzida"] = sel.par <= len(reduzida)
    ordens_cond = [rng.permutation(len(CONDICOES)).tolist() for _ in range(len(sel))]
    codigos = rng.choice(np.arange(1000, 10000), len(sel) * len(CONDICOES), replace=False).tolist()
    return sel, ordens_cond, codigos, k_comp, k_red


# --------------------------------------------------------------------------- #
# Itens
# --------------------------------------------------------------------------- #
def reindentar(handler):
    linhas = normalizar(handler).strip("\n").split("\n")
    linhas[0] = linhas[0].strip()
    resto = [l for l in linhas[1:] if l.strip()]
    if resto:
        desloc = max(min(len(l) - len(l.lstrip()) for l in resto) - 4, 0)
        linhas[1:] = [l[desloc:] if l.strip() else "" for l in linhas[1:]]
    return "\n".join(linhas)


def encaixar(func_body, ref, gerado):
    pos = func_body.index(ref)
    ini = func_body.rfind("\n", 0, pos) + 1
    prefixo = func_body[ini:pos]
    col = len(prefixo) if prefixo.strip() == "" else len(prefixo) - len(prefixo.lstrip())
    linhas = textwrap.dedent(normalizar(gerado)).strip("\n").split("\n")
    novo = linhas[0] + "".join("\n" + (" " * col + l if l.strip() else l) for l in linhas[1:])
    return func_body[:pos] + novo + func_body[pos + len(ref):]


def montar_itens(base, ps, sel, ordens_cond, codigos):
    idx = ps.set_index(["model", "prompt_type", "sample_id"])
    itens, k = [], 0
    for r, ordem in zip(sel.itertuples(), ordens_cond):
        fb, ref = base.at[r.sample_id, "func_body_n"], base.at[r.sample_id, "ref_handler"][0]
        for pos in ordem:
            cond = CONDICOES[pos]
            gerado = normalizar(idx.loc[(r.modelo, cond, r.sample_id), "pred_code"])
            itens.append({
                "item_id": f"I{codigos[k]}", "par": r.par, "sample_id": r.sample_id,
                "funcao": base.at[r.sample_id, "function"], "modelo": r.modelo, "condicao": cond,
                "azure": r.azure, "na_amostra_reduzida": r.na_amostra_reduzida,
                "codigo_em_contexto": encaixar(fb, ref, gerado),
                "handler_avaliado": reindentar(gerado), "handler_desenvolvedor": reindentar(ref),
                "_original": fb, "_ref": ref,
            })
            k += 1
    return pd.DataFrame(itens)


# --------------------------------------------------------------------------- #
# Planilhas
# --------------------------------------------------------------------------- #
COLUNAS = [
    ("item_id", "Item", 10, False), ("par", "Grupo (par)", 9, False), ("funcao", "Função", 22, False),
    ("codigo_em_contexto", "Código da função com o handler avaliado", 70, True),
    ("handler_avaliado", "Handler avaliado", 45, True),
    ("tipo", "1a. O tipo capturado pode ocorrer no try?", 18, False),
    ("reacao", "1b. A reação ao erro é apropriada para a função?", 16, False),
    ("justificativa", "2. Justificativa (obrigatória se 1a ou 1b = Não)", 35, False),
    ("handler_desenvolvedor", "Handler do desenvolvedor (ver só depois de 1a, 1b e 2)", 40, True),
    ("nota", "3. Semelhança com o desenvolvedor (1 a 5)", 16, False),
]
PREENCHER = ("tipo", "reacao", "justificativa", "nota")
INSTRUCOES = [
    ("Objetivo", "Julgar se cada handler gerado é adequado para a função que protege e quão semelhante ele é ao handler escrito pelo desenvolvedor."),
    ("Cegamento", "Os itens não informam o modelo nem a condição. Não abra o arquivo item_key.xlsx antes do fim da avaliação e não discuta itens com o outro avaliador."),
    ("Como ler um item", "Cada linha é um handler. Cada grupo tem duas versões do handler gerado para a mesma função. A coluna D mostra a função com o handler avaliado no lugar do original. Avalie cada linha de forma independente."),
    ("Ordem de preenchimento", "Responda 1a, 1b e 2 antes de olhar a coluna I (handler do desenvolvedor). Depois leia a coluna I e responda 3."),
    ("1a. Tipo", "Sim / Não / Não é possível determinar. Siga a Regra 1 (aba Regras). Responda Não quando for possível ver que nenhuma instrução do try lança aquele tipo de exceção."),
    ("1b. Reação", "Sim: o que o handler faz depois de capturar o erro é apropriado para o papel da função. Não: a reação contraria o que a função deveria fazer. Siga as Regras 2 e 3 (aba Regras)."),
    ("2. Justificativa", "Uma frase curta. Obrigatória quando 1a ou 1b for Não."),
    ("3. Semelhança (Souza et al., 2026)", "1 = nada similar; 2 = pouco similar; 3 = moderadamente similar; 4 = muito similar; 5 = idêntico."),
    ("Adequação", "Não é perguntada diretamente: um handler é adequado quando 1a = Sim e 1b = Sim."),
    ("Células a preencher", "Somente as colunas F, G, H e J, destacadas em amarelo. As colunas F, G e J têm lista de opções."),
    ("Regras", "A aba Regras traz as quatro regras acordadas na calibração do piloto. Consulte-as sempre que tiver dúvida; a Regra 4 vale para toda a planilha."),
    ("Casos não cobertos", "Se surgir um caso que nenhuma regra cobre, responda pelo seu melhor julgamento e comece a justificativa com \"DÚVIDA:\". Não discuta o item com o outro avaliador; esses casos são tratados no consenso, depois que os dois terminarem."),
]


def cab(c):
    c.font = Font(name=FONTE, bold=True, size=10)
    c.fill = PatternFill("solid", fgColor=COR_CABECALHO)
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    c.border = BORDA


def impressao(ws):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def aba_itens(ws, df):
    for j, (_, t, w, _) in enumerate(COLUNAS, start=1):
        cab(ws.cell(row=1, column=j, value=t))
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = "D2"
    dv_t = DataValidation(type="list", formula1='"Sim,Não,Não é possível determinar"', allow_blank=True, showErrorMessage=True)
    dv_r = DataValidation(type="list", formula1='"Sim,Não"', allow_blank=True, showErrorMessage=True)
    dv_n = DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True, showErrorMessage=True)
    for dv in (dv_t, dv_r, dv_n):
        ws.add_data_validation(dv)
    for i, row in enumerate(df.itertuples(index=False), start=2):
        sombra = PatternFill("solid", fgColor=COR_GRUPO) if row.par % 2 == 0 else None
        n_lin = 1
        for j, (campo, _, _, codigo) in enumerate(COLUNAS, start=1):
            v = getattr(row, campo) if campo in df.columns else None
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FONTE_CODIGO if codigo else FONTE, size=9 if codigo else 10)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BORDA
            if campo in PREENCHER:
                c.fill = PatternFill("solid", fgColor=COR_PREENCHER)
            elif sombra:
                c.fill = sombra
            if codigo and isinstance(v, str):
                n_lin = max(n_lin, v.count("\n") + 1)
        ws.row_dimensions[i].height = min(409, 12 * n_lin + 6)
        dv_t.add(f"F{i}")
        dv_r.add(f"G{i}")
        dv_n.add(f"J{i}")
    impressao(ws)


def planilha_avaliador(caminho, nome, itens, n_pares, data_regras):
    wb = Workbook()
    ws = wb.active
    ws.title = "Instrucoes"
    ws["A1"] = f"Avaliação manual de handlers de exceção — {n_pares} pares — avaliador(a): {nome}"
    ws["A1"].font = Font(name=FONTE, bold=True, size=12)
    for i, (t, d) in enumerate(INSTRUCOES, start=3):
        ws.cell(row=i, column=1, value=t).font = Font(name=FONTE, bold=True, size=10)
        c = ws.cell(row=i, column=2, value=d)
        c.font = Font(name=FONTE, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 30
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 30, 110
    impressao(ws)

    wr = wb.create_sheet("Regras")
    wr["A1"] = f"Regras de decisão acordadas na calibração do piloto por Ericlécio e Thays (planilha gerada em {data_regras})"
    wr["A1"].font = Font(name=FONTE, bold=True, size=12)
    for j, (t, w) in enumerate([("Regra", 10), ("Pergunta", 26), ("Texto da regra", 95), ("Exemplo do piloto", 28)], start=1):
        cab(wr.cell(row=3, column=j, value=t))
        wr.column_dimensions[wr.cell(row=3, column=j).column_letter].width = w
    for i, linha in enumerate(REGRAS, start=4):
        for j, v in enumerate(linha, start=1):
            c = wr.cell(row=i, column=j, value=v)
            c.font = Font(name=FONTE, size=10, bold=(j == 1))
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BORDA
        wr.row_dimensions[i].height = 75
    impressao(wr)

    aba_itens(wb.create_sheet("Avaliacao"), itens)
    wb.save(caminho)


def escrever_df(ws, df, larguras=None):
    for j, col in enumerate(df.columns, start=1):
        cab(ws.cell(row=1, column=j, value=str(col)))
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = (larguras or {}).get(col, 18)
    for i, row in enumerate(df.itertuples(index=False), start=2):
        for j, v in enumerate(row, start=1):
            v = v.item() if hasattr(v, "item") else v
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FONTE, size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


# --------------------------------------------------------------------------- #
# Validação
# --------------------------------------------------------------------------- #
def wilson(m, n, z=1.96):
    centro = (m + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(m * (1 - m) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - meia, centro + meia


def validar(args, pares, func, sel, itens, k_comp, k_red, pastas, ps):
    checks = []

    def check(nome, ok, detalhe=""):
        checks.append({"verificacao": nome, "resultado": "OK" if ok else "FALHA", "detalhe": detalhe})

    r1 = sortear(pares, args.seed, args.n_completa, args.n_reduzida)
    r2 = sortear(pares, args.seed, args.n_completa, args.n_reduzida)
    check("Reprodutibilidade: mesmo sorteio com a mesma semente",
          r1[0].equals(r2[0]) and r1[0][["sample_id", "modelo"]].equals(sel[["sample_id", "modelo"]]) and r1[2] == r2[2],
          f"semente {args.seed}")
    N = len(pares)
    req_red, req_comp = cochran(N, e=0.10), cochran(N, e=0.05)
    check("Amostra reduzida atende ao mínimo de Cochran (95%, ±10%)", args.n_reduzida >= req_red,
          f"{args.n_reduzida} pares; mínimo {req_red}; margem obtida ±{100 * margem(N, args.n_reduzida):.1f}%")
    check("Amostra completa atende ao mínimo de Cochran (95%, ±5%)", args.n_completa >= req_comp,
          f"{args.n_completa} pares; mínimo {req_comp}; margem obtida ±{100 * margem(N, args.n_completa):.1f}%")
    check("Tamanhos sorteados", len(sel) == args.n_completa and int(sel.na_amostra_reduzida.sum()) == args.n_reduzida,
          f"{len(sel)} e {int(sel.na_amostra_reduzida.sum())} pares")
    check("Aninhamento: a amostra reduzida são os primeiros pares da completa",
          bool(sel.na_amostra_reduzida.iloc[:args.n_reduzida].all() and not sel.na_amostra_reduzida.iloc[args.n_reduzida:].any()))
    check("Pares sem repetição", not sel.duplicated(["sample_id", "modelo"]).any())
    check("Nenhuma função do piloto na amostra", not set(sel.sample_id) & set(args.piloto),
          f"piloto: {sorted(args.piloto)}")
    elegiveis = set(func.loc[func.elegivel, "sample_id"])
    check("Todos os pares sorteados são elegíveis", set(sel.sample_id) <= elegiveis)
    desvio_c = {s: int((sel.estrato == s).sum()) - k for s, k in k_comp.items()}
    desvio_r = {s: int((sel[sel.na_amostra_reduzida].estrato == s).sum()) - k for s, k in k_red.items()}
    check("Estratificação proporcional (modelo × Azure) respeitada",
          all(v == 0 for v in desvio_c.values()) and all(v == 0 for v in desvio_r.values()),
          "; ".join(f"{s}: {k_red[s]}/{k_comp[s]}" for s in sorted(k_comp)))
    ok_par = itens.groupby("par").apply(lambda g: len(g) == 2 and g.modelo.nunique() == 1 and g.sample_id.nunique() == 1
                                        and set(g.condicao) == set(CONDICOES))
    check("Cada par tem os dois handlers (padrão e QG) do mesmo modelo e função", bool(ok_par.all()), f"{len(ok_par)} pares")
    check("Códigos dos itens únicos", itens.item_id.is_unique, f"{len(itens)} itens")
    esp = lambda t: " ".join(str(t).split())
    ok_ctx = [esp(c) == esp(o.replace(r, g)) for c, o, r, g in
              zip(itens.codigo_em_contexto, itens._original, itens._ref, itens.handler_avaliado)]
    check("Contexto correto: a função original com só o handler trocado", all(ok_ctx), f"{sum(ok_ctx)} de {len(ok_ctx)}")

    vazamentos, conteudos = [], {}
    for pasta in pastas:
        conteudos[pasta] = []
        for nome in args.avaliadores:
            caminho = os.path.join(pasta, f"{nome.lower()}.xlsx")
            wb = load_workbook(caminho, read_only=True)
            for row in wb["Avaliacao"].iter_rows(values_only=True):
                if any(p in str(v).lower() for v in row[:3] if v is not None for p in PALAVRAS_PROIBIDAS):
                    vazamentos.append(os.path.basename(caminho))
            wb.close()
            conteudos[pasta].append(pd.read_excel(caminho, sheet_name="Avaliacao").iloc[:, :5])
    check("Cegamento: planilhas sem identificação de modelo ou condição", not vazamentos, "; ".join(sorted(set(vazamentos))))
    check("Avaliadores recebem os mesmos itens, na mesma ordem",
          all(all(d.equals(v[0]) for d in v) for v in conteudos.values()))
    red, comp = conteudos[pastas[0]][0], conteudos[pastas[1]][0]
    check(f"A planilha de {args.n_reduzida} pares é o início da planilha completa", red.equals(comp.iloc[:len(red)].reset_index(drop=True)),
          f"{len(red)} itens")

    rep = []
    for rotulo, mascara in [(f"{args.n_reduzida} pares", sel.na_amostra_reduzida), (f"{args.n_completa} pares", sel.par > 0)]:
        s = sel[mascara]
        for cond in CONDICOES:
            g = ps[ps.prompt_type == cond].set_index(["sample_id", "model"])
            pop = g.loc[list(zip(pares.sample_id, pares.modelo))]
            am = g.loc[list(zip(s.sample_id, s.modelo))]
            for met, nome_m in [("any_target", "% com W0718 ou W0707"), ("ast_broad", "% com captura de Exception"),
                                ("jaccard", "Jaccard médio")]:
                ref, x = pop[met].mean(), am[met]
                if met == "jaccard":
                    meia = 1.96 * x.std(ddof=1) / math.sqrt(len(x))
                    lo, hi, f = x.mean() - meia, x.mean() + meia, 1
                else:
                    (lo, hi), f = wilson(x.mean(), len(x)), 100
                rep.append({"amostra": rotulo, "condicao": cond, "metrica": nome_m,
                            "populacao": round(f * ref, 3), "amostra_valor": round(f * x.mean(), 3),
                            "ic95": f"[{max(0, f * lo):.3f}; {f * hi:.3f}]",
                            "populacao_no_ic95": "Sim" if lo - 1e-12 <= ref <= hi + 1e-12 else "Não"})
    rep = pd.DataFrame(rep)
    fora = int((rep.populacao_no_ic95 == "Não").sum())
    check("Representatividade: valor da população dentro do IC 95% da amostra", fora == 0,
          f"{len(rep) - fora} de {len(rep)} métricas")
    return pd.DataFrame(checks), rep, req_red, req_comp


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Gera e valida as planilhas da avaliação manual por pares.")
    ap.add_argument("--base", default=os.path.join("data", "balanced_sample.csv"))
    ap.add_argument("--per-sample", default=os.path.join("llm", "output", "analysis", "per_sample.csv"))
    ap.add_argument("--sorteio-piloto", default=os.path.join("llm", "output", "manual_evaluation", "pilot", "sampling.json"),
                    help="sampling.json do piloto, para excluir as funções já usadas")
    ap.add_argument("--out", default=os.path.join("llm", "output", "manual_evaluation", "main"))
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--n-completa", type=int, default=287)
    ap.add_argument("--n-reduzida", type=int, default=120)
    ap.add_argument("--avaliadores", nargs="+", default=["Ericlecio", "Thays"])
    ap.add_argument("--verificar", action="store_true")
    args = ap.parse_args()

    for c in (args.base, args.per_sample, args.sorteio_piloto):
        if not os.path.exists(c):
            sys.exit(f"[ERRO] Arquivo não encontrado: {c}")
    if args.n_reduzida > args.n_completa:
        sys.exit("[ERRO] --n-reduzida não pode ser maior que --n-completa")
    with open(args.sorteio_piloto, encoding="utf-8") as f:
        args.piloto = [int(x) for x in json.load(f)["piloto"]]

    base, ps = carregar(args.base, args.per_sample)
    func, pares = populacao_de_pares(base, ps, args.piloto)
    sel, ordens_cond, codigos, k_comp, k_red = sortear(pares, args.seed, args.n_completa, args.n_reduzida)
    itens = montar_itens(base, ps, sel, ordens_cond, codigos)

    registro = {
        "versao_script": VERSAO, "semente": args.seed, "unidade": "par (função, modelo)",
        "parametros": {"n_completa": args.n_completa, "n_reduzida": args.n_reduzida,
                       "estratos": "modelo × grupo do Azure SDK, alocação proporcional"},
        "funcoes_do_piloto_excluidas": sorted(args.piloto),
        "sha256_entradas": {os.path.basename(c): sha256(c) for c in (args.base, args.per_sample, args.sorteio_piloto)},
        "pares": [[int(r.par), int(r.sample_id), r.modelo] for r in sel.itertuples()],
        "itens": {r.item_id: [r.modelo, r.condicao, int(r.sample_id), int(r.par)] for r in itens.itertuples()},
    }
    caminho_json = os.path.join(args.out, "sampling.json")

    if args.verificar:
        if not os.path.exists(caminho_json):
            sys.exit(f"[ERRO] {caminho_json} não existe; gere os arquivos primeiro.")
        with open(caminho_json, encoding="utf-8") as f:
            ant = json.load(f)
        campos = ["semente", "parametros", "funcoes_do_piloto_excluidas", "sha256_entradas", "pares", "itens"]
        dif = [c for c in campos if json.loads(json.dumps(ant.get(c))) != json.loads(json.dumps(registro[c]))]
        if not dif:
            print("[OK] O sorteio refeito é idêntico ao registrado: mesmas entradas, mesmos pares, mesmos itens.")
            sys.exit(0)
        print("[FALHA] O sorteio refeito difere do registrado em:", dif)
        sys.exit(1)

    data_regras = datetime.now().strftime("%d/%m/%Y")
    pastas = []
    for n in (args.n_reduzida, args.n_completa):
        pasta = os.path.join(args.out, f"sample_{n}_pairs")
        os.makedirs(pasta, exist_ok=True)
        sub = itens[itens.par <= n]
        for nome in args.avaliadores:
            planilha_avaliador(os.path.join(pasta, f"{nome.lower()}.xlsx"), nome, sub, n, data_regras)
        pastas.append(pasta)

    checks, rep, req_red, req_comp = validar(args, pares, func, sel, itens, k_comp, k_red, pastas, ps)

    N = len(pares)
    resumo = pd.DataFrame([
        {"etapa": "Funções da Task 4", "valor": len(func)},
        {"etapa": "Excluídas: algum dos 6 handlers inválido", "valor": int((~func.seis_validos).sum())},
        {"etapa": "Excluídas: usadas no piloto", "valor": int((func.seis_validos & func.piloto).sum())},
        {"etapa": "Funções elegíveis", "valor": int(func.elegivel.sum())},
        {"etapa": "População de pares (funções elegíveis × 3 modelos)", "valor": N},
        {"etapa": "Mínimo de Cochran, 95% de confiança, ±10%", "valor": req_red},
        {"etapa": "Mínimo de Cochran, 95% de confiança, ±5%", "valor": req_comp},
        {"etapa": f"Amostra reduzida (margem ±{100 * margem(N, args.n_reduzida):.1f}%)", "valor": args.n_reduzida},
        {"etapa": f"Amostra completa (margem ±{100 * margem(N, args.n_completa):.1f}%)", "valor": args.n_completa},
    ])
    estratos = pd.DataFrame([{"estrato": s, "pares_na_populacao": int((pares.estrato == s).sum()),
                              "amostra_reduzida": k_red[s], "amostra_completa": k_comp[s]} for s in sorted(k_comp)])

    registro["gerado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registro["validacao"] = checks.to_dict(orient="records")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)

    wb = Workbook()
    ws = wb.active
    ws.title = "Chave"
    escrever_df(ws, itens[["item_id", "par", "sample_id", "funcao", "modelo", "condicao", "azure", "na_amostra_reduzida"]],
                {"funcao": 30, "modelo": 24, "condicao": 18, "na_amostra_reduzida": 20})
    escrever_df(wb.create_sheet("Sorteio"), resumo, {"etapa": 58})
    escrever_df(wb.create_sheet("Estratos"), estratos, {"estrato": 36})
    escrever_df(wb.create_sheet("Validacao"), checks, {"verificacao": 62, "detalhe": 60})
    escrever_df(wb.create_sheet("Representatividade"), rep, {"metrica": 28, "condicao": 18, "ic95": 22})
    wb.save(os.path.join(args.out, "item_key.xlsx"))

    print("=" * 70)
    print("AVALIAÇÃO MANUAL POR PARES: SORTEIO E PLANILHAS")
    print("=" * 70)
    print(resumo.to_string(index=False))
    print("\nESTRATOS\n" + estratos.to_string(index=False))
    print("\nVALIDAÇÃO")
    for r in checks.itertuples():
        print(f"  [{r.resultado}] {r.verificacao}" + (f" ({r.detalhe})" if r.detalhe else ""))
    print(f"\nArquivos em {args.out}:")
    for raiz, _, arqs in os.walk(args.out):
        for a in sorted(arqs):
            print("  ", os.path.join(raiz, a))
    falhas = int((checks.resultado == "FALHA").sum())
    print("\n" + ("RESULTADO: sorteio validado." if not falhas else f"RESULTADO: {falhas} verificação(ões) falharam."))
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
