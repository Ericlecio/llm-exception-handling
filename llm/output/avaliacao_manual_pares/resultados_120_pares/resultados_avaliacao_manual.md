## Concordância antes do consenso

| Question                   |   Agreement (%) |   Krippendorff alpha |
|:---------------------------|----------------:|---------------------:|
| Exception type (1a)        |            80   |                0.499 |
| Reaction to the error (1b) |            90.8 |                0.817 |
| Adequacy (1a and 1b)       |            75.4 |                0.619 |
| Similarity, 1-5 (3)        |            77.1 |                0.913 |

## Resumo por modelo e prompt

| Model            | Prompt   |   Handlers |   Type can occur (%) |   Type undeterminable (%) |   Appropriate reaction (%) |   Adequate (%) |   Mean similarity |
|:-----------------|:---------|-----------:|---------------------:|--------------------------:|---------------------------:|---------------:|------------------:|
| Claude Haiku 4.5 | Default  |         40 |                100   |                       0   |                       50   |           50   |              2.86 |
| Claude Haiku 4.5 | QG       |         40 |                 72.5 |                      22.5 |                       32.5 |           29   |              2.11 |
| Gemini 3 Flash   | Default  |         40 |                 85   |                      10   |                       57.5 |           61.1 |              3    |
| Gemini 3 Flash   | QG       |         40 |                 75   |                      20   |                       50   |           53.1 |              2.68 |
| GPT-4o-mini      | Default  |         40 |                 95   |                       2.5 |                       42.5 |           41   |              2.52 |
| GPT-4o-mini      | QG       |         40 |                 77.5 |                      10   |                       27.5 |           22.2 |              1.84 |
| All models       | Default  |        120 |                 93.3 |                       4.2 |                       50   |           50.4 |              2.8  |
| All models       | QG       |        120 |                 75   |                      17.5 |                       36.7 |           34.3 |              2.21 |

## Comparação pareada (padrão x QG)

| Model            |   Pairs |   Pairs with determinable type |   Adequate, default (%) |   Adequate, QG (%) |   Only default adequate |   Only QG adequate |   McNemar p (adequacy) |   Reaction: only default appropriate |   Reaction: only QG appropriate |   McNemar p (reaction) |   Similarity, default |   Similarity, QG |   Wilcoxon p (similarity) |
|:-----------------|--------:|-------------------------------:|------------------------:|-------------------:|------------------------:|-------------------:|-----------------------:|-------------------------------------:|--------------------------------:|-----------------------:|----------------------:|-----------------:|--------------------------:|
| Claude Haiku 4.5 |      40 |                             31 |                    45.2 |               29   |                       6 |                  1 |              0.125     |                                    8 |                               1 |             0.0390625  |                  2.86 |             2.11 |               7.99785e-05 |
| Gemini 3 Flash   |      40 |                             31 |                    58.1 |               54.8 |                       3 |                  2 |              1         |                                    5 |                               2 |             0.453125   |                  3    |             2.68 |               0.00877463  |
| GPT-4o-mini      |      40 |                             36 |                    41.7 |               22.2 |                       9 |                  2 |              0.0654297 |                                    9 |                               3 |             0.145996   |                  2.52 |             1.84 |               0.000140341 |
| All models       |     120 |                             98 |                    48   |               34.7 |                      18 |                  5 |              0.010622  |                                   22 |                               6 |             0.00371917 |                  2.8  |             2.21 |               1.08376e-09 |

