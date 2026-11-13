# R2 lean results

# Integrity checks (runs_r2)
- OK   f2_25-29: hash ['f7559e2a90b8e70d']
- OK   f2_27-28: hash ['4c8398dcaffdf182']
- OK   main: hash ['264c75fa6507f972']
- OK   severe: hash ['9fd4811ea3ce83fc']
- OK   storage_rich: hash ['ca9be975bca0d373']
- OK   switching_actions non-negative integers
- OK   switching_reversals non-negative integers
- OK   fallback_epochs non-negative integers
- OK   overload_events non-negative integers
- OK   soc_violations non-negative integers
- OK   success binary

## Summary
| scenario     | configuration            |   n |   cum_ens_kwh_mean |   cum_ens_kwh_sd |   cum_ens_kwh_median |   switching_actions_mean |   switching_reversals_mean |   mean_epoch_runtime_s_mean |   success_n |
|:-------------|:-------------------------|----:|-------------------:|-----------------:|---------------------:|-------------------------:|---------------------------:|----------------------------:|------------:|
| f2_25-29     | RH-Lean                  |  30 |             35.78  |           81.855 |                 0    |                   10.733 |                      2.433 |                       0.222 |          30 |
| f2_25-29     | RH-Lean Tp=1             |  30 |              1.92  |           10.516 |                 0    |                    6.533 |                      0.367 |                       0.069 |          30 |
| f2_25-29     | Snapshot-Lean            |  30 |            884.72  |          315.467 |               799.5  |                    3.233 |                      0.067 |                       0.077 |          30 |
| f2_27-28     | RH-Lean                  |  30 |             46.79  |           86.553 |                 0    |                   13.6   |                      3.533 |                       0.227 |          30 |
| f2_27-28     | RH-Lean Tp=1             |  30 |            155.035 |          203.21  |                28.5  |                   10.533 |                      2.033 |                       0.071 |          30 |
| f2_27-28     | Snapshot-Lean            |  30 |            976.37  |          633.626 |               799.5  |                    6.067 |                      0.067 |                       0.081 |          30 |
| main         | RH-Lean                  |  30 |           2247.89  |          184.434 |              2220    |                   21.467 |                     10.5   |                       0.231 |          30 |
| main         | RH-Lean AR1 noise10      |  30 |           2199.69  |          154.583 |              2161.8  |                   21.6   |                     10.3   |                       0.229 |          30 |
| main         | RH-Lean AR1 noise25      |  30 |           2263.89  |          392.72  |              2190.15 |                   23.667 |                     12.267 |                       0.226 |          30 |
| main         | RH-Lean Bias+10%         |  30 |           2391.09  |          185.804 |              2384.8  |                   24.333 |                     12.433 |                       0.234 |          30 |
| main         | RH-Lean Bias-10%         |  30 |           2298.57  |          142.233 |              2304.9  |                   17.933 |                      6.967 |                       0.222 |          30 |
| main         | RH-Lean SoC0=0.2         |  30 |           2243.22  |          204.915 |              2156.5  |                   21.733 |                     10.4   |                       0.225 |          30 |
| main         | RH-Lean SoC0=0.4         |  30 |           2334.51  |          513.815 |              2189.4  |                   21.867 |                     10.5   |                       0.228 |          30 |
| main         | RH-Lean Tp=1             |  30 |           2242.9   |          307.677 |              2133.6  |                   14.6   |                      5.867 |                       0.072 |          30 |
| main         | RH-Lean Tp=1 noise0      |  30 |           2242.9   |          307.677 |              2133.6  |                   14.6   |                      5.867 |                       0.072 |          30 |
| main         | RH-Lean Tp=10            |  30 |           2302.55  |          295.113 |              2291.4  |                   25.333 |                     13.733 |                       0.411 |          30 |
| main         | RH-Lean Tp=2             |  30 |           2188.38  |          187.548 |              2106.3  |                   17.733 |                      7.233 |                       0.113 |          30 |
| main         | RH-Lean Tp=3             |  30 |           2241.86  |          181.11  |              2202.75 |                   19.067 |                      8.467 |                       0.152 |          30 |
| main         | RH-Lean Tp=7             |  30 |           2194.9   |          139.325 |              2162.1  |                   22.6   |                     11.067 |                       0.3   |          30 |
| main         | RH-Lean noise0           |  30 |           2185.41  |          213.552 |              2105.1  |                   16.467 |                      5.633 |                       0.23  |          30 |
| main         | RH-Lean noise15          |  30 |           2227.8   |          175.868 |              2187.6  |                   22.333 |                     10.967 |                       0.229 |          30 |
| main         | RH-Lean noise25          |  30 |           2270.6   |          172.377 |              2252.7  |                   25     |                     13.3   |                       0.229 |          30 |
| main         | RH-Lean noise5           |  30 |           2239.74  |          178.517 |              2246.4  |                   19.867 |                      8.6   |                       0.227 |          30 |
| main         | RH-Lean w/o graph repair |  30 |           8201.22  |         2750.74  |              7653.5  |                   14.767 |                      4.9   |                       0.084 |          28 |
| main         | RH-Lean w/o local search |  30 |           4965.16  |         1279.87  |              4584    |                   27.133 |                     12.6   |                       0.224 |          29 |
| main         | Snapshot-Lean            |  30 |           3361.36  |          959.212 |              3373.2  |                    5.533 |                      0.167 |                       0.082 |          30 |
| main         | Snapshot-Lean SoC0=0.2   |  30 |           3066.35  |          425.07  |              3109.5  |                    5.533 |                      0.033 |                       0.083 |          30 |
| severe       | RH-Lean                  |  30 |          28464     |          229.89  |             28427.7  |                   25.733 |                     11.267 |                       0.246 |          30 |
| severe       | RH-Lean Tp=1             |  30 |          29020.4   |          367.668 |             28972.8  |                    9.833 |                      1.8   |                       0.073 |          30 |
| severe       | Snapshot-Lean            |  30 |          31466.4   |         1602.05  |             32060.3  |                    3.367 |                      0.033 |                       0.08  |          30 |
| storage_rich | RH-Lean                  |  30 |           1523.28  |          674.518 |              1335.6  |                   16.867 |                      5.767 |                       0.239 |          30 |
| storage_rich | RH-Lean Tp=1             |  30 |           1492.59  |          435.244 |              1359.3  |                   11.533 |                      3.167 |                       0.069 |          30 |
| storage_rich | RH-Lean Tp=1 noise0      |  30 |           1492.59  |          435.244 |              1359.3  |                   11.533 |                      3.167 |                       0.069 |          30 |
| storage_rich | RH-Lean Tp=3             |  30 |           1393.71  |          214.038 |              1375.2  |                   13.533 |                      4.033 |                       0.164 |          30 |
| storage_rich | RH-Lean noise0           |  30 |           1319.68  |          148.863 |              1272    |                   13     |                      2.8   |                       0.238 |          29 |
| storage_rich | Snapshot-Lean            |  30 |           2785.76  |         1045.85  |              2491.25 |                    4.133 |                      0.033 |                       0.078 |          30 |

## Pre-declared tests
| hypothesis   | scenario     | baseline                 | proposed       | metric      |   n |   mean_baseline |   mean_proposed |   median_baseline |   median_proposed |   reduction_pct |     W |      p |   HL_reduction |   CI_low |   CI_high |   rank_biserial |   p_holm |
|:-------------|:-------------|:-------------------------|:---------------|:------------|----:|----------------:|----------------:|------------------:|------------------:|----------------:|------:|-------:|---------------:|---------:|----------:|----------------:|---------:|
| H1-main      | main         | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |         3361.36 |         2247.89 |            3373.2 |            2220   |         33.1257 |   3   | 0      |         974.7  |   747.45 |  1318.6   |          0.9871 |   0      |
| H1-severe    | severe       | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |        31466.4  |        28464    |           32060.3 |           28427.7 |          9.5417 |   0   | 0      |        2941.1  |  2421.3  |  3803.9   |          1      |   0      |
| H1-25-29     | f2_25-29     | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |          884.72 |           35.78 |             799.5 |               0   |         95.9558 |   0   | 0      |         799.5  |   771    |   818.9   |          1      |   0      |
| H1-27-28     | f2_27-28     | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |          976.37 |           46.79 |             799.5 |               0   |         95.2078 |   0   | 0      |         780.2  |   671.25 |   904.7   |          1      |   0      |
| H2a          | main         | RH-Lean w/o graph repair | RH-Lean        | cum_ens_kwh |  30 |         8201.22 |         2247.89 |            7653.5 |            2220   |         72.5908 |   0   | 0      |        5617.07 |  4775.75 |  6681.9   |          1      |   0      |
| H2b          | main         | RH-Lean w/o local search | RH-Lean        | cum_ens_kwh |  30 |         4965.16 |         2247.89 |            4584   |            2220   |         54.7268 |   0   | 0      |        2576.7  |  2196.1  |  3147.25  |          1      |   0      |
| H3           | storage_rich | RH-Lean Tp=1             | RH-Lean        | cum_ens_kwh |  30 |         1492.59 |         1523.28 |            1359.3 |            1335.6 |         -2.0562 | 187.5 | 0.5165 |          34.5  |   -81.05 |   139.275 |          0.1379 |   1      |
| H3'          | main         | RH-Lean Tp=1             | RH-Lean        | cum_ens_kwh |  30 |         2242.9  |         2247.89 |            2133.6 |            2220   |         -0.2223 | 200   | 0.5038 |         -56.4  |  -156.15 |   126.6   |         -0.1398 |   1      |
| H4-main      | main         | RH-Lean                  | RH-Lean noise0 | cum_ens_kwh |  30 |         2247.89 |         2185.41 |            2220   |            2105.1 |          2.7794 | 128   | 0.0876 |          57    |    -4.8  |   141.3   |          0.3695 |   0.3505 |
| H4-storage   | storage_rich | RH-Lean                  | RH-Lean noise0 | cum_ens_kwh |  30 |         1523.28 |         1319.68 |            1335.6 |            1272   |         13.3654 | 149.5 | 0.0877 |          55.5  |   -11.55 |   122.75  |          0.357  |   0.3505 |
