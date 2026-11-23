"""
Etapa final da avaliação manual: consenso e resultados.

Modo 1, preparar o consenso (rodar uma vez, depois da comparação dos avaliadores):
    python llm/manual_evaluation/manual_evaluation_results.py --preparar-consenso
    -> cria consensus.xlsx com os itens em que 1a ou 1b divergem, ou que foram marcados
       com "DÚVIDA:", para os dois avaliadores preencherem juntos a resposta final.

Modo 2, analisar (depois de preencher o consenso):
    python llm/manual_evaluation/manual_evaluation_results.py
    -> junta as respostas finais com a chave (modelo e condição de cada item) e calcula:
       concordância antes do consenso, % de handlers adequados por condição e modelo,
       teste de McNemar pareado (padrão x QG) e nota média de semelhança.
    -> salva manual_evaluation_results.xlsx e .md na pasta dos resultados, e a tabela
       manual-evaluation.tex em llm/output/paper/tables/.

Regras usadas na análise:
    - resposta final: a resposta comum aos dois avaliadores, ou a do consenso quando divergiram;
    - nota de semelhança final: média das duas notas;
    - adequado = 1a "Sim" e 1b "Sim"; itens com 1a "Não é possível determinar" ficam fora da
      comparação de adequação (são reportados à parte);
    - teste principal: McNemar exato sobre a adequação, com os três modelos juntos.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import rater_agreement as comp
except ImportError:
    sys.exit("[ERRO] rater_agreement.py precisa estar na mesma pasta deste script.")

import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402
from openpyxl import Workbook                          # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill   # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402
from scipy.stats import binomtest, wilcoxon           # noqa: E402

PASTA = os.path.join("llm", "output", "manual_evaluation", "main")
RESULTADOS = os.path.join(PASTA, "results")
NPD = "Não é possível determinar"
MODELOS = [("claude-haiku-4-5", "Claude Haiku 4.5"), ("gemini-3-flash-preview", "Gemini 3 Flash"),
           ("gpt-4o-mini", "GPT-4o-mini")]
BASE, QG = "style-default", "style-qg-default"


def duvida(v):
    return isinstance(v, str) and v.strip().upper().startswith(("DÚVIDA", "DUVIDA"))


def ler_contexto(caminho):
    df = pd.read_excel(caminho, sheet_name="Avaliacao")
    col = {c.split(" ")[0]: c for c in df.columns}
    return pd.DataFrame({"item_id": df[col["Item"]], "codigo_em_contexto": df.iloc[:, 3],
                         "handler_desenvolvedor": df.iloc[:, 8]})


# --------------------------------------------------------------------------- #
# Modo 1: preparar o consenso
# --------------------------------------------------------------------------- #
def preparar_consenso(args, a, b):
    if os.path.exists(args.consenso) and not args.forcar:
        sys.exit(f"[ERRO] {args.consenso} já existe. Para não apagar o consenso já preenchido, o script parou.\n"
                 "        Use --forcar só se quiser recriá-lo do zero.")
    ctx = ler_contexto(args.a).set_index("item_id")
    linhas = []
    for i in range(len(a)):
        motivos = [n for n, d in [("1a", a.tipo[i] != b.tipo[i]), ("1b", a.reacao[i] != b.reacao[i]),
                                  ("DÚVIDA", duvida(a.justificativa[i]) or duvida(b.justificativa[i]))] if d]
        if motivos:
            linhas.append({
                "item_id": a.item_id[i], "grupo": a.grupo[i], "funcao": a.funcao[i],
                "codigo_em_contexto": ctx.at[a.item_id[i], "codigo_em_contexto"],
                "handler_avaliado": a.handler_avaliado[i],
                f"1a_{args.nomes[0]}": a.tipo[i], f"1a_{args.nomes[1]}": b.tipo[i],
                f"1b_{args.nomes[0]}": a.reacao[i], f"1b_{args.nomes[1]}": b.reacao[i],
                f"justificativa_{args.nomes[0]}": a.justificativa[i], f"justificativa_{args.nomes[1]}": b.justificativa[i],
                "motivo": ", ".join(motivos), "1a_final": None, "1b_final": None, "observacao": None,
            })
    df = pd.DataFrame(linhas)
    # Pré-preenche o que os dois já responderam igual: só sobra decidir o que divergiu
    ca, cb = f"1a_{args.nomes[0]}", f"1a_{args.nomes[1]}"
    ra, rb = f"1b_{args.nomes[0]}", f"1b_{args.nomes[1]}"
    df["1a_final"] = np.where(df[ca] == df[cb], df[ca], None)
    df["1b_final"] = np.where(df[ra] == df[rb], df[ra], None)
    # Agrupa handlers idênticos da mesma função (Regra 4): uma decisão vale para o grupo inteiro
    chave_grupo = df.funcao.astype(str) + "||" + df.handler_avaliado.astype(str).str.split().str.join(" ")
    ordem_grupos = {k: i + 1 for i, k in enumerate(dict.fromkeys(chave_grupo))}
    df["grupo_identicos"] = chave_grupo.map(ordem_grupos)
    tamanho = df.groupby("grupo_identicos").item_id.transform("size")
    df.loc[tamanho == 1, "grupo_identicos"] = None
    # Ordena: primeiro divergências em 1a, depois em 1b, depois só DÚVIDA; casos iguais ficam juntos
    peso = np.where(df[ca] != df[cb], 0, np.where(df[ra] != df[rb], 1, 2))
    df = df.assign(_peso=peso, _func=df.funcao.astype(str), _g=df.grupo_identicos.fillna(1e9)) \
           .sort_values(["_peso", "_func", "_g"]).drop(columns=["_peso", "_func", "_g"]).reset_index(drop=True)
    cols = [c for c in df.columns if c not in ("1a_final", "1b_final", "observacao", "grupo_identicos")]
    df = df[cols[:5] + ["grupo_identicos"] + cols[5:] + ["1a_final", "1b_final", "observacao"]]
    wb = Workbook()
    ws = wb.active
    ws.title = "Consenso"
    larg = {"item_id": 9, "grupo": 7, "funcao": 18, "codigo_em_contexto": 60, "handler_avaliado": 40, "motivo": 12,
            "1a_final": 16, "1b_final": 12, "observacao": 30}
    for j, c in enumerate(df.columns, start=1):
        cel = ws.cell(row=1, column=j, value=c)
        cel.font = Font(name="Arial", bold=True)
        cel.fill = PatternFill("solid", fgColor="D9D9D9")
        cel.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cel.column_letter].width = larg.get(c, 30 if c.startswith("justificativa") else 13)
    dv1 = DataValidation(type="list", formula1=f'"Sim,Não,{NPD}"', allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"Sim,Não"', allow_blank=True)
    ws.add_data_validation(dv1)
    ws.add_data_validation(dv2)
    c1 = list(df.columns).index("1a_final") + 1
    c2 = list(df.columns).index("1b_final") + 1
    for i, r in enumerate(df.itertuples(index=False), start=2):
        n_lin = 1
        for j, v in enumerate(r, start=1):
            v = None if (isinstance(v, float) and np.isnan(v)) else v
            cel = ws.cell(row=i, column=j, value=v)
            codigo = df.columns[j - 1] in ("codigo_em_contexto", "handler_avaliado")
            cel.font = Font(name="Courier New" if codigo else "Arial", size=9 if codigo else 10)
            cel.alignment = Alignment(wrap_text=True, vertical="top")
            if df.columns[j - 1] in ("1a_final", "1b_final", "observacao"):
                cel.fill = PatternFill("solid", fgColor="FFF2CC")
            if codigo and isinstance(v, str):
                n_lin = max(n_lin, v.count("\n") + 1)
        ws.row_dimensions[i].height = min(409, 12 * n_lin + 6)
        dv1.add(ws.cell(row=i, column=c1))
        dv2.add(ws.cell(row=i, column=c2))
    ws.freeze_panes = "F2"
    wi = wb.create_sheet("Instrucoes")
    texto = [
        "Consenso da avaliação manual",
        "",
        "1. Para cada item, discutam as duas respostas e as justificativas, aplicando as regras da aba Regras das planilhas.",
        "2. As respostas em que vocês concordaram já vêm preenchidas em 1a_final e 1b_final; completem só as células vazias.",
        "   Itens com o mesmo número em grupo_identicos têm handlers idênticos da mesma função: decidam uma vez e repitam (Regra 4).",
        "3. Itens com motivo DÚVIDA: confirmem a resposta ou corrijam, e registrem a decisão em observacao.",
        "4. Não alterem as planilhas individuais: elas preservam as respostas usadas no cálculo da concordância.",
        "5. Ao terminar, rodem: python llm/manual_evaluation/manual_evaluation_results.py",
    ]
    for i, t in enumerate(texto, start=1):
        wi.cell(row=i, column=1, value=t).font = Font(name="Arial", bold=(i == 1), size=12 if i == 1 else 10)
    wi.column_dimensions["A"].width = 120
    wb.move_sheet("Instrucoes", offset=-1)
    wb.save(args.consenso)
    contagem = df.motivo.str.split(", ").explode().value_counts().to_dict() if len(df) else {}
    pendentes = df[df["1a_final"].isna() | df["1b_final"].isna()]
    decisoes = int(pendentes.grupo_identicos.nunique() + pendentes.grupo_identicos.isna().sum())
    so_confirmar = len(df) - len(pendentes)
    print(f"Consenso preparado: {len(df)} itens em {args.consenso}")
    print(f"  {so_confirmar} itens já vêm preenchidos (vocês concordaram; só confirmar).")
    print(f"  {len(pendentes)} itens a decidir, que somam {decisoes} decisões "
          f"(itens idênticos da mesma função compartilham o número em grupo_identicos).")
    print("Motivos:", ", ".join(f"{k}: {v}" for k, v in contagem.items()) or "nenhum")
    print("Preencham 1a_final e 1b_final de todos os itens e depois rodem o modo de análise.")


# --------------------------------------------------------------------------- #
# Modo 2: análise
# --------------------------------------------------------------------------- #
def mcnemar(xb, xq):
    b = int(((xb == 1) & (xq == 0)).sum())
    c = int(((xb == 0) & (xq == 1)).sum())
    return b, c, (1.0 if b + c == 0 else binomtest(b, b + c, 0.5).pvalue)


def pct(s):
    s = pd.Series(s).dropna()
    return round(100 * s.mean(), 1) if len(s) else np.nan


def fmt_p(p):
    return "--" if (p is None or np.isnan(p)) else ("< 0.001" if p < 0.001 else f"{p:.3f}")


def respostas_finais(args, a, b):
    cons = pd.read_excel(args.consenso, sheet_name="Consenso") if os.path.exists(args.consenso) else pd.DataFrame()
    precisa = (a.tipo != b.tipo) | (a.reacao != b.reacao)
    if precisa.any() and cons.empty:
        sys.exit(f"[ERRO] Há {int(precisa.sum())} itens divergentes e o consenso não foi encontrado.\n"
                 "        Rode antes: python llm/manual_evaluation/manual_evaluation_results.py --preparar-consenso")
    cons = cons.set_index("item_id") if not cons.empty else cons
    tipo, reacao, faltando = [], [], []
    for i in range(len(a)):
        iid = a.item_id[i]
        if not cons.empty and iid in cons.index:
            t, r = cons.at[iid, "1a_final"], cons.at[iid, "1b_final"]
            if comp.vazio(t) or comp.vazio(r):
                faltando.append(iid)
            tipo.append(str(t).strip() if not comp.vazio(t) else None)
            reacao.append(str(r).strip() if not comp.vazio(r) else None)
        else:
            tipo.append(a.tipo[i])
            reacao.append(a.reacao[i])
    if faltando:
        sys.exit(f"[ERRO] {len(faltando)} itens do consenso sem 1a_final ou 1b_final: {', '.join(faltando[:10])}"
                 + (" ..." if len(faltando) > 10 else ""))
    invalidos = [iid for iid, t, r in zip(a.item_id, tipo, reacao)
                 if t not in comp.OPCOES["tipo"] or r not in comp.OPCOES["reacao"]]
    if invalidos:
        sys.exit(f"[ERRO] Valores inválidos no consenso: {', '.join(invalidos[:10])}")
    final = pd.DataFrame({"item_id": a.item_id, "tipo": tipo, "reacao": reacao,
                          "nota": (a.nota.values + b.nota.values) / 2,
                          "consenso": [(not cons.empty) and (iid in cons.index) for iid in a.item_id]})
    final["determinavel"] = final.tipo != NPD
    final["adequado"] = np.where(final.determinavel, ((final.tipo == "Sim") & (final.reacao == "Sim")).astype(float), np.nan)
    final["tipo_sim"] = (final.tipo == "Sim").astype(float)
    final["reacao_sim"] = (final.reacao == "Sim").astype(float)
    return final


def analisar(args, a, b):
    final = respostas_finais(args, a, b)
    if not os.path.exists(args.chave):
        sys.exit(f"[ERRO] Chave não encontrada: {args.chave}")
    chave = pd.read_excel(args.chave, sheet_name="Chave")
    d = final.merge(chave[["item_id", "par", "modelo", "condicao"]], on="item_id", how="left")
    if d.modelo.isna().any():
        sys.exit("[ERRO] Há itens das planilhas que não estão na chave; confira se a chave é a do mesmo sorteio.")

    # concordância antes do consenso
    conc = []
    for campo, rot, nivel, cats in [("tipo", "Exception type (1a)", "nominal", None),
                                    ("reacao", "Reaction to the error (1b)", "nominal", None),
                                    ("adequado", "Adequacy (1a and 1b)", "nominal", None),
                                    ("nota", "Similarity, 1-5 (3)", "ordinal", [1, 2, 3, 4, 5])]:
        x, y = list(a[campo]), list(b[campo])
        conc.append({"Question": rot, "Agreement (%)": round(100 * np.mean([u == v for u, v in zip(x, y)]), 1),
                     "Krippendorff alpha": round(comp.alfa_krippendorff(x, y, nivel, cats), 3)})
    conc = pd.DataFrame(conc)

    # resumo por modelo e condição
    resumo = []
    grupos = [(m, n) for m, n in MODELOS] + [(None, "All models")]
    for m, nome in grupos:
        for cond, rot in [(BASE, "Default"), (QG, "QG")]:
            g = d[(d.condicao == cond) & ((d.modelo == m) if m else True)]
            resumo.append({"Model": nome, "Prompt": rot, "Handlers": len(g),
                           "Type can occur (%)": pct(g.tipo_sim), "Type undeterminable (%)": pct(~g.determinavel),
                           "Appropriate reaction (%)": pct(g.reacao_sim), "Adequate (%)": pct(g.adequado),
                           "Mean similarity": round(g.nota.mean(), 2)})
    resumo = pd.DataFrame(resumo)

    # testes pareados
    pareado = []
    for m, nome in grupos:
        g = d[(d.modelo == m)] if m else d
        bq = g.pivot(index="par", columns="condicao")
        ok = bq[("determinavel", BASE)].astype(bool) & bq[("determinavel", QG)].astype(bool)
        bb, cc, p = mcnemar(bq.loc[ok, ("adequado", BASE)].astype(int), bq.loc[ok, ("adequado", QG)].astype(int))
        rb, rc, rp = mcnemar(bq[("reacao_sim", BASE)].astype(int), bq[("reacao_sim", QG)].astype(int))
        nb, nq = bq[("nota", BASE)].astype(float), bq[("nota", QG)].astype(float)
        wp = 1.0 if np.allclose(nb, nq) else wilcoxon(nb, nq).pvalue
        pareado.append({"Model": nome, "Pairs": len(bq), "Pairs with determinable type": int(ok.sum()),
                        "Adequate, default (%)": pct(bq.loc[ok, ("adequado", BASE)]),
                        "Adequate, QG (%)": pct(bq.loc[ok, ("adequado", QG)]),
                        "Only default adequate": bb, "Only QG adequate": cc, "McNemar p (adequacy)": p,
                        "Reaction: only default appropriate": rb, "Reaction: only QG appropriate": rc,
                        "McNemar p (reaction)": rp,
                        "Similarity, default": round(nb.mean(), 2), "Similarity, QG": round(nq.mean(), 2),
                        "Wilcoxon p (similarity)": wp})
    pareado = pd.DataFrame(pareado)

    saida = os.path.join(args.out, "manual_evaluation_results.xlsx")
    with pd.ExcelWriter(saida) as w:
        conc.to_excel(w, sheet_name="Concordancia", index=False)
        resumo.to_excel(w, sheet_name="Resumo", index=False)
        pareado.to_excel(w, sheet_name="Pareado", index=False)
        d.to_excel(w, sheet_name="Itens_finais", index=False)
    with open(os.path.join(args.out, "manual_evaluation_results.md"), "w", encoding="utf-8") as f:
        for titulo, df in [("Concordância antes do consenso", conc), ("Resumo por modelo e prompt", resumo),
                           ("Comparação pareada (padrão x QG)", pareado)]:
            f.write(f"## {titulo}\n\n")
            try:
                f.write(df.to_markdown(index=False))
            except ImportError:
                f.write(df.to_string(index=False))
            f.write("\n\n")

    # tabela do artigo
    os.makedirs(args.artigo, exist_ok=True)
    alfa = dict(zip(conc.Question, conc["Krippendorff alpha"]))
    linhas = []
    for r in pareado.itertuples(index=False):
        if r.Model == "All models":
            linhas.append(r"    \midrule")
        linhas.append(f"    {r.Model} & {r[3]:.1f} & {r[4]:.1f} & {fmt_p(r[7])} \\\\")
    tex = "\n".join([
        "% Gerado por manual_evaluation_results.py; não editar à mão.",
        r"\begin{table}[t]", r"  \centering", r"  \footnotesize", r"  \setlength{\tabcolsep}{4pt}",
        rf"  \caption{{Manual evaluation: adequate handlers (\%), {int(pareado.Pairs.iloc[-1])} pairs}}",
        r"  \label{tab:manual}", r"  \begin{tabular}{lccc}", r"    \toprule",
        r"    Model & Default & QG & McNemar $p$ \\", r"    \midrule", *linhas, r"    \bottomrule",
        r"  \end{tabular}", r"  \par\vspace{2pt}",
        rf"  \parbox{{0.95\columnwidth}}{{\scriptsize Pairs with an undeterminable exception type are "
        rf"excluded ({int(pareado.Pairs.iloc[-1] - pareado['Pairs with determinable type'].iloc[-1])} of "
        rf"{int(pareado.Pairs.iloc[-1])}). Krippendorff's $\alpha$ before consensus: type {alfa['Exception type (1a)']:.2f}, "
        rf"reaction {alfa['Reaction to the error (1b)']:.2f}, adequacy {alfa['Adequacy (1a and 1b)']:.2f}, "
        rf"similarity {alfa['Similarity, 1-5 (3)']:.2f}.}}",
        r"\end{table}", ""])
    with open(os.path.join(args.artigo, "manual-evaluation.tex"), "w", encoding="utf-8") as f:
        f.write(tex)

    print("=" * 70)
    print("AVALIAÇÃO MANUAL: RESULTADOS")
    print("=" * 70)
    print(f"Itens: {len(d)} | resolvidos por consenso: {int(d.consenso.sum())} | "
          f"tipo indeterminável: {int((~d.determinavel).sum())}")
    print("\nCONCORDÂNCIA (antes do consenso)\n" + conc.to_string(index=False))
    print("\nRESUMO\n" + resumo.to_string(index=False))
    cols = ["Model", "Pairs with determinable type", "Adequate, default (%)", "Adequate, QG (%)",
            "Only default adequate", "Only QG adequate", "McNemar p (adequacy)", "McNemar p (reaction)",
            "Wilcoxon p (similarity)"]
    print("\nPAREADO\n" + pareado[cols].to_string(index=False))
    print(f"\nArquivos: {saida}\n          {os.path.join(args.artigo, 'manual-evaluation.tex')}")


def main():
    ap = argparse.ArgumentParser(description="Consenso e resultados da avaliação manual.")
    ap.add_argument("--a", default=os.path.join(RESULTADOS, "rater_1.xlsx"))
    ap.add_argument("--b", default=os.path.join(RESULTADOS, "rater_2.xlsx"))
    ap.add_argument("--nomes", nargs=2, default=["Ericlecio", "Thays"])
    ap.add_argument("--chave", default=os.path.join(PASTA, "item_key.xlsx"))
    ap.add_argument("--consenso", default=os.path.join(RESULTADOS, "consensus.xlsx"))
    ap.add_argument("--out", default=RESULTADOS)
    ap.add_argument("--artigo", default=os.path.join("llm", "output", "paper", "tables"))
    ap.add_argument("--preparar-consenso", action="store_true")
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args()

    a, b = comp.ler(args.a, "Avaliacao"), comp.ler(args.b, "Avaliacao")
    if list(a.item_id) != list(b.item_id):
        sys.exit("[ERRO] As duas planilhas não têm os mesmos itens na mesma ordem.")
    erros = comp.problemas_de_preenchimento(a, args.nomes[0]) + comp.problemas_de_preenchimento(b, args.nomes[1])
    if erros:
        sys.exit("[ERRO] Problemas de preenchimento:\n    " + "\n    ".join(erros))
    a.loc[:, "adequado"] = a.adequado
    if args.preparar_consenso:
        preparar_consenso(args, a, b)
    else:
        analisar(args, a, b)


if __name__ == "__main__":
    main()
