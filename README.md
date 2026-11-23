# Quality-Guided Prompting para tratamento de exceções em Python

Mini-estudo que avalia se escrever regras de análise estática diretamente no prompt reduz os antipadrões de tratamento de exceções gerados por LLMs, e quais efeitos colaterais isso produz.

**Quality-Guided Prompting (QG):** o prompt padrão de geração do bloco `except`, acrescido de duas regras do Pylint:

- **W0718 (broad-exception-caught):** não capturar `Exception` ou `BaseException`;
- **W0707 (raise-missing-from):** ao lançar uma nova exceção dentro do `except`, encadear com `from`.

## Perguntas de pesquisa

- **RQ1:** em que medida o QG reduz a taxa de violações W0718 e W0707 em relação ao prompt padrão?
- **RQ2:** que efeitos colaterais o QG introduz nos handlers gerados, e com que frequência?
- **RQ3:** quanto o QG altera a semelhança dos handlers com os escritos pelos desenvolvedores, incluindo a escolha do tipo de exceção?

## Principais resultados

|                                                       | Prompt padrão | QG                         |
| ----------------------------------------------------- | ------------- | -------------------------- |
| Handlers com W0718 ou W0707                           | 31,7–59,6%    | 0,0–0,5%                   |
| Handlers que relançam o erro (desenvolvedores: 26,4%) | 58,3–66,8%    | 70,2–100%                  |
| Handlers adequados na avaliação manual (120 pares)    | 48,0%         | 34,7% (McNemar, p = 0,011) |

O QG elimina as violações-alvo nos três modelos, mas os modelos cumprem as regras mudando o comportamento do handler, e a adequação cai.

## Dados

- **Benchmark:** `data/balanced_sample.csv`, de Souza et al. (SBES 2026), usado sem modificação. A Task 4 usa as 379 funções com `n_try_except == 1`: o modelo recebe a função sem o `try/except` (`str_code_without_try_except`) e gera o bloco `except`; o bloco do desenvolvedor (`str_captures_except`) é a referência.
- **Modelos:** Claude Haiku 4.5, Gemini 3 Flash e GPT-4o-mini, com temperatura 0,7.
- **Total:** 3 modelos × 2 prompts × 379 funções = 2.274 handlers.

## Estrutura do repositório

```
data/
  balanced_sample.csv            benchmark (entrada e referência)
llm/
  collection/
    generate_handlers.py           1. coleta das respostas dos modelos
    verify_collection.py           2. verificação de integridade dos arquivos coletados
  analysis/
    analyze_handlers.py            3. análise automática: Pylint, AST, similaridade e testes pareados
    similarity_metrics.py          3b. CodeBLEU, concordância de ação e medianas (RQ3)
    robustness_analyses.py         3c. análises de robustez
  reporting/
    summary_tables.py              4. figuras e tabelas dos slides
    paper_artifacts.py             5. tabelas (LaTeX) e gráficos (PDF) do artigo
  manual_evaluation/
    sample_manual_evaluation.py    6. sorteio da amostra e planilhas cegas da avaliação manual
    rater_agreement.py             7. concordância entre avaliadores (alfa de Krippendorff)
    manual_evaluation_results.py   8. consenso e resultados da avaliação manual
  output/
    generation/                    respostas dos modelos, uma pasta por modelo e prompt
    analysis/                      resultados da análise automática
    manual_evaluation/pilot/       piloto de calibração (30 itens)
    manual_evaluation/main/        sorteio, chave, respostas, consenso e resultados (120 pares)
    presentation/                  figuras e tabelas dos slides
    paper/                         tabelas e figuras do artigo
```

## Como reproduzir

Todos os comandos rodam a partir da raiz do repositório.

### 1. Ambiente

```bash
pip install -r requirements.txt
```

Para coletar novas respostas, copie `.env.example` para `.env` e preencha as chaves de API. As etapas 2 a 8 não precisam de chaves.

### 2. Coleta (opcional; os resultados já estão em `llm/output/generation/`)

```bash
python llm/collection/generate_handlers.py --task task4 --prompt-types style-default    --models claude-haiku-4-5
python llm/collection/generate_handlers.py --task task4 --prompt-types style-qg-default --models claude-haiku-4-5
```

Troque o modelo por `gemini-3-flash-preview` ou `gpt-4o-mini`. A coleta retoma de onde parou se for interrompida.

### 3. Verificação e análise automática

```bash
python llm/collection/verify_collection.py
python llm/analysis/analyze_handlers.py
python llm/analysis/similarity_metrics.py
```

### 4. Figuras e tabelas

```bash
python llm/reporting/summary_tables.py
python llm/reporting/paper_artifacts.py
```

### 5. Avaliação manual

A amostra (120 pares, 95% de confiança, margem de ±8,5%, fórmula de Cochran) foi sorteada com semente fixa. Para conferir que o sorteio registrado é reproduzível:

```bash
python llm/manual_evaluation/sample_manual_evaluation.py --verificar
```

Concordância antes do consenso e resultados finais:

```bash
python llm/manual_evaluation/rater_agreement.py
python llm/manual_evaluation/manual_evaluation_results.py
```

## Observações

- Os metadados da coleta do Gemini com QG (versão, temperatura e período) foram registrados depois da coleta, que foi feita antes de o script passar a gravá-los. Os tokens de raciocínio dessa condição não foram registrados.
- Respostas sem código ou com sintaxe inválida são contadas como inválidas, sem correção automática (no máximo 3 de 379 por condição).
- Os avaliadores da avaliação manual são os autores do estudo; o cegamento quanto ao modelo e ao prompt foi garantido por códigos aleatórios, com a chave em arquivo separado.

## Referência do benchmark

Souza, J., Alves, T., Lima, R., Araújo, E., Teixeira, L., Fonseca, B. _An Empirical Evaluation of Using Large Language Models to Recommend Exception Handling Tasks_. Brazilian Symposium on Software Engineering (SBES), 2026.
