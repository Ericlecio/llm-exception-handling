"""
Verificação dos CSVs gerados pelo llm.py (Task 4).

Procura todos os arquivos *_task4_*_results.csv em llm/output/geracao (inclusive em
subpastas) e confere, para cada um:
  1. se tem as 379 linhas da Task 4, na mesma ordem do dataset base;
  2. se as colunas originais vieram intactas (mesma função, mesmo snippet);
  3. se as colunas que o llm.py acrescenta existem e seguem o padrão
     (task, prompt_type, modelo, temperatura, versão);
  4. se todas as respostas estão preenchidas e contêm um bloco de código;
  5. se os tokens são números válidos;
  6. se cada modelo tem as duas condições (baseline e QG).

Uso (a partir da raiz do repositório):
    python llm/analise_dados.py
    python llm/analise_dados.py --base data/balanced_sample.csv --output llm/output/geracao
"""

import argparse
import os
import re
import sys

import pandas as pd

FILE_RE = re.compile(r"^(?P<project>[^_]+)_(?P<model>.+)_task4_(?P<style>style-[\w-]+)_results\.csv$")
CONDICOES = ["style-default", "style-qg-default"]

COLUNAS_LLM_OBRIGATORIAS = ["task", "prompt_type", "llm_response", "input_tokens", "output_tokens"]
COLUNAS_LLM_METADADOS = ["model", "model_version", "temperature", "thinking_tokens", "collected_at"]

DESCRICAO_COLUNAS = {
    "function": "Nome da função original.",
    "func_body": "Função original completa, com o try/except do desenvolvedor.",
    "str_code_without_try_except": "Função sem o bloco try/except; é a entrada do modelo.",
    "str_captures_except": "Bloco except escrito pelo desenvolvedor; é a referência.",
    "n_try_except": "Se a função original tinha try/except (1 = sim). A Task 4 usa só as linhas com 1.",
    "task": "Tarefa executada (task4 = gerar o bloco except).",
    "prompt_type": "Condição: style-default (baseline) ou style-qg-default (Quality-Guided).",
    "model": "Modelo usado na coleta.",
    "model_version": "Versão exata do modelo informada pela API.",
    "temperature": "Temperatura usada na geração.",
    "llm_response": "Resposta bruta do modelo; dela sai o bloco analisado pelo Pylint.",
    "input_tokens": "Tokens enviados ao modelo (prompt + snippet).",
    "output_tokens": "Tokens gerados na resposta.",
    "thinking_tokens": "Tokens de raciocínio (só o Gemini usa; 0 nos outros).",
    "collected_at": "Data e hora da coleta de cada linha.",
    "project": "Rótulo do projeto passado ao llm.py.",
}

CODE_RE = re.compile(r"```|<code>", re.I)


class Relatorio:
    def __init__(self, nome):
        self.nome = nome
        self.erros, self.avisos, self.oks = [], [], []

    def ok(self, msg):
        self.oks.append(msg)

    def aviso(self, msg):
        self.avisos.append(msg)

    def erro(self, msg):
        self.erros.append(msg)

    @property
    def status(self):
        return "ERRO" if self.erros else ("AVISO" if self.avisos else "OK")

    def imprimir(self):
        print(f"\n--- {self.nome}  [{self.status}]")
        for m in self.oks:
            print(f"   [OK]    {m}")
        for m in self.avisos:
            print(f"   [AVISO] {m}")
        for m in self.erros:
            print(f"   [ERRO]  {m}")


def encontrar_arquivos(pasta):
    achados = {}
    duplicados = []
    for raiz, _dirs, arquivos in os.walk(pasta):
        if os.path.basename(raiz) == "analysis":
            continue
        for nome in sorted(arquivos):
            m = FILE_RE.match(nome)
            if not m:
                continue
            chave = (m.group("model"), m.group("style"))
            caminho = os.path.join(raiz, nome)
            if chave in achados:
                duplicados.append((chave, achados[chave], caminho))
            else:
                achados[chave] = caminho
    return achados, duplicados


def verificar_arquivo(caminho, modelo, estilo, base, pasta):
    rel = Relatorio(os.path.relpath(caminho, pasta))
    df = pd.read_csv(caminho)

    # 1. Linhas
    if len(df) == len(base):
        rel.ok(f"{len(df)} linhas, igual à Task 4 do dataset base")
    else:
        rel.erro(f"{len(df)} linhas; o esperado é {len(base)}")

    # 2. Colunas originais intactas e na mesma ordem
    faltando_base = [c for c in base.columns if c not in df.columns]
    if faltando_base:
        rel.erro(f"colunas do dataset base ausentes: {faltando_base}")
    elif len(df) == len(base):
        for col in ["function", "str_code_without_try_except", "str_captures_except"]:
            iguais = (df[col].fillna("").astype(str).values == base[col].fillna("").astype(str).values)
            if iguais.all():
                rel.ok(f"coluna '{col}' idêntica ao dataset base, na mesma ordem")
            else:
                rel.erro(f"coluna '{col}' difere do dataset base em {int((~iguais).sum())} linhas "
                         f"(ex.: linha {int((~iguais).argmax())})")

    # 3. Colunas do llm.py
    faltando = [c for c in COLUNAS_LLM_OBRIGATORIAS if c not in df.columns]
    if faltando:
        rel.erro(f"colunas obrigatórias ausentes: {faltando}")
    sem_meta = [c for c in COLUNAS_LLM_METADADOS if c not in df.columns]
    if sem_meta:
        rel.aviso(f"sem colunas de metadados {sem_meta} (coleta feita com o script antigo?)")

    if "task" in df.columns:
        valores = set(df["task"].dropna().astype(str))
        if valores == {"task4"}:
            rel.ok("task = task4 em todas as linhas")
        else:
            rel.erro(f"valores inesperados em 'task': {sorted(valores)}")

    if "prompt_type" in df.columns:
        valores = set(df["prompt_type"].dropna().astype(str))
        if valores == {estilo}:
            rel.ok(f"prompt_type = {estilo} em todas as linhas, igual ao nome do arquivo")
        else:
            rel.erro(f"prompt_type {sorted(valores)} não bate com o nome do arquivo ({estilo})")

    if "model" in df.columns:
        valores = set(df["model"].dropna().astype(str))
        if valores and valores != {modelo}:
            rel.erro(f"coluna 'model' {sorted(valores)} não bate com o nome do arquivo ({modelo})")

    if "temperature" in df.columns:
        temps = df["temperature"].dropna().astype(str).value_counts().to_dict()
        if len(temps) == 1:
            rel.ok(f"temperatura única: {next(iter(temps))} ({sum(temps.values())} linhas)")
        else:
            rel.aviso(f"temperaturas diferentes entre linhas: {temps}")
        n_vazias = int(df["temperature"].isna().sum())
        if n_vazias:
            rel.aviso(f"{n_vazias} linhas sem temperatura registrada")

    if "model_version" in df.columns:
        versoes = sorted(df["model_version"].dropna().astype(str).unique())
        if len(versoes) == 1:
            rel.ok(f"versão do modelo: {versoes[0]}")
        elif versoes:
            rel.aviso(f"mais de uma versão do modelo na mesma coleta: {versoes}")
        else:
            rel.aviso("model_version vazio em todas as linhas")

    if "collected_at" in df.columns:
        datas = pd.to_datetime(df["collected_at"], errors="coerce").dropna()
        if len(datas):
            rel.ok(f"coleta entre {datas.min():%d/%m/%Y %H:%M} e {datas.max():%d/%m/%Y %H:%M}")

    # 4. Respostas preenchidas e com código
    if "llm_response" in df.columns:
        resp = df["llm_response"]
        nulas = int(resp.isna().sum())
        vazias = int((resp.notna() & (resp.astype(str).str.strip() == "")).sum())
        sem_codigo = int((resp.notna() & ~resp.astype(str).str.contains(CODE_RE)).sum())
        if nulas or vazias:
            rel.erro(f"{nulas} respostas nulas e {vazias} vazias; rode o llm.py de novo para completar")
        else:
            rel.ok("todas as respostas preenchidas")
        if sem_codigo:
            rel.aviso(f"{sem_codigo} respostas sem bloco de código (``` ou <code>); "
                      "o llm_analysis.py vai contá-las como inválidas")

    # 5. Tokens
    for col in ["input_tokens", "output_tokens"]:
        if col in df.columns:
            v = pd.to_numeric(df[col], errors="coerce")
            ruins = int((v.isna() | (v <= 0)).sum())
            if ruins:
                rel.erro(f"{ruins} linhas com '{col}' vazio, não numérico ou zero")
            else:
                rel.ok(f"{col}: média {v.mean():.1f}, mín. {v.min():.0f}, máx. {v.max():.0f}")
    if "thinking_tokens" in df.columns:
        v = pd.to_numeric(df["thinking_tokens"], errors="coerce")
        if v.fillna(0).sum() > 0:
            rel.ok(f"thinking_tokens: média {v.mean():.0f}, mediana {v.median():.0f}, "
                   f"mín. {v.min():.0f}, máx. {v.max():.0f}")

    linha = {
        "arquivo": rel.nome, "modelo": modelo, "condicao": estilo, "linhas": len(df),
        "respostas_vazias": int(df["llm_response"].isna().sum()) if "llm_response" in df.columns else None,
        "temperatura": ", ".join(sorted(df["temperature"].dropna().astype(str).unique()))
        if "temperature" in df.columns else "não registrada",
        "versao": ", ".join(sorted(df["model_version"].dropna().astype(str).unique()))
        if "model_version" in df.columns else "não registrada",
        "status": rel.status,
    }
    return rel, linha


def main():
    ap = argparse.ArgumentParser(description="Verifica os CSVs gerados pelo llm.py.")
    ap.add_argument("--base", default=os.path.join("data", "balanced_sample.csv"))
    ap.add_argument("--output", default=os.path.join("llm", "output", "geracao"))
    ap.add_argument("--analysis-dir", default=os.path.join("llm", "output", "analysis"))
    ap.add_argument("--dicionario", action="store_true", help="imprime o dicionário de colunas")
    args = ap.parse_args()

    print("=" * 70)
    print("VERIFICAÇÃO DOS CSVs GERADOS (Task 4)")
    print("=" * 70)

    if not os.path.exists(args.base):
        sys.exit(f"[ERRO] Dataset base não encontrado: {args.base}")
    if not os.path.isdir(args.output):
        sys.exit(f"[ERRO] Pasta de resultados não encontrada: {args.output}")

    base_completa = pd.read_csv(args.base)
    base = base_completa[base_completa["n_try_except"] == 1].reset_index(drop=True)
    print(f"\nDataset base: {len(base_completa)} linhas; {len(base)} usadas na Task 4 (n_try_except == 1).")

    if args.dicionario:
        print("\nDICIONÁRIO DE COLUNAS")
        for col, desc in DESCRICAO_COLUNAS.items():
            print(f"  {col}: {desc}")

    arquivos, duplicados = encontrar_arquivos(args.output)
    print(f"Arquivos encontrados: {len(arquivos)}")
    for chave, a, b in duplicados:
        print(f"[ERRO] condição {chave} aparece duas vezes:\n   {a}\n   {b}")

    linhas, relatorios = [], []
    for (modelo, estilo), caminho in sorted(arquivos.items()):
        rel, linha = verificar_arquivo(caminho, modelo, estilo, base, args.output)
        rel.imprimir()
        relatorios.append(rel)
        linhas.append(linha)

    # 6. Pares completos
    print("\n" + "=" * 70)
    print("PARES BASELINE x QG")
    modelos = sorted({m for m, _ in arquivos})
    pares_ok = True
    for m in modelos:
        faltam = [c for c in CONDICOES if (m, c) not in arquivos]
        if faltam:
            pares_ok = False
            print(f"   [ERRO]  {m}: falta {faltam}")
        else:
            print(f"   [OK]    {m}: baseline e QG presentes")

    resumo = pd.DataFrame(linhas)
    print("\n" + "=" * 70)
    print("RESUMO")
    print(resumo.drop(columns=["arquivo"]).to_string(index=False))

    pasta_analise = args.analysis_dir
    os.makedirs(pasta_analise, exist_ok=True)
    destino = os.path.join(pasta_analise, "verificacao_dados.csv")
    resumo.to_csv(destino, index=False)

    n_erros = sum(len(r.erros) for r in relatorios) + len(duplicados) + (0 if pares_ok else 1)
    n_avisos = sum(len(r.avisos) for r in relatorios)
    print("\n" + "=" * 70)
    if n_erros:
        print(f"RESULTADO: {n_erros} erro(s) e {n_avisos} aviso(s). Corrija os erros antes de analisar.")
    elif n_avisos:
        print(f"RESULTADO: nenhum erro, {n_avisos} aviso(s). Os dados podem ser analisados; "
              "leia os avisos para a seção de limitações.")
    else:
        print("RESULTADO: todos os arquivos estão completos e no padrão.")
    print(f"Resumo salvo em {destino}")
    print("=" * 70)
    sys.exit(1 if n_erros else 0)


if __name__ == "__main__":
    main()
