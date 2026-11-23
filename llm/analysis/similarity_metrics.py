"""
Métricas de similaridade complementares (RQ3): CodeBLEU, concordância de ação e medianas.

O que o script calcula, para cada handler gerado, em relação ao handler do desenvolvedor:
  1. CodeBLEU (Ren et al., 2020) com três componentes: n-gramas, n-gramas ponderados por
     palavras-chave e correspondência sintática (AST). O componente de fluxo de dados fica
     de fora porque não é definido para a maioria dos blocos except, que são curtos
     (a própria biblioteca recomenda ignorá-lo nesses casos).
  2. Concordância de ação: o que o handler faz depois de capturar o erro, classificado em
     raise (relança ou lança outra exceção), return (devolve um valor), log (só registra ou
     imprime), ignore (pass ou continue) ou other; a métrica indica se o handler gerado faz
     a mesma coisa que o do desenvolvedor.
  3. Média e mediana de todas as métricas de similaridade por modelo e prompt.

Testes pareados, prompt padrão x QG, por modelo, com correção de Holm entre as três
medidas: Wilcoxon para o CodeBLEU e McNemar exato para as concordâncias de ação e de tipo
(medidas binárias).

Entradas (geradas pelo analyze_handlers.py):
    llm/output/analysis/per_sample.csv e reference.csv
Saídas (em llm/output/analysis/):
    similarity_extra_per_sample.csv    uma linha por handler
    similarity_extra.csv                médias, medianas e testes por modelo e prompt

Uso (a partir da raiz do repositório):
    python llm/analysis/similarity_metrics.py
"""

import argparse
import ast
import logging
import os
import sys
import textwrap

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

try:
    from codebleu import calc_codebleu
except ImportError:
    sys.exit("[ERRO] Instale o CodeBLEU: python -m pip install codebleu tree-sitter-python")

logging.disable(logging.WARNING)   # a biblioteca avisa a cada chamada sobre o fluxo de dados
PESOS_CODEBLEU = (1 / 3, 1 / 3, 1 / 3, 0)
BASE, QG = "style-default", "style-qg-default"
ACOES = ["raise", "return", "log", "ignore", "other"]


def normalizar(code):
    return textwrap.dedent(str(code).replace("\r\n", "\n")).strip("\n")


def como_bloco(code):
    """Embrulha o except num try mínimo, para que o trecho seja Python válido."""
    code = normalizar(code)
    return code if code.lstrip().startswith("try") else "try:\n    pass\n" + code + "\n"


def acao(code):
    if not isinstance(code, str) or not code.strip():
        return None
    try:
        arvore = ast.parse(como_bloco(code))
    except SyntaxError:
        return None
    corpos = [s for h in ast.walk(arvore) if isinstance(h, ast.ExceptHandler) for s in h.body
              if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if not corpos:
        return "ignore"
    if any(isinstance(n, ast.Raise) for s in corpos for n in ast.walk(s)):
        return "raise"
    if all(isinstance(s, (ast.Pass, ast.Continue)) for s in corpos):
        return "ignore"
    if any(isinstance(n, ast.Return) for s in corpos for n in ast.walk(s)):
        return "return"
    if all(isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
           and any(k in ast.unparse(s.value.func).lower() for k in ("log", "print", "warn")) for s in corpos):
        return "log"
    return "other"


def codebleu(gerado, referencia):
    if not isinstance(gerado, str) or not gerado.strip():
        return 0.0
    try:
        return float(calc_codebleu([como_bloco(referencia)], [como_bloco(gerado)], lang="python",
                                   weights=PESOS_CODEBLEU)["codebleu"])
    except Exception:   # trecho que o parser não aceita: sem semelhança mensurável
        return 0.0


def holm(ps):
    ordem = np.argsort(ps)
    ajust, acumulado = np.empty(len(ps)), 0.0
    for i, j in enumerate(ordem):
        acumulado = max(acumulado, min(1.0, (len(ps) - i) * ps[j]))
        ajust[j] = acumulado
    return ajust


def main():
    ap = argparse.ArgumentParser(description="CodeBLEU, concordância de ação e medianas (RQ3).")
    ap.add_argument("--analysis", default=os.path.join("llm", "output", "analysis"))
    args = ap.parse_args()

    ps_path, ref_path = os.path.join(args.analysis, "per_sample.csv"), os.path.join(args.analysis, "reference.csv")
    for c in (ps_path, ref_path):
        if not os.path.exists(c):
            sys.exit(f"[ERRO] {c} não encontrado. Rode antes: python llm/analysis/analyze_handlers.py")
    ps = pd.read_csv(ps_path)
    ref = pd.read_csv(ref_path).set_index("sample_id")
    ref["acao_ref"] = ref["ref_code"].apply(acao)

    print(f"Calculando CodeBLEU e ações para {len(ps)} handlers (pode levar alguns minutos)...")
    linhas = []
    for r in ps.itertuples(index=False):
        valido = r.status == "valido"
        rc = ref.at[r.sample_id, "ref_code"]
        a_ger = acao(r.pred_code) if valido else None
        a_ref = ref.at[r.sample_id, "acao_ref"]
        linhas.append({
            "model": r.model, "prompt_type": r.prompt_type, "sample_id": r.sample_id, "status": r.status,
            "codebleu": codebleu(r.pred_code, rc) if valido else 0.0,
            "acao_gerada": a_ger, "acao_desenvolvedor": a_ref,
            "mesma_acao": (float(a_ger == a_ref) if (a_ger is not None and a_ref is not None) else np.nan),
            "bleu": r.bleu, "crystalbleu": r.crystalbleu, "jaccard": r.jaccard,
        })
    por_amostra = pd.DataFrame(linhas)
    por_amostra.to_csv(os.path.join(args.analysis, "similarity_extra_per_sample.csv"), index=False)

    resumo = []
    for m in sorted(por_amostra.model.unique()):
        g = por_amostra[por_amostra.model == m]
        b = g[g.prompt_type == BASE].set_index("sample_id").sort_index()
        q = g[g.prompt_type == QG].set_index("sample_id").sort_index()
        p_cb = wilcoxon(b.codebleu, q.codebleu).pvalue if not np.allclose(b.codebleu, q.codebleu) else 1.0
        ok = b.mesma_acao.notna() & q.mesma_acao.notna()
        piorou = int(((b.mesma_acao[ok] == 1) & (q.mesma_acao[ok] == 0)).sum())
        melhorou = int(((b.mesma_acao[ok] == 0) & (q.mesma_acao[ok] == 1)).sum())
        p_ac = binomtest(piorou, piorou + melhorou).pvalue if piorou + melhorou else 1.0
        # concordância de tipo (binária): McNemar exato nos pares em que o desenvolvedor nomeia um tipo
        tb = ps[(ps.model == m) & (ps.prompt_type == BASE)].set_index("sample_id").type_overlap
        tq = ps[(ps.model == m) & (ps.prompt_type == QG)].set_index("sample_id").type_overlap
        okt = tb.notna() & tq.notna()
        t_piorou = int(((tb[okt] == 1) & (tq[okt] == 0)).sum())
        t_melhorou = int(((tb[okt] == 0) & (tq[okt] == 1)).sum())
        p_tp = binomtest(t_piorou, t_piorou + t_melhorou).pvalue if t_piorou + t_melhorou else 1.0
        p_cb_h, p_ac_h, p_tp_h = holm(np.array([p_cb, p_ac, p_tp]))
        for cond, d in ((BASE, b), (QG, q)):
            linha = {"model": m, "prompt_type": cond,
                     "same_action_pct": round(100 * d.mesma_acao[ok].mean(), 1),   # só pares válidos nas duas condições
                     "same_action_pairs_lost": piorou, "same_action_pairs_gained": melhorou,
                     "p_holm_codebleu": p_cb_h, "p_holm_same_action": p_ac_h,
                     "same_type_pct": round(100 * (tb if cond == BASE else tq)[okt].mean(), 1),
                     "same_type_pairs": int(okt.sum()), "p_holm_same_type": p_tp_h}
            for met in ("codebleu", "bleu", "crystalbleu", "jaccard"):
                linha[f"{met}_mean"] = round(d[met].mean(), 3)
                linha[f"{met}_median"] = round(d[met].median(), 3)
            dist = d.acao_gerada.value_counts(normalize=True)
            for a in ACOES:
                linha[f"acao_{a}_pct"] = round(100 * dist.get(a, 0.0), 1)
            resumo.append(linha)
    resumo = pd.DataFrame(resumo)
    dist_ref = ref.acao_ref.value_counts(normalize=True)
    dev = {"model": "developers", "prompt_type": "reference"}
    dev.update({f"acao_{a}_pct": round(100 * dist_ref.get(a, 0.0), 1) for a in ACOES})
    resumo = pd.concat([resumo, pd.DataFrame([dev])], ignore_index=True)
    resumo.to_csv(os.path.join(args.analysis, "similarity_extra.csv"), index=False)

    pd.set_option("display.width", 200)
    print("\nMÉDIAS E MEDIANAS (prompt padrão x QG)")
    print(resumo[["model", "prompt_type", "codebleu_mean", "codebleu_median", "crystalbleu_median",
                  "jaccard_median", "same_action_pct", "same_type_pct", "p_holm_codebleu", "p_holm_same_action",
                  "p_holm_same_type"]].to_string(index=False))
    print("\nDISTRIBUIÇÃO DAS AÇÕES (% dos handlers)")
    print(resumo[["model", "prompt_type"] + [f"acao_{a}_pct" for a in ACOES]].to_string(index=False))
    print(f"\nArquivos salvos em {args.analysis}: similarity_extra.csv e similarity_extra_per_sample.csv")


if __name__ == "__main__":
    main()