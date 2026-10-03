# LLM Exception Handling: Quality-Guided Prompting

Mini-estudo sobre a geração de blocos de tratamento de exceções em Python por Grandes Modelos de Linguagem (LLMs). O projeto investiga se a técnica de **Quality-Guided Prompting** reduz os _anti-patterns_ que as IAs costumam introduzir em blocos `try/except`.

## Contexto

Estudos recentes mostram que os LLMs ajudam bastante na escrita de código, mas vão mal no tratamento de exceções. O código gerado por IA apresenta **104,2% mais violações de qualidade** do que o código escrito por desenvolvedores humanos.

As violações mais comuns são:

- **Pylint W0718 (Broad Exception Catching):** captura genérica de exceções (ex.: `except Exception:`), que pode esconder bugs inesperados.
- **Pylint W0707 (Missing Exception Chaining):** levantar uma nova exceção dentro do `except` sem encadear o erro original com `from`.

## Abordagem

Em vez de usar prompts zero-shot tradicionais, as regras de qualidade estática do Pylint são incluídas diretamente nas instruções do LLM (Quality-Guided Prompting).

O objetivo é comparar, com testes A/B, se a IA consegue gerar código limpo e sem _anti-patterns_ já na primeira tentativa, diminuindo a necessidade de revisão humana.

## Estrutura do repositório

- `data/balanced_sample.csv`: dataset com 379 trechos de código Python reais que precisam de tratamento de exceções (Ground Truth).
- `llm.py`: script de coleta de dados. Conecta-se às APIs da OpenAI (GPT), Anthropic (Claude) e Google (Gemini), com rodízio automático de chaves para contornar limites de taxa (erro 429) e bloqueios.
- `llm_analysis.py`: avaliador automatizado. Extrai os códigos gerados, calcula métricas de similaridade léxica (BLEU, CrystalBLEU e Jaccard) e roda o Pylint para contar os _anti-patterns_ (W0707 e W0718).
- `output/`: pasta onde ficam os CSVs com os resultados brutos e as métricas processadas.

## Como reproduzir

### 1. Configurar o ambiente

Instale as dependências:

```bash
pip install pandas openai anthropic google-genai pylint scikit-learn nltk crystalbleu python-dotenv
```

Crie um arquivo `.env` na raiz do projeto com suas chaves de API:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_KEY_1=AIza...
GEMINI_KEY_2=AIza...
```

### 2. Coletar os dados (teste A/B)

Rode o `llm.py` para executar a Tarefa 4 (geração do bloco `except`), comparando o prompt padrão (baseline) com o prompt focado em qualidade:

```bash
# Baseline (prompt padrão) - GEMINI
python llm.py --task task4 --prompt-types style-default --models gemini-3-flash-preview

# Intervenção (Quality-Guided Prompt)
python llm.py --task task4 --prompt-types style-qg-default --models gemini-3-flash-preview


# 1. Testar o Baseline - CODEX
python llm/llm.py --task task4 --prompt-types style-default --models gpt-4o-mini -v

# 2. Testar o Quality-Guided
python llm/llm.py --task task4 --prompt-types style-qg-default --models gpt-4o-mini -v


# 1. Testar o Baseline- CLAUDE
python llm/llm.py --task task4 --prompt-types style-default --models claude-haiku-4-5 -v

# 2. Testar o Quality-Guided
python llm/llm.py --task task4 --prompt-types style-qg-default --models claude-haiku-4-5 -v

```

Para testar outras IAs, troque o modelo por `gpt-4o-mini` ou `claude-haiku-4-5`.

### 3. Analisar os resultados

Depois da coleta, rode o avaliador para calcular as métricas e contar as violações do Pylint:

```bash
python llm_analysis.py
```

Os resultados processados ficam na pasta `output/`.
