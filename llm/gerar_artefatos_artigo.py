"""
Gera as tabelas (LaTeX) e os gráficos (PDF vetorial) do artigo a partir dos resultados.

Os números vêm dos mesmos cálculos do gerar_figuras_apresentacao.py, que precisa estar
na mesma pasta: o artigo e os slides usam exatamente os mesmos valores.

Entradas (geradas pelo llm_analysis.py):
    llm/output/analysis/per_sample.csv, reference.csv e paired_tests.csv

Saídas (em llm/output/artigo/), prontas para subir nas pastas de mesmo nome no Overleaf:
    tables/rq1-violations.tex      violações-alvo e capturas reais de Exception (RQ1)
    tables/rq2-behavior.tex        o que o handler faz depois de capturar o erro (RQ2)
    tables/rq3-similarity.tex      semelhança com o handler do desenvolvedor (RQ3)
    figures/rq1-violations.pdf     violações W0718/W0707 por modelo e prompt
    figures/rq2-reraise.pdf        handlers que relançam o erro
    figures/study-design.pdf       fluxo do estudo (entrada, geração, registros, análise)

Uso (a partir da raiz do repositório):
    python llm/gerar_artefatos_artigo.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import gerar_figuras_apresentacao as base
except ImportError:
    sys.exit("[ERRO] gerar_figuras_apresentacao.py precisa estar na mesma pasta deste script.")

import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyBboxPatch        # noqa: E402
from matplotlib.ticker import FuncFormatter          # noqa: E402
import numpy as np                                   # noqa: E402

# Largura de uma coluna no modelo IEEE de conferência: 3,5 polegadas
LARGURA = 3.5
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "TeX Gyre Termes", "Liberation Serif", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7,
    "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
    "pdf.fonttype": 42, "ps.fonttype": 42,          # fontes embutidas, como exige a IEEE
})
CURTO = {"Claude Haiku 4.5": "Claude", "Gemini 3 Flash": "Gemini", "GPT-4o-mini": "GPT"}
SETA = r" $\rightarrow$ "


# --------------------------------------------------------------------------- #
# Tabelas em LaTeX
# --------------------------------------------------------------------------- #
def num(v, casas=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    if casas == 3:
        return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"
    return f"{v:.{casas}f}"


def estrela(p):
    return r"\textsuperscript{*}" if (p is not None and not np.isnan(p) and p < 0.05) else ""


def linha_modelo(df, nome, prompt):
    return df[(df.Model == nome) & (df.Prompt == base.ROTULO_COND[prompt])].iloc[0]


def tabela(caminho, legenda, rotulo, colunas, cabecalho, linhas, nota=None, fonte=r"\footnotesize", sep="2.5pt"):
    corpo = [r"\begin{table}[t]", r"  \centering", f"  {fonte}", rf"  \setlength{{\tabcolsep}}{{{sep}}}",
             rf"  \caption{{{legenda}}}", rf"  \label{{{rotulo}}}", rf"  \begin{{tabular}}{{{colunas}}}",
             r"    \toprule"]
    corpo += [f"    {c}" for c in cabecalho]
    corpo.append(r"    \midrule")
    for ln in linhas:
        corpo.append(r"    \midrule" if ln == "MIDRULE" else f"    {ln} \\\\")
    corpo.append(r"    \bottomrule")
    if nota:
        corpo.append(rf"    \multicolumn{{{len(colunas)}}}{{l}}{{{nota}}}")
    corpo += [r"  \end{tabular}", r"\end{table}", ""]
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("% Gerado por gerar_artefatos_artigo.py; não editar à mão.\n" + "\n".join(corpo))


def tabelas(t, ps, testes, pasta):
    # RQ1
    v, par, cego = t["rq1_violations"], t["rq1_paired"].set_index("Model"), t["pylint_blind_spot"].set_index("Model")
    linhas = []
    for _, nome in base.MODELOS:
        b, q = linha_modelo(v, nome, base.BASE), linha_modelo(v, nome, base.QG)
        linhas.append(f"{nome} & {num(b['W0718 or W0707 (%)'])} & {num(q['W0718 or W0707 (%)'])} & "
                      f"{par.at[nome, 'Improved']} / {par.at[nome, 'Worsened']} & "
                      f"{num(cego.at[nome, 'Actual Exception catch, default (%)'])} & "
                      f"{num(cego.at[nome, 'Actual Exception catch, QG (%)'])}")
    h = v[v.Model == "Developers"].iloc[0]
    linhas += ["MIDRULE", f"Developers & {num(h['W0718 or W0707 (%)'])} & -- & -- & "
                          f"{num(cego.at['Developers', 'Actual Exception catch, default (%)'])} & --"]
    tabela(os.path.join(pasta, "rq1-violations.tex"),
           r"Target violations and actual broad catches (\% of valid handlers)", "tab:rq1", "lccccc",
           [r"& \multicolumn{2}{c}{W0718 or W0707} & & \multicolumn{2}{c}{Catches \texttt{Exception}\textsuperscript{\dag}} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){5-6}",
            r"Model & Def. & QG & Impr./Wors. & Def. & QG \\"],
           linhas, r"\textsuperscript{\dag}Counted in the AST, including re-raising handlers.")

    # RQ2
    p = t["rq2_patterns"]
    cols = [("Contains raise (%)", "Re-raises"), ("Raises RuntimeError (%)", r"\texttt{RuntimeError}"),
            ("Swallows the error (%)", "Swallows")]
    linhas = []
    for _, nome in base.MODELOS:
        b, q = linha_modelo(p, nome, base.BASE), linha_modelo(p, nome, base.QG)
        linhas.append(nome + " & " + " & ".join(num(b[c]) + SETA + num(q[c]) for c, _ in cols))
    h = p[p.Model == "Developers"].iloc[0]
    linhas += ["MIDRULE", "Developers & " + " & ".join(num(h[c]) for c, _ in cols)]
    tabela(os.path.join(pasta, "rq2-behavior.tex"),
           r"What the handler does after catching the error (\% of handlers, default $\rightarrow$ QG)",
           "tab:rq2", "lccc", [r"Model & " + " & ".join(r for _, r in cols) + r" \\"], linhas)

    # RQ3
    s = t["rq3_similarity"]
    metricas = [("BLEU", None, 3), ("CrystalBLEU", "crystalbleu", 3), ("Jaccard", "jaccard", 3),
                ("Type in common with developer (%)", "type_overlap", 1)]
    linhas = []
    for m, nome in base.MODELOS:
        b, q = linha_modelo(s, nome, base.BASE), linha_modelo(s, nome, base.QG)
        celulas = []
        for col, metrica, casas in metricas:
            pv = base.p_holm(testes, m, metrica) if metrica else None
            if col == "BLEU":   # média direta do per_sample.csv, sobre as 379 funções
                vb = base.condicao(ps, m, base.BASE).bleu.mean()
                vq = base.condicao(ps, m, base.QG).bleu.mean()
            else:
                vb, vq = b[col], q[col]
            celulas.append(num(vb, casas) + SETA + num(vq, casas) + estrela(pv))
        linhas.append(CURTO[nome] + " & " + " & ".join(celulas))
    tabela(os.path.join(pasta, "rq3-similarity.tex"),
           r"Similarity to the developer's handler (default $\rightarrow$ QG); $p$ from Wilcoxon, Holm-corrected",
           "tab:rq3", "lcccc", [r"Model & BLEU & CrystalBLEU & Jaccard & Same type (\%) \\"], linhas,
           r"\textsuperscript{*}$p < 0.05$. Same type: at least one exception type in common.",
           fonte=r"\scriptsize")


# --------------------------------------------------------------------------- #
# Gráficos em PDF
# --------------------------------------------------------------------------- #
def barras(caminho, base_vals, qg_vals, humano, rotulo_y, ymax):
    fig, ax = plt.subplots(figsize=(LARGURA, 2.05))
    x, w = np.arange(len(base_vals)), 0.36
    for desl, vals, cor, rot in ((-w / 2, base_vals, base.CINZA, "Default prompt"),
                                 (w / 2, qg_vals, base.VERMELHO, "Quality-guided prompt")):
        bs = ax.bar(x + desl, vals, w, color=cor, label=rot)
        for r, val in zip(bs, vals):
            ax.text(r.get_x() + r.get_width() / 2, val + ymax * 0.015, f"{val:.1f}", ha="center", va="bottom",
                    fontsize=6.5, color=base.TEXTO)
    ax.axhline(humano, ls="--", lw=0.8, color=base.TEXTO, label=f"Developers ({humano:.1f}%)")
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in base.MODELOS])
    ax.set_ylim(0, ymax)
    ax.set_ylabel(rotulo_y)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, handlelength=1.4,
              columnspacing=1.0)
    fig.savefig(caminho, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def diagrama(caminho, n_funcoes):
    fig, ax = plt.subplots(figsize=(LARGURA, 1.05))
    ax.axis("off")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 1.0)
    caixas = [("Benchmark", f"{n_funcoes} functions,\nunchanged", "#F2F2F2"),
              ("Generation", "3 LLMs \u00d7\n2 prompts", "#FBE3E6"),
              ("Records", "outputs per\nmodel/prompt", "#F2F2F2"),
              ("Analysis", "Pylint, AST,\nsimilarity", "#F2F2F2")]
    larg, passo = 0.82, 1.0
    for i, (titulo, corpo, cor) in enumerate(caixas):
        x0 = 0.05 + i * passo
        ax.add_patch(FancyBboxPatch((x0, 0.05), larg, 0.88, boxstyle="round,pad=0.015,rounding_size=0.05",
                                    fc=cor, ec=base.TEXTO, lw=0.6))
        ax.text(x0 + larg / 2, 0.80, titulo, ha="center", va="top", fontsize=7, fontweight="bold", color=base.TEXTO)
        ax.text(x0 + larg / 2, 0.52, corpo, ha="center", va="top", fontsize=6.2, color=base.TEXTO, linespacing=1.25)
        if i < 3:
            ax.annotate("", xy=(x0 + passo + 0.02, 0.49), xytext=(x0 + larg + 0.02, 0.49),
                        arrowprops=dict(arrowstyle="-|>", lw=0.7, color=base.TEXTO, mutation_scale=7))
    fig.savefig(caminho, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def graficos(t, ps, pasta):
    v, p = t["rq1_violations"], t["rq2_patterns"]
    def col(df, c, prompt):
        return [linha_modelo(df, n, prompt)[c] for _, n in base.MODELOS]
    b, q = col(v, "W0718 or W0707 (%)", base.BASE), col(v, "W0718 or W0707 (%)", base.QG)
    barras(os.path.join(pasta, "rq1-violations.pdf"), b, q, v[v.Model == "Developers"].iloc[0]["W0718 or W0707 (%)"],
           "Handlers with W0718 or W0707", max(b) * 1.18)
    b, q = col(p, "Contains raise (%)", base.BASE), col(p, "Contains raise (%)", base.QG)
    barras(os.path.join(pasta, "rq2-reraise.pdf"), b, q, p[p.Model == "Developers"].iloc[0]["Contains raise (%)"],
           "Handlers that re-raise", 115)
    diagrama(os.path.join(pasta, "study-design.pdf"), int(ps.sample_id.nunique()))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Gera tabelas (LaTeX) e gráficos (PDF) do artigo.")
    ap.add_argument("--analysis", default=os.path.join("llm", "output", "analysis"))
    ap.add_argument("--out", default=os.path.join("llm", "output", "artigo"))
    args = ap.parse_args()

    ps, ref, testes, custo = base.carregar(args.analysis)
    t, _ = base.construir_tabelas(ps, ref, testes, custo)
    pasta_tab, pasta_fig = os.path.join(args.out, "tables"), os.path.join(args.out, "figures")
    os.makedirs(pasta_tab, exist_ok=True)
    os.makedirs(pasta_fig, exist_ok=True)
    tabelas(t, ps, testes, pasta_tab)
    graficos(t, ps, pasta_fig)

    print("Arquivos gerados para o Overleaf:")
    for raiz, _, arqs in os.walk(args.out):
        for a in sorted(arqs):
            print("  ", os.path.join(raiz, a))
    print("\nSuba o conteúdo de 'tables' e 'figures' nas pastas de mesmo nome do projeto no Overleaf.")


if __name__ == "__main__":
    main()
