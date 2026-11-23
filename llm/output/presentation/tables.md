## RQ1 · Violations per model and prompt (% of valid handlers)

| Model            | Prompt                |   W0718 (%) |   W0707 (%) |   W0718 or W0707 (%) |
|:-----------------|:----------------------|------------:|------------:|---------------------:|
| Claude Haiku 4.5 | Default prompt        |         6.9 |        24.9 |                 31.7 |
| Claude Haiku 4.5 | Quality-guided prompt |         0.5 |         0   |                  0.5 |
| Gemini 3 Flash   | Default prompt        |        12.2 |        22.6 |                 34.8 |
| Gemini 3 Flash   | Quality-guided prompt |         0.3 |         0   |                  0.3 |
| GPT-4o-mini      | Default prompt        |        20.1 |        39.6 |                 59.6 |
| GPT-4o-mini      | Quality-guided prompt |         0   |         0   |                  0   |
| Developers       | Reference             |         7.1 |         6.6 |                 13.7 |

## RQ1 · Paired comparison, default vs. quality-guided prompt

| Model            |   Valid pairs |   Improved |   Worsened | McNemar p (Holm)   |
|:-----------------|--------------:|-----------:|-----------:|:-------------------|
| Claude Haiku 4.5 |           378 |        118 |          0 | < 0.001            |
| Gemini 3 Flash   |           376 |        130 |          0 | < 0.001            |
| GPT-4o-mini      |           379 |        226 |          0 | < 0.001            |

## Pylint W0718 vs. actual catch of Exception (AST)

| Model            |   Flagged by W0718, default (%) |   Actual Exception catch, default (%) |   Actual Exception catch, QG (%) |
|:-----------------|--------------------------------:|--------------------------------------:|---------------------------------:|
| Claude Haiku 4.5 |                             6.9 |                                  37.8 |                              3.4 |
| Gemini 3 Flash   |                            12.2 |                                  34.6 |                              0.3 |
| GPT-4o-mini      |                            20.1 |                                  49.1 |                              0.3 |
| Developers       |                             7.1 |                                  12.1 |                            nan   |

## RQ2 · Handler patterns (% of handlers)

| Model            | Prompt                |   Bare except: W0702 (%) |   raise ... from None (%) |   Raises Exception (%) |   Only re-raises: W0706 (%) |   Contains raise (%) |   Raises RuntimeError (%) |   Swallows the error (%) |   Only logs or prints (%) |   Catches 3+ types (%) |
|:-----------------|:----------------------|-------------------------:|--------------------------:|-----------------------:|----------------------------:|---------------------:|--------------------------:|-------------------------:|--------------------------:|-----------------------:|
| Claude Haiku 4.5 | Default prompt        |                      0   |                       0   |                    0.5 |                         1.3 |                 66.8 |                       1.1 |                      3.7 |                       4.2 |                    8.7 |
| Claude Haiku 4.5 | Quality-guided prompt |                      0   |                       0   |                    0   |                         9.8 |                 88.1 |                       4.2 |                      0.5 |                       0.8 |                    9.5 |
| Gemini 3 Flash   | Default prompt        |                      0.8 |                       1.1 |                    0.8 |                         0   |                 58.3 |                       0.5 |                      7.7 |                       3.7 |                    7.1 |
| Gemini 3 Flash   | Quality-guided prompt |                      0   |                       0   |                    0.3 |                         0   |                 70.2 |                       3.5 |                      4.3 |                       2.4 |                    7.7 |
| GPT-4o-mini      | Default prompt        |                      0   |                       0   |                    5.5 |                         0   |                 65.4 |                       7.4 |                      0   |                      18.7 |                    5.5 |
| GPT-4o-mini      | Quality-guided prompt |                      0   |                       0   |                    0   |                         0   |                100   |                      26.9 |                      0   |                       0   |                    2.4 |
| Developers       | Reference             |                      2.9 |                       0.5 |                    0   |                         0   |                 26.4 |                       0   |                     35.6 |                       2.6 |                    4.5 |

## RQ2 · Direct ways around the rules (% of handlers)

| Model            | Prompt                |   Bare except: W0702 (%) |   raise ... from None (%) |   Raises Exception (%) |   Only re-raises: W0706 (%) |
|:-----------------|:----------------------|-------------------------:|--------------------------:|-----------------------:|----------------------------:|
| Claude Haiku 4.5 | Default prompt        |                      0   |                       0   |                    0.5 |                         1.3 |
| Claude Haiku 4.5 | Quality-guided prompt |                      0   |                       0   |                    0   |                         9.8 |
| Gemini 3 Flash   | Default prompt        |                      0.8 |                       1.1 |                    0.8 |                         0   |
| Gemini 3 Flash   | Quality-guided prompt |                      0   |                       0   |                    0.3 |                         0   |
| GPT-4o-mini      | Default prompt        |                      0   |                       0   |                    5.5 |                         0   |
| GPT-4o-mini      | Quality-guided prompt |                      0   |                       0   |                    0   |                         0   |
| Developers       | Reference             |                      2.9 |                       0.5 |                    0   |                         0   |

## RQ2 · What the handler does after catching the error (% of handlers)

| Model            | Prompt                |   Contains raise (%) |   Raises RuntimeError (%) |   Swallows the error (%) |   Only logs or prints (%) |
|:-----------------|:----------------------|---------------------:|--------------------------:|-------------------------:|--------------------------:|
| Claude Haiku 4.5 | Default prompt        |                 66.8 |                       1.1 |                      3.7 |                       4.2 |
| Claude Haiku 4.5 | Quality-guided prompt |                 88.1 |                       4.2 |                      0.5 |                       0.8 |
| Gemini 3 Flash   | Default prompt        |                 58.3 |                       0.5 |                      7.7 |                       3.7 |
| Gemini 3 Flash   | Quality-guided prompt |                 70.2 |                       3.5 |                      4.3 |                       2.4 |
| GPT-4o-mini      | Default prompt        |                 65.4 |                       7.4 |                      0   |                      18.7 |
| GPT-4o-mini      | Quality-guided prompt |                100   |                      26.9 |                      0   |                       0   |
| Developers       | Reference             |                 26.4 |                       0   |                     35.6 |                       2.6 |

## RQ3 · Similarity to the developer's handler

| Model            | Prompt                |   Jaccard |   CrystalBLEU |   Type in common with developer (%) |
|:-----------------|:----------------------|----------:|--------------:|------------------------------------:|
| Claude Haiku 4.5 | Default prompt        |     0.345 |         0.075 |                                41.3 |
| Claude Haiku 4.5 | Quality-guided prompt |     0.291 |         0.042 |                                37.1 |
| Gemini 3 Flash   | Default prompt        |     0.422 |         0.132 |                                42.4 |
| Gemini 3 Flash   | Quality-guided prompt |     0.373 |         0.103 |                                38.5 |
| GPT-4o-mini      | Default prompt        |     0.255 |         0.029 |                                30.1 |
| GPT-4o-mini      | Quality-guided prompt |     0.236 |         0.01  |                                23.6 |

## RQ3 · Significance of the change (Wilcoxon, Holm)

| Model            | Jaccard p (Holm)   | CrystalBLEU p (Holm)   |   Type in common p (Holm) |
|:-----------------|:-------------------|:-----------------------|--------------------------:|
| Claude Haiku 4.5 | < 0.001            | < 0.001                |                     0.049 |
| Gemini 3 Flash   | < 0.001            | 0.003                  |                     0.358 |
| GPT-4o-mini      | 1.000              | 0.014                  |                     0.014 |

## Exception type chosen by QG (outside the Azure SDK cluster)

| Model            |   QG replaced Exception with specific types |   Same types as the developer |
|:-----------------|--------------------------------------------:|------------------------------:|
| Claude Haiku 4.5 |                                          64 |                             6 |
| Gemini 3 Flash   |                                          96 |                            17 |
| GPT-4o-mini      |                                         129 |                             9 |

## Results without the near-duplicate Azure SDK cluster

| Model            |   Valid pairs |   W0718 or W0707, default (%) |   W0718 or W0707, QG (%) |   W0706, default (%) |   W0706, QG (%) |   Jaccard, default |   Jaccard, QG |
|:-----------------|--------------:|------------------------------:|-------------------------:|---------------------:|----------------:|-------------------:|--------------:|
| Claude Haiku 4.5 |           267 |                          41.2 |                      0.7 |                    0 |             0.4 |              0.393 |         0.318 |
| Gemini 3 Flash   |           265 |                          47.5 |                      0.4 |                    0 |             0   |              0.492 |         0.447 |
| GPT-4o-mini      |           268 |                          70.5 |                      0   |                    0 |             0   |              0.283 |         0.247 |

## Cost: mean tokens per function

| Model            |   Input, default |   Input, QG | Added input   |   Output, default |   Output, QG |
|:-----------------|-----------------:|------------:|:--------------|------------------:|-------------:|
| Claude Haiku 4.5 |            472.8 |       567.8 | +95 (+20%)    |              46.3 |         41.9 |
| Gemini 3 Flash   |            479.9 |       569.9 | +90 (+19%)    |              31   |         47.6 |
| GPT-4o-mini      |            374.9 |       457.9 | +83 (+22%)    |              33.2 |         31.9 |

## Manual evaluation pilot: agreement between raters (before calibration)

| Question                   |   Agreement (%) |   Krippendorff's α |
|:---------------------------|----------------:|-------------------:|
| Exception type (1a)        |            66.7 |              0.35  |
| Reaction to the error (1b) |            80   |              0.385 |
| Adequacy (1a and 1b)       |            63.3 |              0.352 |
| Similarity, 1–5 (3)        |            70   |              0.932 |

