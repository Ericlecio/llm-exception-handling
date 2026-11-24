## 1. Manual evaluation: primary outcome, sensitivity and strict adequacy

| scope         | measure                                 |   pairs |   default_% | default_CI95   |   QG_% | QG_CI95      |   diff_pp | diff_CI95_cluster_bootstrap   |   only_default |   only_QG | McNemar_p   |   odds_ratio_b/c | OR_CI95       |
|:--------------|:----------------------------------------|--------:|------------:|:---------------|-------:|:-------------|----------:|:------------------------------|---------------:|----------:|:------------|-----------------:|:--------------|
| All pairs     | Reaction appropriate (primary)          |     120 |        50   | [41.2; 58.8]   |   36.7 | [28.6; 45.6] |     -13.3 | [-22.2; -5.0]                 |             22 |         6 | 0.004       |             3.67 | [1.44; 11.05] |
| All pairs     | Adequate, original (determinable pairs) |      98 |        48   | [38.3; 57.7]   |   34.7 | [26.0; 44.5] |     -13.3 | [-22.6; -4.0]                 |             18 |         5 | 0.011       |             3.6  | [1.29; 12.40] |
| All pairs     | Adequate, undeterminable = inadequate   |     120 |        48.3 | [39.6; 57.2]   |   28.3 | [21.0; 37.0] |     -20   | [-29.1; -11.0]                |             29 |         5 | < 0.001     |             5.8  | [2.22; 19.19] |
| All pairs     | Adequate, undeterminable = adequate     |     120 |        50   | [41.2; 58.8]   |   36.7 | [28.6; 45.6] |     -13.3 | [-21.5; -5.1]                 |             22 |         6 | 0.004       |             3.67 | [1.44; 11.05] |
| All pairs     | Adequate, strict (no broad catch)       |     120 |        32.5 | [24.8; 41.3]   |   28.3 | [21.0; 37.0] |      -4.2 | [-12.2; 4.1]                  |             15 |        10 | 0.424       |             1.5  | [0.63; 3.73]  |
| Without Azure | Reaction appropriate (primary)          |      84 |        70.2 | [59.8; 79.0]   |   52.4 | [41.8; 62.7] |     -17.9 | [-29.4; -6.1]                 |             21 |         6 | 0.006       |             3.5  | [1.37; 10.60] |
| Without Azure | Adequate, original (determinable pairs) |      69 |        68.1 | [56.4; 77.9]   |   49.3 | [37.8; 60.8] |     -18.8 | [-31.9; -5.8]                 |             18 |         5 | 0.011       |             3.6  | [1.29; 12.40] |
| Without Azure | Adequate, undeterminable = inadequate   |      84 |        69   | [58.5; 77.9]   |   40.5 | [30.6; 51.2] |     -28.6 | [-40.7; -16.7]                |             29 |         5 | < 0.001     |             5.8  | [2.22; 19.19] |
| Without Azure | Adequate, undeterminable = adequate     |      84 |        70.2 | [59.8; 79.0]   |   52.4 | [41.8; 62.7] |     -17.9 | [-29.8; -6.0]                 |             21 |         6 | 0.006       |             3.5  | [1.37; 10.60] |
| Without Azure | Adequate, strict (no broad catch)       |      84 |        46.4 | [36.2; 57.0]   |   40.5 | [30.6; 51.2] |      -6   | [-17.2; 5.7]                  |             15 |        10 | 0.424       |             1.5  | [0.63; 3.73]  |

## 1b. Similarity rating (1-5)

| measure                 |   default_mean |   QG_mean |   default_median |   QG_median | Wilcoxon_p   |
|:------------------------|---------------:|----------:|-----------------:|------------:|:-------------|
| Similarity rating (1-5) |            2.8 |      2.21 |              2.5 |           2 | < 0.001      |

## 1c. Undeterminable exception type (% of handlers)

| condicao         |   pct |
|:-----------------|------:|
| style-default    |   4.2 |
| style-qg-default |  17.5 |

## 2. RQ1: target violations with CI and paired difference

| model   |   pairs |   default_% | default_CI95   |   QG_% | QG_CI95    |   diff_pp | diff_CI95      |   worsened |   improved | McNemar_p   |
|:--------|--------:|------------:|:---------------|-------:|:-----------|----------:|:---------------|-----------:|-----------:|:------------|
| Claude  |     378 |        31.7 | [27.3; 36.6]   |    0.5 | [0.1; 1.9] |     -31.2 | [-35.7; -26.7] |          0 |        118 | < 0.001     |
| Gemini  |     376 |        34.8 | [30.2; 39.8]   |    0.3 | [0.0; 1.5] |     -34.6 | [-39.4; -29.8] |          0 |        130 | < 0.001     |
| GPT     |     379 |        59.6 | [54.6; 64.4]   |    0   | [0.0; 1.0] |     -59.6 | [-64.6; -54.6] |          0 |        226 | < 0.001     |

## 2b. RQ1: actual broad catches (AST) vs. W0718, default prompt

| model   |   W0718_default_% |   AST_broad_default_% |   ratio_AST/W0718 |
|:--------|------------------:|----------------------:|------------------:|
| Claude  |               6.9 |                  37.8 |               5.5 |
| Gemini  |              12.2 |                  34.6 |               2.8 |
| GPT     |              20.1 |                  49.1 |               2.4 |

## 2c. RQ1: raising Exception/BaseException (W0719 behavior)

| model   |   raises_Exception_default_% |   raises_Exception_QG_% |
|:--------|-----------------------------:|------------------------:|
| Claude  |                          0.5 |                     0   |
| Gemini  |                          0.8 |                     0.3 |
| GPT     |                          5.5 |                     0   |

## 3. RQ2: action distribution (% of valid handlers)

| model      | prompt    |   n |   raise |   return |   log |   ignore |   other |
|:-----------|:----------|----:|--------:|---------:|------:|---------:|--------:|
| Claude     | Default   | 379 |    66.8 |     16.6 |   4.2 |      3.7 |     8.7 |
| Claude     | QG        | 378 |    88.4 |      7.4 |   0.8 |      0.5 |     2.9 |
| Gemini     | Default   | 379 |    58.3 |     15   |   3.7 |      7.7 |    15.3 |
| Gemini     | QG        | 376 |    70.7 |     13.3 |   2.4 |      4.3 |     9.3 |
| GPT        | Default   | 379 |    65.4 |      7.9 |  18.7 |      0   |     7.9 |
| GPT        | QG        | 379 |   100   |      0   |   0   |      0   |     0   |
| Developers | Reference | 379 |    26.4 |     16.4 |   2.6 |     35.6 |    19   |

## 3b. RQ2: forms of raise (% of valid handlers; a handler may have more than one)

| model      | prompt    |   n |   any_raise |   reraise_caught |   new_with_from |   new_without_from |
|:-----------|:----------|----:|------------:|-----------------:|----------------:|-------------------:|
| Claude     | Default   | 379 |        66.8 |             31.1 |            31.4 |               25.3 |
| Claude     | QG        | 378 |        88.4 |             18.8 |            78   |                0   |
| Gemini     | Default   | 379 |        58.3 |             23.7 |            12.1 |               22.4 |
| Gemini     | QG        | 376 |        70.7 |              4   |            66.8 |                0   |
| GPT        | Default   | 379 |        65.4 |             10.6 |            17.9 |               40.6 |
| GPT        | QG        | 379 |       100   |              0   |           100   |                0   |
| Developers | Reference | 379 |        26.4 |              6.3 |            14.2 |                6.6 |

## 4. RQ3: action agreement and CodeBLEU, with and without Azure

| scope         | model   |   pairs |   same_action_default_% |   same_action_QG_% | same_action_diff_CI95   | same_action_McNemar_p   |   CodeBLEU_default |   CodeBLEU_QG | CodeBLEU_Wilcoxon_p   |   CodeBLEU_effect_r |
|:--------------|:--------|--------:|------------------------:|-------------------:|:------------------------|:------------------------|-------------------:|--------------:|:----------------------|--------------------:|
| All functions | Claude  |     378 |                    46.8 |               37   | [-13.5; -6.3]           | < 0.001                 |              0.315 |         0.274 | < 0.001               |                0.23 |
| All functions | Gemini  |     376 |                    55.6 |               48.4 | [-10.4; -4.0]           | < 0.001                 |              0.379 |         0.334 | < 0.001               |                0.3  |
| All functions | GPT     |     379 |                    34.8 |               26.4 | [-12.1; -4.7]           | < 0.001                 |              0.258 |         0.231 | < 0.001               |                0.23 |
| Without Azure | Claude  |     267 |                    66.3 |               52.4 | [-18.7; -9.0]           | < 0.001                 |              0.365 |         0.284 | < 0.001               |                0.57 |
| Without Azure | Gemini  |     265 |                    78.9 |               68.7 | [-14.7; -6.0]           | < 0.001                 |              0.432 |         0.39  | 0.034                 |                0.13 |
| Without Azure | GPT     |     268 |                    49.3 |               37.3 | [-16.8; -7.1]           | < 0.001                 |              0.282 |         0.241 | < 0.001               |                0.34 |

