"""
Análises de robustez (respostas à revisão crítica do artigo).

Não coleta dados novos: reanalisa os resultados que já existem.

1. Avaliação manual (RQ2):
   - reação ao erro como desfecho principal (todos os 120 pares);
   - adequação original (pares com tipo determinável);
   - sensibilidade dos pares excluídos: tipo indeterminável tratado como inadequado e como adequado;
   - adequação estrita: além de tipo e reação, não pode capturar Exception/BaseException;
   - as mesmas medidas sem o grupo de funções quase duplicadas do Azure SDK;
   - intervalos de confiança: Wilson para as proporções, bootstrap por função para a diferença
     (respeita o fato de a mesma função aparecer para até três modelos);
   - tamanho de efeito do McNemar (razão de chances pareada b/c, com IC exato);
   - mediana da nota de semelhança.
2. RQ1: IC das taxas de violação, IC da diferença (bootstrap por função), razão de chances,
   razão entre a captura real de Exception (AST) e o W0718, e lançamento de Exception (W0719).
3. RQ2: distribuição das cinco ações (desenvolvedores, padrão, QG), redução de "engolir o erro"
   e formas de raise (relança o erro capturado, exceção nova com from, exceção nova sem from).
4. RQ3: concordância de ação e CodeBLEU com IC, tamanho de efeito do Wilcoxon e versão sem o Azure.

Entradas:
    llm/output/analysis/per_sample.csv, reference.csv, similarity_extra_per_sample.csv
    llm/output/manual_evaluation/main/results/manual_evaluation_results.xlsx
    llm/output/manual_evaluation/main/item_key.xlsx
Saídas (em llm/output/analysis/):
    robustness.xlsx e robustness.md

Uso (a partir da raiz do repositório):
    python llm/analysis/robustness_analyses.py
"""

import argparse
import ast
import os
import sys
import textwrap

import numpy as np
import pandas as pd
from scipy.stats import beta, binomtest, wilcoxon

BASE, QG = "style-default", "style-qg-default"
MODELOS = [("claude-haiku-4-5", "Claude"), ("gemini-3-flash-preview", "Gemini"), ("gpt-4o-mini", "GPT")]
MARCA_AZURE = "StreamConsumedError"
N_BOOT = 5000
RNG = np.random.default_rng(20261118)


# --------------------------------------------------------------------------- #
# Estatística
# --------------------------------------------------------------------------- #
def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * max(0.0, c - m), 100 * min(1.0, c + m)


def mcnemar(xb, xq):
    """xb, xq: arrays 0/1 pareados. Retorna b (só padrão), c (só QG), p exato, OR = b/c e IC exato."""
    xb, xq = np.asarray(xb, int), np.asarray(xq, int)
    b, c = int(((xb == 1) & (xq == 0)).sum()), int(((xb == 0) & (xq == 1)).sum())
    if b + c == 0:
        return b, c, 1.0, np.nan, (np.nan, np.nan)
    p = binomtest(b, b + c, 0.5).pvalue
    lo = beta.ppf(0.025, b, c + 1) if b > 0 else 0.0
    hi = beta.ppf(0.975, b + 1, c) if c > 0 else 1.0
    para_or = lambda t: t / (1 - t) if t < 1 else np.inf
    return b, c, p, (b / c if c else np.inf), (para_or(lo), para_or(hi))


def bootstrap_dif(df, coluna_b, coluna_q, grupo="sample_id"):
    """IC 95% da diferença de médias (QG - padrão), reamostrando funções inteiras."""
    grupos = df.groupby(grupo)
    somas = grupos[[coluna_b, coluna_q]].sum()
    contagens = grupos.size()
    ids = somas.index.to_numpy()
    sb, sq, n = somas[coluna_b].to_numpy(), somas[coluna_q].to_numpy(), contagens.to_numpy()
    difs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        idx = RNG.integers(0, len(ids), len(ids))
        difs[i] = (sq[idx].sum() - sb[idx].sum()) / n[idx].sum()
    return np.percentile(difs, [2.5, 97.5])


def fmt_ci(lo, hi, casas=1):
    return f"[{lo:.{casas}f}; {hi:.{casas}f}]"


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def carregar(args):
    caminhos = {
        "ps": os.path.join(args.analysis, "per_sample.csv"),
        "ref": os.path.join(args.analysis, "reference.csv"),
        "extra": os.path.join(args.analysis, "similarity_extra_per_sample.csv"),
        "manual": os.path.join(args.manual, "manual_evaluation_results.xlsx"),
        "chave": args.chave,
    }
    faltando = [c for c in caminhos.values() if not os.path.exists(c)]
    if faltando:
        sys.exit("[ERRO] Arquivos não encontrados:\n  " + "\n  ".join(faltando) +
                 "\nRode antes: analyze_handlers.py, similarity_metrics.py e manual_evaluation_results.py")
    ps = pd.read_csv(caminhos["ps"])
    ref = pd.read_csv(caminhos["ref"]).set_index("sample_id")
    extra = pd.read_csv(caminhos["extra"])
    itens = pd.read_excel(caminhos["manual"], sheet_name="Itens_finais")
    chave = pd.read_excel(caminhos["chave"], sheet_name="Chave")[["item_id", "sample_id", "azure"]]
    itens = itens.merge(chave, on="item_id", how="left")
    azure = ref["ref_code"].astype(str).str.contains(MARCA_AZURE)
    return ps, ref, extra, itens, azure


def raise_generico(code):
    if not isinstance(code, str):
        return np.nan
    code = textwrap.dedent(code.replace("\r\n", "\n")).strip("\n")
    for src in ("try:\n    pass\n" + code, code):
        try:
            arvore = ast.parse(src)
            break
        except SyntaxError:
            arvore = None
    if arvore is None:
        return np.nan
    for n in ast.walk(arvore):
        if isinstance(n, ast.Raise) and n.exc is not None:
            alvo = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            if ast.unparse(alvo).split(".")[-1] in ("Exception", "BaseException"):
                return 1.0
    return 0.0


# --------------------------------------------------------------------------- #
# 1. Avaliação manual
# --------------------------------------------------------------------------- #
def avaliacao_manual(itens, ps):
    broad = ps.set_index(["model", "prompt_type", "sample_id"])["ast_broad"]
    itens = itens.copy()
    itens["captura_ampla"] = [broad.get((m, c, s), np.nan) for m, c, s in zip(itens.modelo, itens.condicao, itens.sample_id)]
    itens["reacao_ok"] = itens.reacao_sim.astype(float)
    itens["adequado_orig"] = itens.adequado                                   # NaN quando indeterminável
    itens["adequado_npd_inad"] = ((itens.tipo == "Sim") & (itens.reacao == "Sim")).astype(float)
    itens["adequado_npd_adeq"] = (((itens.tipo == "Sim") | (itens.tipo == "Não é possível determinar"))
                                  & (itens.reacao == "Sim")).astype(float)
    itens["adequado_estrito"] = ((itens.tipo == "Sim") & (itens.reacao == "Sim")
                                 & (itens.captura_ampla == 0)).astype(float)

    medidas = [("reacao_ok", "Reaction appropriate (primary)"),
               ("adequado_orig", "Adequate, original (determinable pairs)"),
               ("adequado_npd_inad", "Adequate, undeterminable = inadequate"),
               ("adequado_npd_adeq", "Adequate, undeterminable = adequate"),
               ("adequado_estrito", "Adequate, strict (no broad catch)")]
    linhas = []
    for escopo, filtro in [("All pairs", itens.par > 0), ("Without Azure", ~itens.azure.astype(bool))]:
        sub = itens[filtro]
        wide = sub.pivot(index="par", columns="condicao")
        sid = wide[("sample_id", BASE)]
        for col, rotulo in medidas:
            xb, xq = wide[(col, BASE)], wide[(col, QG)]
            ok = xb.notna() & xq.notna()
            xb, xq = xb[ok].astype(int), xq[ok].astype(int)
            n = len(xb)
            b, c, p, orr, (olo, ohi) = mcnemar(xb, xq)
            dlo, dhi = bootstrap_dif(pd.DataFrame({"sample_id": sid[ok].values, "b": xb.values, "q": xq.values}), "b", "q")
            linhas.append({
                "scope": escopo, "measure": rotulo, "pairs": n,
                "default_%": round(100 * xb.mean(), 1), "default_CI95": fmt_ci(*wilson(int(xb.sum()), n)),
                "QG_%": round(100 * xq.mean(), 1), "QG_CI95": fmt_ci(*wilson(int(xq.sum()), n)),
                "diff_pp": round(100 * (xq.mean() - xb.mean()), 1),
                "diff_CI95_cluster_bootstrap": fmt_ci(100 * dlo, 100 * dhi),
                "only_default": b, "only_QG": c, "McNemar_p": fmt_p(p),
                "odds_ratio_b/c": (round(orr, 2) if np.isfinite(orr) else "inf"),
                "OR_CI95": fmt_ci(olo, ohi, 2) if np.isfinite(olo) else "--",
            })
    tab = pd.DataFrame(linhas)

    notas = itens.pivot(index="par", columns="condicao", values="nota")
    nota = pd.DataFrame([{"measure": "Similarity rating (1-5)",
                          "default_mean": round(notas[BASE].mean(), 2), "QG_mean": round(notas[QG].mean(), 2),
                          "default_median": notas[BASE].median(), "QG_median": notas[QG].median(),
                          "Wilcoxon_p": fmt_p(wilcoxon(notas[BASE], notas[QG]).pvalue)}])
    ind = (itens.tipo == "Não é possível determinar").groupby(itens.condicao).mean().mul(100).round(1)
    return tab, nota, ind


# --------------------------------------------------------------------------- #
# 2. RQ1
# --------------------------------------------------------------------------- #
def rq1(ps, ref, azure):
    linhas, razoes, w0719 = [], [], []
    for m, nome in MODELOS:
        b = ps[(ps.model == m) & (ps.prompt_type == BASE)].set_index("sample_id").sort_index()
        q = ps[(ps.model == m) & (ps.prompt_type == QG)].set_index("sample_id").sort_index()
        ok = (b.status == "valido") & (q.status == "valido")
        xb, xq = b.any_target[ok].astype(int), q.any_target[ok].astype(int)
        n = len(xb)
        bb, cc, p, orr, (olo, ohi) = mcnemar(xb, xq)
        dlo, dhi = bootstrap_dif(pd.DataFrame({"sample_id": xb.index, "b": xb.values, "q": xq.values}), "b", "q")
        linhas.append({"model": nome, "pairs": n,
                       "default_%": round(100 * xb.mean(), 1), "default_CI95": fmt_ci(*wilson(int(xb.sum()), n)),
                       "QG_%": round(100 * xq.mean(), 1), "QG_CI95": fmt_ci(*wilson(int(xq.sum()), n)),
                       "diff_pp": round(100 * (xq.mean() - xb.mean()), 1), "diff_CI95": fmt_ci(100 * dlo, 100 * dhi),
                       "worsened": cc, "improved": bb, "McNemar_p": fmt_p(p)})
        w = 100 * b.W0718[ok].mean()
        a = 100 * b.ast_broad[ok].mean()
        razoes.append({"model": nome, "W0718_default_%": round(w, 1), "AST_broad_default_%": round(a, 1),
                       "ratio_AST/W0718": round(a / w, 1) if w else np.nan})
        gb = b.pred_code[b.status == "valido"].apply(raise_generico)
        gq = q.pred_code[q.status == "valido"].apply(raise_generico)
        w0719.append({"model": nome, "raises_Exception_default_%": round(100 * gb.mean(), 1),
                      "raises_Exception_QG_%": round(100 * gq.mean(), 1)})
    return pd.DataFrame(linhas), pd.DataFrame(razoes), pd.DataFrame(w0719)


def formas_raise(code):
    """Separa os raise do handler: relança o erro capturado, exceção nova com from, exceção nova sem from."""
    if not isinstance(code, str):
        return None
    code = textwrap.dedent(code.replace("\r\n", "\n")).strip("\n")
    arvore = None
    for src in ("try:\n    pass\n" + code, code):
        try:
            arvore = ast.parse(src)
            break
        except SyntaxError:
            pass
    if arvore is None:
        return None
    f = {"any_raise": 0, "reraise_caught": 0, "new_with_from": 0, "new_without_from": 0}
    for h in ast.walk(arvore):
        if not isinstance(h, ast.ExceptHandler):
            continue
        for n in ast.walk(h):
            if isinstance(n, ast.Raise):
                f["any_raise"] = 1
                if n.exc is None or (isinstance(n.exc, ast.Name) and n.exc.id == h.name):
                    f["reraise_caught"] = 1
                elif n.cause is not None:
                    f["new_with_from"] = 1
                else:
                    f["new_without_from"] = 1
    return f


def tabela_formas_raise(ps, ref):
    linhas = []
    for m, nome in MODELOS:
        for cond, rot in ((BASE, "Default"), (QG, "QG")):
            g = ps[(ps.model == m) & (ps.prompt_type == cond) & (ps.status == "valido")]
            d = pd.DataFrame([x for x in g.pred_code.map(formas_raise) if x])
            linhas.append({"model": nome, "prompt": rot, "n": len(d), **{k: round(100 * d[k].mean(), 1) for k in d}})
    d = pd.DataFrame([x for x in ref.ref_code.map(formas_raise) if x])
    linhas.append({"model": "Developers", "prompt": "Reference", "n": len(d), **{k: round(100 * d[k].mean(), 1) for k in d}})
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
# 3 e 4. Ações (RQ2) e semelhança (RQ3)
# --------------------------------------------------------------------------- #
def acoes_e_rq3(extra, ref, azure):
    acoes = ["raise", "return", "log", "ignore", "other"]
    dist = []
    for m, nome in MODELOS:
        for cond, rot in ((BASE, "Default"), (QG, "QG")):
            g = extra[(extra.model == m) & (extra.prompt_type == cond) & extra.acao_gerada.notna()]
            vc = g.acao_gerada.value_counts(normalize=True)
            dist.append({"model": nome, "prompt": rot, "n": len(g), **{a: round(100 * vc.get(a, 0), 1) for a in acoes}})
    from similarity_metrics import acao   # mesma classificação usada na concordância de ação
    vc = ref.ref_code.apply(acao).value_counts(normalize=True)
    dist.append({"model": "Developers", "prompt": "Reference", "n": int(ref.ref_code.notna().sum()),
                 **{a: round(100 * vc.get(a, 0), 1) for a in acoes}})

    linhas = []
    for escopo, ids in [("All functions", ref.index), ("Without Azure", ref.index[~azure])]:
        for m, nome in MODELOS:
            g = extra[(extra.model == m) & extra.sample_id.isin(ids)]
            b = g[g.prompt_type == BASE].set_index("sample_id").sort_index()
            q = g[g.prompt_type == QG].set_index("sample_id").sort_index()
            ok = b.mesma_acao.notna() & q.mesma_acao.notna()
            xb, xq = b.mesma_acao[ok].astype(int), q.mesma_acao[ok].astype(int)
            bb, cc, p, _, _ = mcnemar(xb, xq)
            dlo, dhi = bootstrap_dif(pd.DataFrame({"sample_id": xb.index, "b": xb.values, "q": xq.values}), "b", "q")
            w = wilcoxon(b.codebleu, q.codebleu, method="approx")
            r = abs(w.zstatistic) / np.sqrt(len(b)) if hasattr(w, "zstatistic") else np.nan
            linhas.append({"scope": escopo, "model": nome, "pairs": len(xb),
                           "same_action_default_%": round(100 * xb.mean(), 1),
                           "same_action_QG_%": round(100 * xq.mean(), 1),
                           "same_action_diff_CI95": fmt_ci(100 * dlo, 100 * dhi), "same_action_McNemar_p": fmt_p(p),
                           "CodeBLEU_default": round(b.codebleu.mean(), 3), "CodeBLEU_QG": round(q.codebleu.mean(), 3),
                           "CodeBLEU_Wilcoxon_p": fmt_p(w.pvalue), "CodeBLEU_effect_r": round(r, 2)})
    return pd.DataFrame(dist), pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Análises de robustez para o artigo.")
    ap.add_argument("--analysis", default=os.path.join("llm", "output", "analysis"))
    ap.add_argument("--manual", default=os.path.join("llm", "output", "manual_evaluation", "main", "results"))
    ap.add_argument("--chave", default=os.path.join("llm", "output", "manual_evaluation", "main", "item_key.xlsx"))
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    ps, ref, extra, itens, azure = carregar(args)
    man, nota, ind = avaliacao_manual(itens, ps)
    r1, razoes, w0719 = rq1(ps, ref, azure)
    dist, r3 = acoes_e_rq3(extra, ref, azure)
    formas = tabela_formas_raise(ps, ref)

    blocos = [("1. Manual evaluation: primary outcome, sensitivity and strict adequacy", man),
              ("1b. Similarity rating (1-5)", nota),
              ("1c. Undeterminable exception type (% of handlers)", ind.rename("pct").reset_index()),
              ("2. RQ1: target violations with CI and paired difference", r1),
              ("2b. RQ1: actual broad catches (AST) vs. W0718, default prompt", razoes),
              ("2c. RQ1: raising Exception/BaseException (W0719 behavior)", w0719),
              ("3. RQ2: action distribution (% of valid handlers)", dist),
              ("3b. RQ2: forms of raise (% of valid handlers; a handler may have more than one)", formas),
              ("4. RQ3: action agreement and CodeBLEU, with and without Azure", r3)]
    saida_xlsx = os.path.join(args.analysis, "robustness.xlsx")
    with pd.ExcelWriter(saida_xlsx) as w:
        for i, (_, df) in enumerate(blocos, start=1):
            df.to_excel(w, sheet_name=f"bloco{i}", index=False)
    with open(os.path.join(args.analysis, "robustness.md"), "w", encoding="utf-8") as f:
        for titulo, df in blocos:
            f.write(f"## {titulo}\n\n")
            try:
                f.write(df.to_markdown(index=False))
            except ImportError:
                f.write(df.to_string(index=False))
            f.write("\n\n")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for titulo, df in blocos:
        print("\n" + "=" * 100 + f"\n{titulo}\n" + "=" * 100)
        print(df.to_string(index=False))
    print(f"\nArquivos salvos: {saida_xlsx} e robustness.md")


if __name__ == "__main__":
    main()