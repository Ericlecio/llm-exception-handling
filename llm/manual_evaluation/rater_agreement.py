"""
Compara as respostas de dois avaliadores (piloto ou avaliação principal).

O que o script faz:
  1. Lê a mesma aba (Piloto ou Avaliacao) das duas planilhas de avaliação.
  2. Confere se as planilhas têm os mesmos itens, na mesma ordem, e se todas as
     respostas estão preenchidas com valores válidos.
  3. Calcula, por pergunta, a concordância percentual e o alfa de Krippendorff
     (nominal para tipo, reação e adequação; ordinal para a nota de 1 a 5).
  4. Lista os itens com divergência, com as respostas e justificativas lado a lado,
     e uma coluna em branco para registrar a decisão da reunião de calibração.

O script não lê o arquivo-chave: modelo e condição continuam ocultos.

Uso (a partir da raiz do repositório):
    python llm/manual_evaluation/rater_agreement.py                    # avaliação principal (120 pares)
    python llm/manual_evaluation/rater_agreement.py --aba Piloto \
        --a llm/output/manual_evaluation/pilot/results/rater_1_pilot_analyzed.xlsx \
        --b llm/output/manual_evaluation/pilot/results/rater_2_pilot_analyzed.xlsx

Saída: agreement_main.xlsx ou agreement_pilot.xlsx, na mesma pasta das planilhas
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

PASTA = os.path.join("llm", "output", "manual_evaluation", "main", "results")
OPCOES = {
    "tipo": {"Sim", "Não", "Não é possível determinar"},
    "reacao": {"Sim", "Não"},
    "nota": {1, 2, 3, 4, 5},
}
PREFIXOS = {"item_id": "Item", "grupo": "Grupo", "funcao": "Função",
            "handler_avaliado": "Handler avaliado", "tipo": "1a.", "reacao": "1b.",
            "justificativa": "2.", "nota": "3."}


def vazio(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == ""


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def ler(caminho, aba):
    if not os.path.exists(caminho):
        sys.exit(f"[ERRO] Arquivo não encontrado: {caminho}")
    df = pd.read_excel(caminho, sheet_name=aba)
    colunas = {}
    for campo, prefixo in PREFIXOS.items():
        achadas = [c for c in df.columns if str(c).startswith(prefixo)]
        if not achadas:
            sys.exit(f"[ERRO] {os.path.basename(caminho)}: coluna '{prefixo}…' não encontrada na aba {aba}")
        colunas[campo] = achadas[0]
    df = df[list(colunas.values())].copy()
    df.columns = list(colunas.keys())
    for campo in ("tipo", "reacao", "justificativa"):
        df[campo] = df[campo].apply(lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else None)
    df["nota"] = pd.to_numeric(df["nota"], errors="coerce")
    df["adequado"] = [
        None if (vazio(t) or vazio(r)) else
        ("Indeterminado" if t == "Não é possível determinar" else ("Sim" if t == "Sim" and r == "Sim" else "Não"))
        for t, r in zip(df["tipo"], df["reacao"])
    ]
    return df


def problemas_de_preenchimento(df, nome):
    erros = []
    for i, r in df.iterrows():
        faltam = [c for c in ("tipo", "reacao", "nota") if vazio(r[c])]
        if faltam:
            erros.append(f"{nome}, {r.item_id}: sem resposta em {', '.join(faltam)}")
            continue
        if r.tipo not in OPCOES["tipo"]:
            erros.append(f"{nome}, {r.item_id}: valor inválido em 1a ({r.tipo})")
        if r.reacao not in OPCOES["reacao"]:
            erros.append(f"{nome}, {r.item_id}: valor inválido em 1b ({r.reacao})")
        if r.nota not in OPCOES["nota"]:
            erros.append(f"{nome}, {r.item_id}: valor inválido na nota ({r.nota})")
        if (r.tipo == "Não" or r.reacao == "Não") and vazio(r.justificativa):
            erros.append(f"{nome}, {r.item_id}: justificativa obrigatória (1a ou 1b = Não) está vazia")
    return erros


# --------------------------------------------------------------------------- #
# Alfa de Krippendorff (Krippendorff, 2008), dois avaliadores, sem dados faltantes
# --------------------------------------------------------------------------- #
def alfa_krippendorff(a, b, nivel, categorias=None):
    valores = sorted(set(a) | set(b)) if categorias is None else list(categorias)
    if len(set(a) | set(b)) < 2:
        return float("nan")   # sem variação: o alfa não é definido
    idx = {v: i for i, v in enumerate(valores)}
    k = len(valores)
    o = np.zeros((k, k))      # matriz de coincidências
    for x, y in zip(a, b):
        o[idx[x], idx[y]] += 1
        o[idx[y], idx[x]] += 1
    n_c = o.sum(axis=1)
    n = n_c.sum()
    delta = np.zeros((k, k))
    for c in range(k):
        for d in range(k):
            if c == d:
                continue
            if nivel == "nominal":
                delta[c, d] = 1.0
            else:   # ordinal
                lo, hi = min(c, d), max(c, d)
                delta[c, d] = (n_c[lo:hi + 1].sum() - (n_c[lo] + n_c[hi]) / 2) ** 2
    d_obs = (o * delta).sum() / n
    d_esp = (np.outer(n_c, n_c) * delta).sum() / (n * (n - 1))
    return float("nan") if d_esp == 0 else 1 - d_obs / d_esp


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Compara as respostas de dois avaliadores.")
    ap.add_argument("--aba", default="Avaliacao", choices=["Piloto", "Avaliacao"])
    ap.add_argument("--a", default=os.path.join(PASTA, "rater_1.xlsx"))
    ap.add_argument("--b", default=os.path.join(PASTA, "rater_2.xlsx"))
    ap.add_argument("--nomes", nargs=2, default=["rater_1", "rater_2"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    na, nb = args.nomes

    a, b = ler(args.a, args.aba), ler(args.b, args.aba)
    if list(a.item_id) != list(b.item_id):
        sys.exit("[ERRO] As duas planilhas não têm os mesmos itens na mesma ordem. "
                 "Confira se ambas vieram da mesma execução do sample_manual_evaluation.py.")

    erros = problemas_de_preenchimento(a, na) + problemas_de_preenchimento(b, nb)
    if erros:
        print(f"[ERRO] Há {len(erros)} problema(s) de preenchimento; corrija antes de comparar:")
        for e in erros:
            print("   ", e)
        sys.exit(1)

    # concordância por pergunta
    perguntas = [("tipo", "1a. Tipo", "nominal", None),
                 ("reacao", "1b. Reação", "nominal", None),
                 ("adequado", "Adequação (derivada de 1a e 1b)", "nominal", None),
                 ("nota", "3. Semelhança (1 a 5)", "ordinal", [1, 2, 3, 4, 5])]
    resumo = []
    for campo, rotulo, nivel, cats in perguntas:
        x, y = list(a[campo]), list(b[campo])
        concord = np.mean([u == v for u, v in zip(x, y)])
        alfa = alfa_krippendorff(x, y, nivel, cats)
        resumo.append({"pergunta": rotulo, "nivel": nivel, "itens": len(x),
                       "concordancia_%": round(100 * concord, 1),
                       "alfa_krippendorff": None if np.isnan(alfa) else round(alfa, 3)})
    resumo = pd.DataFrame(resumo)
    dif_nota = (a.nota - b.nota).abs()
    resumo_nota = {"iguais": int((dif_nota == 0).sum()), "diferença de 1": int((dif_nota == 1).sum()),
                   "diferença de 2 ou mais": int((dif_nota >= 2).sum())}

    # itens com divergência
    div = pd.DataFrame({
        "item_id": a.item_id, "grupo": a.grupo, "funcao": a.funcao, "handler_avaliado": a.handler_avaliado,
        f"1a_{na}": a.tipo, f"1a_{nb}": b.tipo,
        f"1b_{na}": a.reacao, f"1b_{nb}": b.reacao,
        f"nota_{na}": a.nota.astype(int), f"nota_{nb}": b.nota.astype(int),
        f"justificativa_{na}": a.justificativa, f"justificativa_{nb}": b.justificativa,
    })
    div["diverge_em"] = [
        ", ".join(n for n, d in [("1a", a.tipo[i] != b.tipo[i]), ("1b", a.reacao[i] != b.reacao[i]),
                                 ("nota", dif_nota[i] >= 2)] if d)
        for i in range(len(a))
    ]
    div["decisao_calibracao"] = ""
    divergentes = div[div.diverge_em != ""]

    # saída
    out = args.out or os.path.join(os.path.dirname(args.a), f"agreement_{ {'Avaliacao': 'main', 'Piloto': 'pilot'}[args.aba]}.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    ws["A1"] = f"Concordância entre avaliadores, aba {args.aba} ({len(a)} itens)"
    ws["A1"].font = Font(name="Arial", bold=True, size=12)
    for j, col in enumerate(resumo.columns, start=1):
        ws.cell(row=3, column=j, value=col).font = Font(name="Arial", bold=True)
    for i, r in enumerate(resumo.itertuples(index=False), start=4):
        for j, v in enumerate(r, start=1):
            ws.cell(row=i, column=j, value=v).font = Font(name="Arial")
    lin = 4 + len(resumo) + 1
    ws.cell(row=lin, column=1, value="Diferença nas notas de semelhança").font = Font(name="Arial", bold=True)
    for k, (rot, v) in enumerate(resumo_nota.items(), start=1):
        ws.cell(row=lin + k, column=1, value=rot).font = Font(name="Arial")
        ws.cell(row=lin + k, column=2, value=v).font = Font(name="Arial")
    ws.cell(row=lin + 5, column=1, value=(
        "Referência: alfa ≥ 0,800 é considerado confiável e ≥ 0,667 permite conclusões provisórias "
        "(Krippendorff). No estudo de Souza et al. (2026), o alfa foi 0,60. No piloto, o valor serve apenas para orientar a calibração.")
    ).font = Font(name="Arial", italic=True)
    for col, w in zip("ABCDE", (34, 10, 8, 16, 18)):
        ws.column_dimensions[col].width = w

    for nome_aba, dados in [("Divergencias", divergentes), ("Todos os itens", div)]:
        w = wb.create_sheet(nome_aba)
        for j, col in enumerate(dados.columns, start=1):
            c = w.cell(row=1, column=j, value=col)
            c.font = Font(name="Arial", bold=True)
            c.fill = PatternFill("solid", fgColor="D9D9D9")
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for i, r in enumerate(dados.itertuples(index=False), start=2):
            for j, v in enumerate(r, start=1):
                c = w.cell(row=i, column=j, value=None if (isinstance(v, float) and np.isnan(v)) else v)
                c.font = Font(name="Courier New" if dados.columns[j - 1] == "handler_avaliado" else "Arial", size=9)
                c.alignment = Alignment(wrap_text=True, vertical="top")
                if dados.columns[j - 1] == "decisao_calibracao":
                    c.fill = PatternFill("solid", fgColor="FFF2CC")
        larguras = {"item_id": 9, "grupo": 7, "funcao": 20, "handler_avaliado": 45, "diverge_em": 14,
                    "decisao_calibracao": 40}
        for j, col in enumerate(dados.columns, start=1):
            letra = w.cell(row=1, column=j).column_letter
            w.column_dimensions[letra].width = larguras.get(col, 30 if col.startswith("justificativa") else 12)
        w.freeze_panes = "B2"
    wb.save(out)

    print("=" * 70)
    print(f"COMPARAÇÃO DOS AVALIADORES: aba {args.aba} ({len(a)} itens)")
    print("=" * 70)
    print(resumo.to_string(index=False))
    print("\nNotas de semelhança:", ", ".join(f"{k}: {v}" for k, v in resumo_nota.items()))
    print(f"\nItens com divergência em 1a, 1b ou nota (diferença ≥ 2): {len(divergentes)} de {len(a)}")
    print(f"Relatório salvo em {out}")
    if args.aba == "Piloto":
        print("\nUse a aba 'Divergencias' na reunião de calibração e registre as regras na aba Decisões das duas planilhas.")


if __name__ == "__main__":
    main()
