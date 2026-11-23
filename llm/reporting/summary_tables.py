"""
Gera as figuras e tabelas da apresentação a partir dos resultados da análise.

Entradas (geradas pelo analyze_handlers.py e pelo rater_agreement.py):
    llm/output/analysis/per_sample.csv      obrigatório
    llm/output/analysis/reference.csv       obrigatório
    llm/output/analysis/paired_tests.csv    obrigatório
    llm/output/analysis/cost_tokens.csv     opcional (tabela de custo)
    agreement_pilot.xlsx                  opcional (concordância do piloto; procurado em
                                            llm/output/manual_evaluation/pilot e subpastas)

Saídas (em llm/output/presentation/):
    figures/fig1_rq1_violations.png        violações W0718/W0707 por modelo e prompt
    figures/fig2_pylint_blind_spot.png     W0718 do Pylint vs. captura real de Exception (AST)
    figures/fig3_rq2_reraise.png           handlers que relançam o erro
    figures/fig4_pipeline.png              entrada, geração, registros e análise
    figures/fig5_rq3_similarity.png        semelhança com o código do desenvolvedor
    tables/*.png                          tabelas prontas para slide
    tables.xlsx e tables.md              todas as tabelas, com os números

Uso (a partir da raiz do repositório):
    python llm/reporting/summary_tables.py
"""

import argparse
import ast
import glob
import os
import re
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyBboxPatch        # noqa: E402
from matplotlib.ticker import FuncFormatter          # noqa: E402
import numpy as np                                   # noqa: E402
import pandas as pd                                  # noqa: E402
from scipy.stats import binomtest                    # noqa: E402

MODELOS = [("claude-haiku-4-5", "Claude Haiku 4.5"),
           ("gemini-3-flash-preview", "Gemini 3 Flash"),
           ("gpt-4o-mini", "GPT-4o-mini")]
BASE, QG = "style-default", "style-qg-default"
ROTULO_COND = {BASE: "Default prompt", QG: "Quality-guided prompt"}
MARCA_AZURE = "StreamConsumedError"

VERMELHO, CINZA, CINZA_ESCURO, TEXTO = "#D7263D", "#B8B8B8", "#7A7A7A", "#333333"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13,
                     "axes.spines.top": False, "axes.spines.right": False})


# --------------------------------------------------------------------------- #
# Padrões de comportamento dos handlers (contagem via AST)
# --------------------------------------------------------------------------- #
def analisar(code):
    if not isinstance(code, str) or not code.strip():
        return None
    code = textwrap.dedent(code.replace("\r\n", "\n")).strip("\n")
    for src in ("def _f():\n" + textwrap.indent("try:\n    pass\n" + code, "    "),
                "def _f():\n" + textwrap.indent(code, "    ")):
        try:
            arvore = ast.parse(src)
            break
        except SyntaxError:
            arvore = None
    if arvore is None:
        return None
    f = dict(raise_generic=0, raise_runtime=0, from_none=0, swallow=0,
             tuple3=0, reraise_same=0, logs_only=0)
    for h in ast.walk(arvore):
        if not isinstance(h, ast.ExceptHandler):
            continue
        nomes = []
        if h.type is not None:
            for e in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]):
                nomes.append(ast.unparse(e).split(".")[-1])
        if len(nomes) >= 3:
            f["tuple3"] = 1
        corpo = [s for s in h.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if corpo and all(isinstance(s, (ast.Pass, ast.Continue)) for s in corpo):
            f["swallow"] = 1
        if corpo and all(isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                         and any(k in ast.unparse(s.value.func).lower() for k in ("log", "print", "warn"))
                         for s in corpo):
            f["logs_only"] = 1
        for n in ast.walk(h):
            if isinstance(n, ast.Raise) and n.exc is not None:
                alvo = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
                nome = ast.unparse(alvo).split(".")[-1]
                f["raise_generic"] |= nome in ("Exception", "BaseException")
                f["raise_runtime"] |= nome == "RuntimeError"
                f["from_none"] |= isinstance(n.cause, ast.Constant) and n.cause.value is None
                f["reraise_same"] |= nome in nomes
    return {k: int(v) for k, v in f.items()}


def tem_raise(code):
    return bool(re.search(r"^\s*raise\b", str(code), re.M)) if isinstance(code, str) else False


def tipos(code):
    t = analisar_tipos(code)
    return t if t is not None else set()


def analisar_tipos(code):
    if not isinstance(code, str):
        return None
    code = textwrap.dedent(code.replace("\r\n", "\n")).strip("\n")
    for src in ("try:\n    pass\n" + code, code):
        try:
            arvore = ast.parse(src)
            break
        except SyntaxError:
            arvore = None
    if arvore is None:
        return None
    s = set()
    for h in ast.walk(arvore):
        if isinstance(h, ast.ExceptHandler) and h.type is not None:
            for e in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]):
                s.add(ast.unparse(e).split(".")[-1])
    return s


def pct(serie):
    s = pd.Series(serie).dropna()
    return round(100 * s.mean(), 1) if len(s) else np.nan


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def carregar(pasta):
    caminhos = {k: os.path.join(pasta, f"{k}.csv") for k in ("per_sample", "reference", "paired_tests", "cost_tokens")}
    for k in ("per_sample", "reference", "paired_tests"):
        if not os.path.exists(caminhos[k]):
            sys.exit(f"[ERRO] {caminhos[k]} não encontrado. Rode antes: python llm/analysis/analyze_handlers.py")
    ps = pd.read_csv(caminhos["per_sample"])
    ref = pd.read_csv(caminhos["reference"]).set_index("sample_id").sort_index()
    if "any_target" not in ref.columns:
        ref["any_target"] = ref[["W0718", "W0707"]].max(axis=1, skipna=False)
    testes = pd.read_csv(caminhos["paired_tests"])
    custo = pd.read_csv(caminhos["cost_tokens"]) if os.path.exists(caminhos["cost_tokens"]) else None
    faltando = [(m, c) for m, _ in MODELOS for c in (BASE, QG)
                if ps[(ps.model == m) & (ps.prompt_type == c)].empty]
    if faltando:
        sys.exit(f"[ERRO] per_sample.csv não tem as condições: {faltando}")
    return ps, ref, testes, custo


def condicao(ps, modelo, cond):
    return ps[(ps.model == modelo) & (ps.prompt_type == cond)].set_index("sample_id").sort_index()


def pares(ps, modelo, mascara=None):
    b, q = condicao(ps, modelo, BASE), condicao(ps, modelo, QG)
    ok = (b.status == "valido") & (q.status == "valido")
    if mascara is not None:
        ok &= mascara.reindex(ok.index).values
    return b[ok], q[ok]


def p_holm(testes, modelo, metrica):
    linha = testes[(testes.model == modelo) & (testes.metrica == metrica)]
    return float(linha.p_holm.iloc[0]) if len(linha) else np.nan


def fmt_p(p):
    if np.isnan(p):
        return "—"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


# --------------------------------------------------------------------------- #
# Tabelas
# --------------------------------------------------------------------------- #
def construir_tabelas(ps, ref, testes, custo):
    t = {}
    azure = ref["ref_code"].astype(str).str.contains(MARCA_AZURE)
    ref_ok = ref[ref.W0718.notna()]

    # RQ1: violações por modelo e prompt (pares válidos nas duas condições)
    linhas, pareado = [], []
    for m, nome in MODELOS:
        b, q = pares(ps, m)
        for cond, d in ((BASE, b), (QG, q)):
            linhas.append({"Model": nome, "Prompt": ROTULO_COND[cond], "W0718 (%)": pct(d.W0718),
                           "W0707 (%)": pct(d.W0707), "W0718 or W0707 (%)": pct(d.any_target)})
        xb, xq = b.any_target.astype(int), q.any_target.astype(int)
        melhorou, piorou = int(((xb == 1) & (xq == 0)).sum()), int(((xb == 0) & (xq == 1)).sum())
        p = p_holm(testes, m, "any_target")
        if np.isnan(p) and melhorou + piorou:
            p = binomtest(melhorou, melhorou + piorou).pvalue
        pareado.append({"Model": nome, "Valid pairs": len(b), "Improved": melhorou, "Worsened": piorou,
                        "McNemar p (Holm)": fmt_p(p)})
    linhas.append({"Model": "Developers", "Prompt": "Reference", "W0718 (%)": pct(ref_ok.W0718),
                   "W0707 (%)": pct(ref_ok.W0707), "W0718 or W0707 (%)": pct(ref_ok.any_target)})
    t["rq1_violations"] = pd.DataFrame(linhas)
    t["rq1_paired"] = pd.DataFrame(pareado)

    # Ponto cego do Pylint
    linhas = []
    for m, nome in MODELOS:
        b, q = pares(ps, m)
        linhas.append({"Model": nome, "Flagged by W0718, default (%)": pct(b.W0718),
                       "Actual Exception catch, default (%)": pct(b.ast_broad),
                       "Actual Exception catch, QG (%)": pct(q.ast_broad)})
    linhas.append({"Model": "Developers", "Flagged by W0718, default (%)": pct(ref_ok.W0718),
                   "Actual Exception catch, default (%)": pct(ref_ok.ast_broad),
                   "Actual Exception catch, QG (%)": np.nan})
    t["pylint_blind_spot"] = pd.DataFrame(linhas)

    # RQ2: padrões dos handlers
    def padroes(codigos, w0702, w0706):
        feats = [analisar(c) for c in codigos]
        df = pd.DataFrame([f for f in feats if f])
        return {"Bare except: W0702 (%)": pct(w0702), "raise ... from None (%)": pct(df.from_none),
                "Raises Exception (%)": pct(df.raise_generic), "Only re-raises: W0706 (%)": pct(w0706),
                "Contains raise (%)": round(100 * np.mean([tem_raise(c) for c in codigos]), 1),
                "Raises RuntimeError (%)": pct(df.raise_runtime),
                "Swallows the error (%)": pct(df.swallow), "Only logs or prints (%)": pct(df.logs_only),
                "Catches 3+ types (%)": pct(df.tuple3)}
    linhas = []
    for m, nome in MODELOS:
        for cond in (BASE, QG):
            d = condicao(ps, m, cond)
            v = d[d.status == "valido"]
            linhas.append({"Model": nome, "Prompt": ROTULO_COND[cond],
                           **padroes(d.pred_code, v.W0702, v.W0706)})
    linhas.append({"Model": "Developers", "Prompt": "Reference",
                   **padroes(ref.ref_code, ref_ok.W0702, ref_ok.W0706)})
    t["rq2_patterns"] = pd.DataFrame(linhas)
    chaves = ["Model", "Prompt"]
    t["rq2_evasions"] = t["rq2_patterns"][chaves + ["Bare except: W0702 (%)", "raise ... from None (%)",
                                                    "Raises Exception (%)", "Only re-raises: W0706 (%)"]]
    t["rq2_behavior"] = t["rq2_patterns"][chaves + ["Contains raise (%)", "Raises RuntimeError (%)",
                                                    "Swallows the error (%)", "Only logs or prints (%)"]]

    # RQ3: semelhança
    linhas, signif = [], []
    for m, nome in MODELOS:
        for cond in (BASE, QG):
            d = condicao(ps, m, cond)
            linhas.append({"Model": nome, "Prompt": ROTULO_COND[cond],
                           "Jaccard": round(d.jaccard.mean(), 3), "CrystalBLEU": round(d.crystalbleu.mean(), 3),
                           "Type in common with developer (%)": pct(d.type_overlap)})
        signif.append({"Model": nome, "Jaccard p (Holm)": fmt_p(p_holm(testes, m, "jaccard")),
                       "CrystalBLEU p (Holm)": fmt_p(p_holm(testes, m, "crystalbleu")),
                       "Type in common p (Holm)": fmt_p(p_holm(testes, m, "type_overlap"))})
    t["rq3_similarity"] = pd.DataFrame(linhas)
    t["rq3_significance"] = pd.DataFrame(signif)

    # Troca de Exception por tipo específico (fora do grupo do Azure)
    linhas = []
    for m, nome in MODELOS:
        b, q = condicao(ps, m, BASE), condicao(ps, m, QG)
        trocas = b.index[(b.ast_broad == 1) & (q.ast_broad == 0) & (q.status == "valido") & ~azure.reindex(b.index).values]
        iguais = sum(1 for i in trocas if tipos(ref.at[i, "ref_code"]) and
                     tipos(ref.at[i, "ref_code"]) == tipos(q.at[i, "pred_code"]))
        linhas.append({"Model": nome, "QG replaced Exception with specific types": len(trocas),
                       "Same types as the developer": iguais})
    t["type_choice"] = pd.DataFrame(linhas)

    # Sem o grupo do Azure
    linhas = []
    for m, nome in MODELOS:
        b, q = pares(ps, m, ~azure)
        linhas.append({"Model": nome, "Valid pairs": len(b),
                       "W0718 or W0707, default (%)": pct(b.any_target), "W0718 or W0707, QG (%)": pct(q.any_target),
                       "W0706, default (%)": pct(b.W0706), "W0706, QG (%)": pct(q.W0706),
                       "Jaccard, default": round(b.jaccard.mean(), 3), "Jaccard, QG": round(q.jaccard.mean(), 3)})
    t["without_azure"] = pd.DataFrame(linhas)

    # Custo
    if custo is not None:
        linhas = []
        for m, nome in MODELOS:
            cb = custo[(custo.model == m) & (custo.prompt_type == BASE)].iloc[0]
            cq = custo[(custo.model == m) & (custo.prompt_type == QG)].iloc[0]
            linhas.append({"Model": nome, "Input, default": round(cb.input_tokens, 1), "Input, QG": round(cq.input_tokens, 1),
                           "Added input": f"+{cq.input_tokens - cb.input_tokens:.0f} (+{100 * (cq.input_tokens / cb.input_tokens - 1):.0f}%)",
                           "Output, default": round(cb.output_tokens, 1), "Output, QG": round(cq.output_tokens, 1)})
        t["cost_tokens"] = pd.DataFrame(linhas)
    return t, azure


def carregar_piloto(caminho):
    if not caminho:
        achados = glob.glob(os.path.join("llm", "output", "manual_evaluation", "pilot", "**", "agreement_pilot.xlsx"), recursive=True)
        caminho = achados[0] if achados else None
    if not caminho or not os.path.exists(caminho):
        return None
    df = pd.read_excel(caminho, sheet_name="Resumo", header=2).dropna(subset=["pergunta"])
    df = df[df["pergunta"].astype(str).str.match(r"^(1a|1b|Adequa|3\.)")]
    nomes = {"1a": "Exception type (1a)", "1b": "Reaction to the error (1b)",
             "Adequa": "Adequacy (1a and 1b)", "3.": "Similarity, 1–5 (3)"}
    df["Question"] = [next(v for k, v in nomes.items() if str(p).startswith(k)) for p in df["pergunta"]]
    return pd.DataFrame({"Question": df["Question"], "Agreement (%)": df["concordancia_%"].astype(float),
                         "Krippendorff's α": df["alfa_krippendorff"].astype(float).round(3)})


# --------------------------------------------------------------------------- #
# Figuras
# --------------------------------------------------------------------------- #
def barras_agrupadas(ax, base, qg, ymax, humano=None, rotulo_humano=None):
    x = np.arange(len(MODELOS))
    w = 0.36
    for desloc, vals, cor, rot in ((-w / 2, base, CINZA, "Default prompt"), (w / 2, qg, VERMELHO, "Quality-guided prompt")):
        barras = ax.bar(x + desloc, vals, w, color=cor, label=rot)
        for r, v in zip(barras, vals):
            ax.text(r.get_x() + r.get_width() / 2, v + ymax * 0.015, f"{v:.1f}%", ha="center", va="bottom", fontsize=12, color=TEXTO)
    if humano is not None:
        ax.axhline(humano, ls="--", color=TEXTO, lw=1.2, label=rotulo_humano)
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in MODELOS])
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    # legenda abaixo do gráfico, para não cobrir os rótulos das barras altas
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=11)


def salvar(fig, caminho):
    fig.savefig(caminho, dpi=200, bbox_inches="tight")
    plt.close(fig)


def figuras(t, ps, ref, pasta):
    v, par = t["rq1_violations"], t["rq1_paired"]
    def col(df, coluna, prompt):
        return [df[(df.Model == n) & (df.Prompt == ROTULO_COND[prompt])][coluna].iloc[0] for _, n in MODELOS]
    humano = v[v.Model == "Developers"]

    # Figura 1
    base, qg = col(v, "W0718 or W0707 (%)", BASE), col(v, "W0718 or W0707 (%)", QG)
    fig, ax = plt.subplots(figsize=(10, 5.2))
    barras_agrupadas(ax, base, qg, max(base) * 1.18, humano["W0718 or W0707 (%)"].iloc[0],
                     f"Developer-written handlers: {humano['W0718 or W0707 (%)'].iloc[0]:.1f}%")
    ax.set_ylabel("Handlers with W0718 or W0707")
    ax.set_title(f"QG drops W0718/W0707 violations to ≤{max(qg):.1f}% in all three models", loc="left", fontsize=15, fontweight="bold")
    piores = int(par.Worsened.sum())
    fig.text(0.01, -0.1, f"Valid pairs per model: {', '.join(str(n) for n in par['Valid pairs'])} · McNemar exact test, "
             f"p {par['McNemar p (Holm)'].iloc[0]} (Holm) · functions that got worse: {piores}", fontsize=10, color="#666")
    salvar(fig, os.path.join(pasta, "fig1_rq1_violations.png"))

    # Figura 2
    b = t["pylint_blind_spot"]
    b = b[b.Model != "Developers"]
    series = [(b["Flagged by W0718, default (%)"], CINZA_ESCURO, "Flagged by Pylint W0718 (default prompt)"),
              (b["Actual Exception catch, default (%)"], CINZA, "Actual catch of Exception, via AST (default prompt)"),
              (b["Actual Exception catch, QG (%)"], VERMELHO, "Actual catch of Exception, via AST (QG)")]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    x, w = np.arange(3), 0.26
    topo = max(series[1][0]) * 1.25
    for k, (vals, cor, rot) in enumerate(series):
        barras = ax.bar(x + (k - 1) * w, vals, w, color=cor, label=rot)
        for r, val in zip(barras, vals):
            ax.text(r.get_x() + r.get_width() / 2, val + topo * 0.012, f"{val:.1f}%", ha="center", fontsize=11, color=TEXTO)
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in MODELOS])
    ax.set_ylim(0, topo)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{val:.0f}%"))
    ax.legend(frameon=False, loc="upper left", fontsize=11)
    ax.set_ylabel("Handlers")
    ax.set_title("Pylint misses most broad catches: W0718 ignores handlers that re-raise", loc="left", fontsize=15, fontweight="bold")
    salvar(fig, os.path.join(pasta, "fig2_pylint_blind_spot.png"))

    # Figura 3
    p = t["rq2_patterns"]
    base, qg = col(p, "Contains raise (%)", BASE), col(p, "Contains raise (%)", QG)
    h = p[p.Model == "Developers"]["Contains raise (%)"].iloc[0]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    barras_agrupadas(ax, base, qg, 115, h, f"Developer-written handlers: {h:.1f}%")
    ax.set_ylabel("Handlers that re-raise the error")
    ax.set_title("With QG, models re-raise instead of recovering", loc="left", fontsize=15, fontweight="bold")
    rt = p[(p.Model == "GPT-4o-mini")]["Raises RuntimeError (%)"].tolist()
    rt_h = p[p.Model == "Developers"]["Raises RuntimeError (%)"].iloc[0]
    fig.text(0.01, -0.1, f"GPT-4o-mini raises RuntimeError in {rt[1]:.1f}% of QG handlers ({rt[0]:.1f}% with the default "
             f"prompt, {rt_h:.1f}% in developers' code); Pylint does not flag it", fontsize=10, color="#666")
    salvar(fig, os.path.join(pasta, "fig3_rq2_reraise.png"))

    # Figura 4
    n_func = int(ps.sample_id.nunique())
    fig, ax = plt.subplots(figsize=(12, 4.4))
    ax.axis("off")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4.6)
    caixas = [(0.1, "Base dataset", f"Souza et al. (SBES 2026)\n{n_func} real Python functions\nused unchanged\n\ninput:\nstr_code_without_try_except\n\nreference:\nstr_captures_except", "#F2F2F2"),
              (3.3, "LLM generation", f"{len(MODELOS)} models × 2 prompts\n\ndefault prompt\n\nquality-guided prompt\n(+ W0718 and W0707 rules)", "#FBE3E6"),
              (6.3, "Result records", "one file per\nmodel × prompt\n\nllm_response,\nprompt_type, model,\ntemperature, tokens", "#F2F2F2"),
              (9.3, "Analysis", "extract the except block\n\nPylint + AST\n\ncompare with the\ndeveloper's handler", "#F2F2F2")]
    for x0, titulo, corpo, cor in caixas:
        larg = 2.7 if x0 == 0.1 else 2.5
        ax.add_patch(FancyBboxPatch((x0, 0.4), larg, 3.6, boxstyle="round,pad=0.04,rounding_size=0.15", fc=cor, ec=TEXTO, lw=1.2))
        ax.text(x0 + larg / 2, 3.68, titulo, ha="center", va="top", fontsize=12.5, fontweight="bold", color=TEXTO)
        ax.text(x0 + larg / 2, 3.15, corpo, ha="center", va="top", fontsize=10.5, color=TEXTO, linespacing=1.45)
    for x1, x2 in ((2.85, 3.25), (5.85, 6.25), (8.85, 9.25)):
        ax.annotate("", xy=(x2, 2.2), xytext=(x1, 2.2), arrowprops=dict(arrowstyle="-|>", lw=1.6, color=TEXTO))
    ax.text(0.1, 4.35, "The benchmark is the input and the reference; model outputs are stored separately",
            fontsize=11, color="#555")
    salvar(fig, os.path.join(pasta, "fig4_pipeline.png"))

    # Figura 5
    s = t["rq3_similarity"]
    base, qg = col(s, "Jaccard", BASE), col(s, "Jaccard", QG)
    fig, ax = plt.subplots(figsize=(10, 5.2))
    x, w = np.arange(3), 0.36
    for desloc, vals, cor, rot in ((-w / 2, base, CINZA, "Default prompt"), (w / 2, qg, VERMELHO, "Quality-guided prompt")):
        barras = ax.bar(x + desloc, vals, w, color=cor, label=rot)
        for r, val in zip(barras, vals):
            ax.text(r.get_x() + r.get_width() / 2, val + 0.008, f"{val:.3f}", ha="center", fontsize=12, color=TEXTO)
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in MODELOS])
    ax.set_ylim(0, max(base) * 1.3)
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylabel("Jaccard similarity to developer's handler")
    ax.set_title("With QG, handlers move away from the developer's code", loc="left", fontsize=15, fontweight="bold")
    sig = t["rq3_significance"]
    fig.text(0.01, -0.02, "Wilcoxon signed-rank, Holm-corrected p — Jaccard: " +
             ", ".join(f"{m} {p_}" for m, p_ in zip(sig["Model"], sig["Jaccard p (Holm)"])), fontsize=10, color="#666")
    salvar(fig, os.path.join(pasta, "fig5_rq3_similarity.png"))


def tabela_png(df, caminho, titulo):
    df = df.copy()
    if "Prompt" in df.columns:
        df["Prompt"] = df["Prompt"].replace({"Default prompt": "Default", "Quality-guided prompt": "QG"})
    for c in df.columns:
        decimais = 3 if c.startswith(("Jaccard", "CrystalBLEU", "Krippendorff")) else 1
        df[c] = df[c].apply(lambda v: "—" if (isinstance(v, float) and np.isnan(v)) else
                            (f"{v:.{decimais}f}" if isinstance(v, float) else str(v)))
    cabecalhos = [textwrap.fill(str(c), 16) for c in df.columns]
    pesos = [max(max(len(l) for l in h.split("\n")), df[c].map(len).max()) + 2
             for h, c in zip(cabecalhos, df.columns)]
    total = sum(pesos)
    linhas_cab = max(h.count("\n") + 1 for h in cabecalhos)
    fig, ax = plt.subplots(figsize=(max(6, total * 0.13), 0.8 + 0.4 * (len(df) + linhas_cab)))
    ax.axis("off")
    tab = ax.table(cellText=df.values, colLabels=cabecalhos, loc="center", cellLoc="center",
                   colWidths=[p / total for p in pesos])
    tab.auto_set_font_size(False)
    tab.set_fontsize(11)
    tab.scale(1, 1.6)
    for (lin, _), cel in tab.get_celld().items():
        cel.set_edgecolor("#BFBFBF")
        if lin == 0:
            cel.set_facecolor("#E6E6E6")
            cel.set_text_props(fontweight="bold")
            cel.set_height(cel.get_height() * (0.7 + 0.45 * linhas_cab))
    ax.set_title(titulo, loc="left", fontsize=13, fontweight="bold")
    salvar(fig, caminho)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Gera figuras e tabelas da apresentação a partir dos resultados.")
    ap.add_argument("--analysis", default=os.path.join("llm", "output", "analysis"))
    ap.add_argument("--piloto", default=None, help="caminho do agreement_pilot.xlsx (opcional)")
    ap.add_argument("--out", default=os.path.join("llm", "output", "presentation"))
    args = ap.parse_args()

    ps, ref, testes, custo = carregar(args.analysis)
    t, _ = construir_tabelas(ps, ref, testes, custo)
    piloto = carregar_piloto(args.piloto)
    if piloto is not None:
        t["pilot_agreement"] = piloto

    pasta_fig = os.path.join(args.out, "figures")
    pasta_tab = os.path.join(args.out, "tables")
    os.makedirs(pasta_fig, exist_ok=True)
    os.makedirs(pasta_tab, exist_ok=True)

    figuras(t, ps, ref, pasta_fig)
    titulos = {
        "rq1_violations": "RQ1 · Violations per model and prompt (% of valid handlers)",
        "rq1_paired": "RQ1 · Paired comparison, default vs. quality-guided prompt",
        "pylint_blind_spot": "Pylint W0718 vs. actual catch of Exception (AST)",
        "rq2_patterns": "RQ2 · Handler patterns (% of handlers)",
        "rq2_evasions": "RQ2 · Direct ways around the rules (% of handlers)",
        "rq2_behavior": "RQ2 · What the handler does after catching the error (% of handlers)",
        "rq3_similarity": "RQ3 · Similarity to the developer's handler",
        "rq3_significance": "RQ3 · Significance of the change (Wilcoxon, Holm)",
        "type_choice": "Exception type chosen by QG (outside the Azure SDK cluster)",
        "without_azure": "Results without the near-duplicate Azure SDK cluster",
        "cost_tokens": "Cost: mean tokens per function",
        "pilot_agreement": "Manual evaluation pilot: agreement between raters (before calibration)",
    }
    for nome, df in t.items():
        if nome != "rq2_patterns":   # a versão completa fica só no xlsx/md; no slide, as duas partes
            tabela_png(df, os.path.join(pasta_tab, f"{nome}.png"), titulos.get(nome, nome))

    with pd.ExcelWriter(os.path.join(args.out, "tables.xlsx")) as w:
        for nome, df in t.items():
            df.to_excel(w, sheet_name=nome[:31], index=False)
    with open(os.path.join(args.out, "tables.md"), "w", encoding="utf-8") as f:
        for nome, df in t.items():
            f.write(f"## {titulos.get(nome, nome)}\n\n")
            try:
                f.write(df.to_markdown(index=False))
            except ImportError:
                f.write(df.to_string(index=False))
            f.write("\n\n")

    print("=" * 70)
    print("FIGURAS E TABELAS DA APRESENTAÇÃO")
    print("=" * 70)
    for nome in ("rq1_violations", "rq1_paired", "pylint_blind_spot"):
        print(f"\n{titulos[nome]}\n{t[nome].to_string(index=False)}")
    print("\nArquivos gerados:")
    for raiz, _, arquivos in os.walk(args.out):
        for a in sorted(arquivos):
            print("  ", os.path.join(raiz, a))
    if piloto is None:
        print("\n[aviso] agreement_pilot.xlsx não encontrado: a tabela do piloto não foi gerada.")


if __name__ == "__main__":
    main()
