"""
Análise da Task 4: prompt padrão (style-default) vs Quality-Guided (style-qg-default).

RQ1  O QG reduz W0718 (broad-exception-caught) e W0707 (raise-missing-from)?
RQ2  A redução vem acompanhada de efeitos colaterais?
     (W0702 bare-except, W0706 try-except-raise, capturas genéricas que o Pylint
     não marca porque o handler relança, respostas inválidas)
RQ3  O QG preserva a similaridade com o código dos desenvolvedores?
     (BLEU, CrystalBLEU, Jaccard, Exact Match, concordância de tipos de exceção)

Uso (a partir da raiz do repositório; os CSVs podem estar em subpastas de llm/output):
    python llm/analysis/analyze_handlers.py
    python llm/analysis/analyze_handlers.py --input-dir llm/output --out-dir llm/output/analysis

Diferenças em relação ao script original:
  * respostas com \r\n são extraídas corretamente;
  * respostas sem código ou que não fazem parse são contadas como INVÁLIDAS,
    nunca como "limpas" e nunca embrulhadas num `except Exception:` artificial;
  * o Pylint roda com overgeneral-exceptions em nome completo (builtins.*),
    obrigatório nas versões atuais para o W0718 funcionar;
  * as violações são registradas por código e por snippet (0/1), o que permite
    o teste pareado de McNemar;
  * os "crystals" do CrystalBLEU vêm do código de referência (fixo), e não das
    respostas dos modelos, então as notas não mudam quando novos arquivos entram.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import warnings
from collections import Counter

import numpy as np
import pandas as pd
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from scipy.stats import binomtest, wilcoxon

try:
    from crystalbleu import sentence_bleu as crystal_bleu
except ImportError:  # CrystalBLEU é opcional
    crystal_bleu = None

warnings.filterwarnings("ignore")

BASELINE = "style-default"
QG = "style-qg-default"
TARGET_CODES = ["W0718", "W0707"]          # RQ1: as duas regras do prompt QG
SIDE_CODES = ["W0702", "W0706"]            # RQ2: possíveis "rotas de fuga"
ALL_CODES = TARGET_CODES + SIDE_CODES
BROAD_NAMES = {"Exception", "BaseException"}
FILE_RE = re.compile(r"^(?P<project>[^_]+)_(?P<model>.+)_task4_(?P<style>style-[\w-]+)_results\.csv$")


# --------------------------------------------------------------------------- #
# Extração e normalização do código
# --------------------------------------------------------------------------- #
def extract_code(response):
    """Extrai o bloco de código da resposta (markdown ou <code>). '' se não houver."""
    if not isinstance(response, str):
        return ""
    text = response.replace("\r\n", "\n").replace("\r", "\n")
    m = re.search(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)\n?```", text, re.S)
    if not m:
        m = re.search(r"<code>(.*?)</code>", text, re.S)
    return m.group(1).strip("\n") if m else ""


def reference_code(raw):
    """str_captures_except vem como lista serializada; junta os handlers."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return "\n".join(str(p) for p in parsed).replace("\r\n", "\n")
        except (ValueError, SyntaxError):
            pass
    return raw.replace("\r\n", "\n")


def make_analyzable(code):
    """
    Devolve um módulo Python válido contendo o handler, ou None se for inválido.
    Nunca inventa um `except` — se não der para analisar, a resposta é inválida.
    """
    if not code.strip():
        return None
    body = textwrap.dedent(code).strip("\n")
    first = body.lstrip().split("\n", 1)[0]
    candidates = []
    if first.startswith("except"):
        block = "try:\n    pass\n" + body
        candidates += [
            "def _f():\n" + textwrap.indent(block, "    ") + "\n",
            "async def _f():\n" + textwrap.indent(block, "    ") + "\n",
        ]
    else:  # o modelo devolveu o try/except completo (ou trecho maior)
        candidates += [
            "def _f():\n" + textwrap.indent(body, "    ") + "\n",
            "async def _f():\n" + textwrap.indent(body, "    ") + "\n",
        ]
    for src in candidates:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        if any(isinstance(n, ast.ExceptHandler) for n in ast.walk(tree)):
            return src
    return None


# --------------------------------------------------------------------------- #
# Métricas estruturais (AST)
# --------------------------------------------------------------------------- #
def handler_types(src):
    """Nomes das exceções capturadas (último componente: requests.RequestException -> RequestException)."""
    names, bare = set(), False
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare = True
                continue
            elts = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for e in elts:
                names.add(ast.unparse(e).split(".")[-1])
    return names, bare


def ast_features(src):
    if not isinstance(src, str):
        return {"ast_broad": np.nan, "ast_bare": np.nan, "n_types": np.nan, "types": ""}
    names, bare = handler_types(src)
    return {
        "ast_broad": int(bool(names & BROAD_NAMES)),
        "ast_bare": int(bare),
        "n_types": len(names),
        "types": ",".join(sorted(names)),
    }


# --------------------------------------------------------------------------- #
# Pylint (uma única execução para todos os arquivos)
# --------------------------------------------------------------------------- #
def run_pylint(sources):
    """sources: dict id -> código. Retorna dict id -> set de códigos de violação."""
    result = {k: set() for k in sources}
    if not sources:
        return result
    with tempfile.TemporaryDirectory(prefix="eh_") as tmp:
        names = {}
        for i, (key, src) in enumerate(sources.items()):
            name = f"s{i}"
            names[name] = key
            with open(os.path.join(tmp, f"{name}.py"), "w", encoding="utf-8") as f:
                f.write(src)
        cmd = [
            sys.executable, "-m", "pylint", tmp,
            "--rcfile=" + os.devnull,
            "--disable=all", "--enable=" + ",".join(ALL_CODES),
            "--overgeneral-exceptions=builtins.BaseException,builtins.Exception",
            "--output-format=json", "--persistent=n", "--score=n",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = proc.stdout.strip()
        if not out:
            if proc.returncode not in (0,) and proc.stderr:
                raise RuntimeError("Pylint falhou:\n" + proc.stderr[-2000:])
            return result
        for msg in json.loads(out):
            name = os.path.splitext(os.path.basename(msg["path"]))[0]
            code = msg.get("message-id")
            if name in names and code in ALL_CODES:
                result[names[name]].add(code)
    return result


# --------------------------------------------------------------------------- #
# Similaridade
# --------------------------------------------------------------------------- #
def tokenize(code):
    return re.findall(r"\w+|[()[\]{},:.;=<>!+\-/*&|]", code or "")


def ngrams(tokens, n):
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def build_crystals(reference_codes, k=500):
    counts = Counter()
    for code in reference_codes:
        toks = tokenize(code)
        for n in range(1, 5):
            counts.update(ngrams(toks, n))
    return [g for g, _ in counts.most_common(k)]


# --------------------------------------------------------------------------- #
# Estatística
# --------------------------------------------------------------------------- #
def mcnemar_exact(x_base, x_qg):
    """x_*: arrays 0/1 pareados. b = só baseline tem; c = só QG tem."""
    b = int(((x_base == 1) & (x_qg == 0)).sum())
    c = int(((x_base == 0) & (x_qg == 1)).sum())
    p = 1.0 if b + c == 0 else binomtest(b, b + c, 0.5).pvalue
    return b, c, p


def holm(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p) - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def load_results(input_dir, include_incomplete=False):
    """
    Procura os CSVs da Task 4 em input_dir e em todas as subpastas.
    Arquivos com respostas faltando (coleta em andamento) são ignorados,
    a não ser que include_incomplete=True.
    """
    found = {}
    for root, _dirs, files in os.walk(input_dir):
        if os.path.basename(root) == "analysis":
            continue
        for fname in sorted(files):
            m = FILE_RE.match(fname)
            if not m:
                continue
            key = (m.group("model"), m.group("style"))
            path = os.path.join(root, fname)
            if key in found:
                sys.exit(f"Arquivo duplicado para {key}:\n  {found[key]}\n  {path}\n"
                         "Deixe só uma cópia de cada condição dentro de --input-dir.")
            found[key] = path

    frames = []
    for (model, style), path in sorted(found.items()):
        df = pd.read_csv(path)
        missing = df["llm_response"].isna().sum() + (df["llm_response"].astype(str).str.strip() == "").sum()
        rel = os.path.relpath(path, input_dir)
        if missing and not include_incomplete:
            print(f"  [ignorado] {rel}: {missing} de {len(df)} linhas sem resposta (coleta incompleta)")
            continue
        df["sample_id"] = range(len(df))
        df["model"] = model
        df["prompt_type"] = style
        df["source_file"] = rel
        frames.append(df)
        print(f"  carregado: {rel} ({len(df)} linhas)")
    if not frames:
        sys.exit(f"Nenhum arquivo *_task4_*_results.csv completo encontrado em {input_dir}")
    return pd.concat(frames, ignore_index=True)


def analyze(df):
    # ----- referência humana (uma vez por snippet) -----
    ref = (
        df.drop_duplicates("sample_id")
        .set_index("sample_id")[["function", "str_captures_except"]]
        .copy()
    )
    ref["ref_code"] = ref["str_captures_except"].apply(reference_code)
    ref["ref_src"] = ref["ref_code"].apply(make_analyzable)

    # ----- respostas dos modelos -----
    df = df.copy()
    df["pred_code"] = df["llm_response"].apply(extract_code)
    df["pred_src"] = df["pred_code"].apply(make_analyzable)
    df["status"] = np.where(
        df["llm_response"].isna(), "sem_resposta",
        np.where(df["pred_code"].str.strip() == "", "sem_codigo",
                 np.where(df["pred_src"].isna(), "sintaxe_invalida", "valido")))
    df["valid"] = (df["status"] == "valido").astype(int)

    # ----- Pylint em lote -----
    sources = {("pred", i): s for i, s in df["pred_src"].items() if isinstance(s, str)}
    sources.update({("ref", i): s for i, s in ref["ref_src"].items() if isinstance(s, str)})
    print(f"  rodando Pylint em {len(sources)} blocos...")
    hits = run_pylint(sources)

    for code in ALL_CODES:
        df[code] = [
            int(code in hits[("pred", i)]) if isinstance(s, str) else np.nan
            for i, s in df["pred_src"].items()
        ]
        ref[code] = [
            int(code in hits[("ref", i)]) if isinstance(s, str) else np.nan
            for i, s in ref["ref_src"].items()
        ]
    df["any_target"] = df[TARGET_CODES].max(axis=1, skipna=False)
    ref["any_target"] = ref[TARGET_CODES].max(axis=1, skipna=False)

    df = pd.concat([df, df["pred_src"].apply(ast_features).apply(pd.Series)], axis=1)
    ref = pd.concat([ref, ref["ref_src"].apply(ast_features).apply(pd.Series)], axis=1)
    df["broad_hidden"] = ((df["ast_broad"] == 1) & (df["W0718"] == 0)).astype(float).where(df["valid"] == 1)
    ref["broad_hidden"] = ((ref["ast_broad"] == 1) & (ref["W0718"] == 0)).astype(float).where(ref["ref_src"].notna())

    # ----- similaridade com a referência -----
    crystals = build_crystals(ref["ref_code"])
    smooth = SmoothingFunction().method1
    rows = []
    for i, r in df.iterrows():
        rc = ref.loc[r["sample_id"]]
        rt, ht = tokenize(rc["ref_code"]), tokenize(r["pred_code"])
        if ht and rt:
            bleu = sentence_bleu([rt], ht, smoothing_function=smooth)
            cbleu = (crystal_bleu([rt], ht, ignoring=crystals, smoothing_function=smooth)
                     if crystal_bleu else np.nan)
        else:
            bleu, cbleu = 0.0, (0.0 if crystal_bleu else np.nan)
        st, sp = set(rt), set(ht)
        jacc = len(st & sp) / len(st | sp) if st | sp else 0.0
        exact = int(bool(rt) and rt == ht)
        ref_types = set(filter(None, rc["types"].split(","))) if isinstance(rc["types"], str) else set()
        pred_types = set(filter(None, r["types"].split(","))) if isinstance(r["types"], str) else set()
        rows.append({
            "bleu": bleu, "crystalbleu": cbleu, "jaccard": jacc, "exact_match": exact,
            # Só faz sentido quando a referência nomeia algum tipo (exclui `except:` puro)
            "type_overlap": int(bool(ref_types & pred_types)) if ref_types else np.nan,
            "type_exact": int(ref_types == pred_types) if ref_types else np.nan,
        })
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    return df, ref


def rate(series):
    """Proporção sobre os blocos válidos e contagem absoluta."""
    s = series.dropna()
    return (s.mean() if len(s) else np.nan), int(s.sum())


def build_tables(df, ref):
    n_ref = len(ref)
    groups = list(df.groupby(["model", "prompt_type"], sort=True))

    # ---------------- RQ1 / RQ2: violações ----------------
    viol_rows = []
    for (model, style), g in groups:
        row = {"model": model, "prompt_type": style, "n": len(g),
               "validos": int(g["valid"].sum()),
               "invalidos": int(len(g) - g["valid"].sum())}
        for col in ALL_CODES + ["any_target", "broad_hidden", "ast_broad"]:
            pct, cnt = rate(g[col])
            row[f"{col}_n"] = cnt
            row[f"{col}_%"] = round(100 * pct, 1)
        row["violacoes_por_amostra"] = round(g[ALL_CODES].sum(axis=1, min_count=1).mean(), 3)
        viol_rows.append(row)
    row = {"model": "HUMANO (referência)", "prompt_type": "-", "n": n_ref,
           "validos": int(ref["ref_src"].notna().sum()),
           "invalidos": int(ref["ref_src"].isna().sum())}
    for col in ALL_CODES + ["any_target", "broad_hidden", "ast_broad"]:
        pct, cnt = rate(ref[col])
        row[f"{col}_n"] = cnt
        row[f"{col}_%"] = round(100 * pct, 1)
    row["violacoes_por_amostra"] = round(ref[ALL_CODES].sum(axis=1, min_count=1).mean(), 3)
    viol_rows.append(row)
    violations = pd.DataFrame(viol_rows)

    # ---------------- RQ3: similaridade ----------------
    sim_cols = ["bleu", "crystalbleu", "jaccard", "exact_match", "type_overlap", "type_exact", "n_types"]
    similarity = (df.groupby(["model", "prompt_type"])[sim_cols].mean().round(3).reset_index())

    # ---------------- custo ----------------
    cost_cols = [c for c in ["input_tokens", "output_tokens", "thinking_tokens"] if c in df.columns]
    cost = df.groupby(["model", "prompt_type"])[cost_cols].mean().round(1).reset_index()

    # ---------------- testes pareados baseline x QG ----------------
    tests = []
    for model, gm in df.groupby("model"):
        styles = set(gm["prompt_type"])
        if not {BASELINE, QG} <= styles:
            print(f"  [aviso] {model}: faltando {sorted({BASELINE, QG} - styles)}; sem teste pareado.")
            continue
        base = gm[gm["prompt_type"] == BASELINE].set_index("sample_id")
        qg = gm[gm["prompt_type"] == QG].set_index("sample_id")
        common = base.index.intersection(qg.index)
        if not (base.loc[common, "function"] == qg.loc[common, "function"]).all():
            raise ValueError(f"{model}: as linhas de baseline e QG não estão na mesma ordem.")
        both_valid = common[(base.loc[common, "valid"] == 1) & (qg.loc[common, "valid"] == 1)]

        model_tests = []
        # Validade: em TODAS as linhas (resposta inválida é um desfecho)
        b, c, p = mcnemar_exact(1 - base.loc[common, "valid"].values, 1 - qg.loc[common, "valid"].values)
        model_tests.append(("invalidas", "RQ2", len(common), b, c, p,
                            100 * (1 - base.loc[common, "valid"].mean()),
                            100 * (1 - qg.loc[common, "valid"].mean())))
        # Violações: nas linhas válidas nas duas condições
        for col, rq in [("W0718", "RQ1"), ("W0707", "RQ1"), ("any_target", "RQ1"),
                        ("W0702", "RQ2"), ("W0706", "RQ2"), ("broad_hidden", "RQ2"),
                        ("ast_broad", "RQ2")]:
            xb = base.loc[both_valid, col].astype(int).values
            xq = qg.loc[both_valid, col].astype(int).values
            b, c, p = mcnemar_exact(xb, xq)
            model_tests.append((col, rq, len(both_valid), b, c, p, 100 * xb.mean(), 100 * xq.mean()))
        # Similaridade: Wilcoxon pareado em todas as linhas
        for col in ["jaccard", "crystalbleu", "type_overlap"]:
            xb, xq = base.loc[common, col].values.astype(float), qg.loc[common, col].values.astype(float)
            keep = ~(np.isnan(xb) | np.isnan(xq))
            xb, xq = xb[keep], xq[keep]
            if len(xb) == 0:
                continue
            diff = xq - xb
            p = 1.0 if np.allclose(diff, 0) else wilcoxon(xb, xq, zero_method="wilcox").pvalue
            model_tests.append((col, "RQ3", len(xb), None, None, p,
                                np.nanmean(xb), np.nanmean(xq)))

        adj = holm([t[5] for t in model_tests])
        for t, pa in zip(model_tests, adj):
            metric, rq, n, b, c, p, vb, vq = t
            tests.append({
                "model": model, "rq": rq, "metrica": metric, "n_pares": n,
                "baseline": round(vb, 3), "qg": round(vq, 3),
                "so_baseline(b)": b, "so_qg(c)": c,
                "teste": "McNemar exato" if b is not None else "Wilcoxon",
                "p": p, "p_holm": pa, "signif_0.05": "sim" if pa < 0.05 else "não",
            })
    return violations, similarity, cost, pd.DataFrame(tests)


def to_markdown(df):
    try:
        return df.to_markdown(index=False)
    except ImportError:
        return df.to_string(index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", default=os.path.join("llm", "output", "generation"))
    ap.add_argument("--out-dir", default=os.path.join("llm", "output", "analysis"))
    ap.add_argument("--include-incomplete", action="store_true",
                    help="inclui arquivos com linhas ainda sem resposta (contadas como inválidas)")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    print("Carregando resultados...")
    df = load_results(args.input_dir, args.include_incomplete)
    print("Analisando...")
    df, ref = analyze(df)
    violations, similarity, cost, tests = build_tables(df, ref)

    keep = ["sample_id", "function", "model", "prompt_type", "status", "pred_code"] + ALL_CODES + [
        "any_target", "ast_broad", "broad_hidden", "ast_bare", "types", "n_types",
        "bleu", "crystalbleu", "jaccard", "exact_match", "type_overlap", "type_exact"]
    df[keep].to_csv(os.path.join(args.out_dir, "per_sample.csv"), index=False)
    ref.reset_index()[["sample_id", "function", "ref_code"] + ALL_CODES + ["ast_broad", "broad_hidden", "types"]] \
        .to_csv(os.path.join(args.out_dir, "reference.csv"), index=False)
    violations.to_csv(os.path.join(args.out_dir, "rq1_rq2_violations.csv"), index=False)
    similarity.to_csv(os.path.join(args.out_dir, "rq3_similarity.csv"), index=False)
    cost.to_csv(os.path.join(args.out_dir, "cost_tokens.csv"), index=False)
    tests.to_csv(os.path.join(args.out_dir, "paired_tests.csv"), index=False)

    status = df.groupby(["model", "prompt_type"])["status"].value_counts().unstack(fill_value=0).reset_index()
    status.to_csv(os.path.join(args.out_dir, "response_status.csv"), index=False)

    pct_cols = ["model", "prompt_type", "n", "invalidos"] + [f"{c}_%" for c in
               ["W0718", "W0707", "any_target", "W0702", "W0706", "broad_hidden"]] + ["violacoes_por_amostra"]
    report = [
        "# Task 4: Baseline vs Quality-Guided\n",
        "Percentuais calculados sobre os blocos válidos. `broad_hidden` = captura de "
        "Exception/BaseException que o Pylint não marca porque o handler relança.\n",
        "## RQ1/RQ2: violações\n", to_markdown(violations[pct_cols]), "",
        "## RQ3: similaridade com o código humano\n", to_markdown(similarity), "",
        "## Status das respostas\n", to_markdown(status), "",
        "## Custo médio (tokens)\n", to_markdown(cost), "",
        "## Testes pareados (baseline x QG, Holm por modelo)\n",
        to_markdown(tests) if len(tests) else "_Ainda não há pares baseline/QG completos._", "",
    ]
    with open(os.path.join(args.out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("\n".join(report))
    print(f"\nArquivos salvos em {args.out_dir}")


if __name__ == "__main__":
    main()
