# Task 4: Baseline vs Quality-Guided

Percentuais calculados sobre os blocos válidos. `broad_hidden` = captura de Exception/BaseException que o Pylint não marca porque o handler relança.

## RQ1/RQ2: violações

| model                  | prompt_type      |   n |   invalidos |   W0718_% |   W0707_% |   any_target_% |   W0702_% |   W0706_% |   broad_hidden_% |   violacoes_por_amostra |
|:-----------------------|:-----------------|----:|------------:|----------:|----------:|---------------:|----------:|----------:|-----------------:|------------------------:|
| claude-haiku-4-5       | style-default    | 379 |           0 |       6.9 |      24.8 |           31.7 |       0   |       1.3 |             30.9 |                   0.33  |
| claude-haiku-4-5       | style-qg-default | 379 |           1 |       0.5 |       0   |            0.5 |       0   |       9.8 |              2.9 |                   0.103 |
| gemini-3-flash-preview | style-default    | 379 |           0 |      12.4 |      22.4 |           34.8 |       0.8 |       0   |             22.2 |                   0.356 |
| gemini-3-flash-preview | style-qg-default | 379 |           3 |       0.3 |       0   |            0.3 |       0   |       0   |              0   |                   0.003 |
| gpt-4o-mini            | style-default    | 379 |           0 |      20.1 |      39.6 |           59.6 |       0   |       0   |             29   |                   0.596 |
| gpt-4o-mini            | style-qg-default | 379 |           0 |       0   |       0   |            0   |       0   |       0   |              0.3 |                   0     |
| HUMANO (referência)    | -                | 379 |           0 |       7.1 |       6.6 |           13.7 |       2.9 |       0   |              5   |                   0.166 |

## RQ3: similaridade com o código humano

| model                  | prompt_type      |   bleu |   crystalbleu |   jaccard |   exact_match |   type_overlap |   type_exact |   n_types |
|:-----------------------|:-----------------|-------:|--------------:|----------:|--------------:|---------------:|-------------:|----------:|
| claude-haiku-4-5       | style-default    |  0.145 |         0.075 |     0.345 |         0.04  |          0.413 |        0.267 |     1.573 |
| claude-haiku-4-5       | style-qg-default |  0.092 |         0.042 |     0.291 |         0.026 |          0.371 |        0.247 |     1.463 |
| gemini-3-flash-preview | style-default    |  0.218 |         0.132 |     0.422 |         0.098 |          0.424 |        0.34  |     1.208 |
| gemini-3-flash-preview | style-qg-default |  0.18  |         0.103 |     0.373 |         0.082 |          0.385 |        0.289 |     1.253 |
| gpt-4o-mini            | style-default    |  0.067 |         0.029 |     0.255 |         0.013 |          0.301 |        0.16  |     1.464 |
| gpt-4o-mini            | style-qg-default |  0.035 |         0.01  |     0.236 |         0     |          0.236 |        0.129 |     1.33  |

## Status das respostas

| model                  | prompt_type      |   sem_codigo |   sintaxe_invalida |   valido |
|:-----------------------|:-----------------|-------------:|-------------------:|---------:|
| claude-haiku-4-5       | style-default    |            0 |                  0 |      379 |
| claude-haiku-4-5       | style-qg-default |            0 |                  1 |      378 |
| gemini-3-flash-preview | style-default    |            0 |                  0 |      379 |
| gemini-3-flash-preview | style-qg-default |            2 |                  1 |      376 |
| gpt-4o-mini            | style-default    |            0 |                  0 |      379 |
| gpt-4o-mini            | style-qg-default |            0 |                  0 |      379 |

## Custo médio (tokens)

| model                  | prompt_type      |   input_tokens |   output_tokens |   thinking_tokens |
|:-----------------------|:-----------------|---------------:|----------------:|------------------:|
| claude-haiku-4-5       | style-default    |          472.8 |            46.3 |                 0 |
| claude-haiku-4-5       | style-qg-default |          567.8 |            41.9 |                 0 |
| gemini-3-flash-preview | style-default    |          479.9 |            31   |             13817 |
| gemini-3-flash-preview | style-qg-default |          569.9 |            47.6 |               nan |
| gpt-4o-mini            | style-default    |          374.9 |            33.2 |                 0 |
| gpt-4o-mini            | style-qg-default |          457.9 |            31.9 |                 0 |

## Testes pareados (baseline x QG, Holm por modelo)

| model                  | rq   | metrica      |   n_pares |   baseline |    qg |   so_baseline(b) |   so_qg(c) | teste         |           p |      p_holm | signif_0.05   |
|:-----------------------|:-----|:-------------|----------:|-----------:|------:|-----------------:|-----------:|:--------------|------------:|------------:|:--------------|
| claude-haiku-4-5       | RQ2  | invalidas    |       379 |      0     | 0.264 |                0 |          1 | McNemar exato | 1           | 1           | não           |
| claude-haiku-4-5       | RQ1  | W0718        |       378 |      6.878 | 0.529 |               24 |          0 | McNemar exato | 1.19209e-07 | 5.96046e-07 | sim           |
| claude-haiku-4-5       | RQ1  | W0707        |       378 |     24.868 | 0     |               94 |          0 | McNemar exato | 1.00974e-28 | 8.12065e-28 | sim           |
| claude-haiku-4-5       | RQ1  | any_target   |       378 |     31.746 | 0.529 |              118 |          0 | McNemar exato | 6.01853e-36 | 6.01853e-35 | sim           |
| claude-haiku-4-5       | RQ2  | W0702        |       378 |      0     | 0     |                0 |          0 | McNemar exato | 1           | 1           | não           |
| claude-haiku-4-5       | RQ2  | W0706        |       378 |      1.323 | 9.788 |                3 |         35 | McNemar exato | 6.67787e-08 | 4.00672e-07 | sim           |
| claude-haiku-4-5       | RQ2  | broad_hidden |       378 |     30.952 | 2.91  |              109 |          3 | McNemar exato | 9.02294e-29 | 8.12065e-28 | sim           |
| claude-haiku-4-5       | RQ2  | ast_broad    |       378 |     37.831 | 3.439 |              132 |          2 | McNemar exato | 8.30744e-37 | 9.13818e-36 | sim           |
| claude-haiku-4-5       | RQ3  | jaccard      |       379 |      0.345 | 0.291 |              nan |        nan | Wilcoxon      | 1.18915e-12 | 8.32407e-12 | sim           |
| claude-haiku-4-5       | RQ3  | crystalbleu  |       379 |      0.075 | 0.042 |              nan |        nan | Wilcoxon      | 1.05583e-06 | 4.22331e-06 | sim           |
| claude-haiku-4-5       | RQ3  | type_overlap |       356 |      0.413 | 0.371 |              nan |        nan | Wilcoxon      | 0.0163092   | 0.0489275   | sim           |
| gemini-3-flash-preview | RQ2  | invalidas    |       379 |      0     | 0.792 |                0 |          3 | McNemar exato | 0.25        | 0.75        | não           |
| gemini-3-flash-preview | RQ1  | W0718        |       376 |     12.234 | 0.266 |               45 |          0 | McNemar exato | 5.68434e-14 | 3.97904e-13 | sim           |
| gemini-3-flash-preview | RQ1  | W0707        |       376 |     22.606 | 0     |               85 |          0 | McNemar exato | 5.16988e-26 | 4.65289e-25 | sim           |
| gemini-3-flash-preview | RQ1  | any_target   |       376 |     34.84  | 0.266 |              130 |          0 | McNemar exato | 1.46937e-39 | 1.6163e-38  | sim           |
| gemini-3-flash-preview | RQ2  | W0702        |       376 |      0.532 | 0     |                2 |          0 | McNemar exato | 0.5         | 1           | não           |
| gemini-3-flash-preview | RQ2  | W0706        |       376 |      0     | 0     |                0 |          0 | McNemar exato | 1           | 1           | não           |
| gemini-3-flash-preview | RQ2  | broad_hidden |       376 |     22.34  | 0     |               84 |          0 | McNemar exato | 1.03398e-25 | 8.27181e-25 | sim           |
| gemini-3-flash-preview | RQ2  | ast_broad    |       376 |     34.574 | 0.266 |              129 |          0 | McNemar exato | 2.93874e-39 | 2.93874e-38 | sim           |
| gemini-3-flash-preview | RQ3  | jaccard      |       379 |      0.422 | 0.373 |              nan |        nan | Wilcoxon      | 2.17513e-09 | 1.30508e-08 | sim           |
| gemini-3-flash-preview | RQ3  | crystalbleu  |       379 |      0.132 | 0.103 |              nan |        nan | Wilcoxon      | 0.000646    | 0.00323     | sim           |
| gemini-3-flash-preview | RQ3  | type_overlap |       356 |      0.424 | 0.385 |              nan |        nan | Wilcoxon      | 0.0895551   | 0.35822     | não           |
| gpt-4o-mini            | RQ2  | invalidas    |       379 |      0     | 0     |                0 |          0 | McNemar exato | 1           | 1           | não           |
| gpt-4o-mini            | RQ1  | W0718        |       379 |     20.053 | 0     |               76 |          0 | McNemar exato | 2.64698e-23 | 1.85288e-22 | sim           |
| gpt-4o-mini            | RQ1  | W0707        |       379 |     39.578 | 0     |              150 |          0 | McNemar exato | 1.4013e-45  | 1.26117e-44 | sim           |
| gpt-4o-mini            | RQ1  | any_target   |       379 |     59.631 | 0     |              226 |          0 | McNemar exato | 1.8546e-68  | 2.04006e-67 | sim           |
| gpt-4o-mini            | RQ2  | W0702        |       379 |      0     | 0     |                0 |          0 | McNemar exato | 1           | 1           | não           |
| gpt-4o-mini            | RQ2  | W0706        |       379 |      0     | 0     |                0 |          0 | McNemar exato | 1           | 1           | não           |
| gpt-4o-mini            | RQ2  | broad_hidden |       379 |     29.024 | 0.264 |              110 |          1 | McNemar exato | 8.62817e-32 | 6.90253e-31 | sim           |
| gpt-4o-mini            | RQ2  | ast_broad    |       379 |     49.077 | 0.264 |              186 |          1 | McNemar exato | 1.91681e-54 | 1.91681e-53 | sim           |
| gpt-4o-mini            | RQ3  | jaccard      |       379 |      0.255 | 0.236 |              nan |        nan | Wilcoxon      | 0.43989     | 1           | não           |
| gpt-4o-mini            | RQ3  | crystalbleu  |       379 |      0.029 | 0.01  |              nan |        nan | Wilcoxon      | 0.00231886  | 0.0138948   | sim           |
| gpt-4o-mini            | RQ3  | type_overlap |       356 |      0.301 | 0.236 |              nan |        nan | Wilcoxon      | 0.00231581  | 0.0138948   | sim           |
