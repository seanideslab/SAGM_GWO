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
| f2_25-29     | RH-Lean                  |  30 |             11.32  |           34.473 |                 0    |                   10.267 |                      1.933 |                       0.225 |          30 |
| f2_25-29     | RH-Lean Tp=1             |  30 |              1.92  |           10.516 |                 0    |                    6.533 |                      0.367 |                       0.073 |          30 |
| f2_25-29     | Snapshot-Lean            |  30 |            884.72  |          315.467 |               799.5  |                    3.233 |                      0.067 |                       0.081 |          30 |
| f2_27-28     | RH-Lean                  |  30 |             37.33  |          119.282 |                 0    |                   12.867 |                      2.9   |                       0.233 |          30 |
| f2_27-28     | RH-Lean Tp=1             |  30 |            155.035 |          203.21  |                28.5  |                   10.533 |                      2.033 |                       0.074 |          30 |
| f2_27-28     | Snapshot-Lean            |  30 |            976.37  |          633.626 |               799.5  |                    6.067 |                      0.067 |                       0.085 |          30 |
| main         | RH-Lean                  |  30 |           2120.75  |          121.102 |              2107.2  |                   20.267 |                      9.167 |                       0.235 |          30 |
| main         | RH-Lean AR1 noise10      |  30 |           2210.45  |          182.761 |              2180.55 |                   18.067 |                      7.4   |                       0.232 |          30 |
| main         | RH-Lean AR1 noise25      |  30 |           2212.74  |          193.11  |              2200.15 |                   22.8   |                     11.467 |                       0.234 |          30 |
| main         | RH-Lean Bias+10%         |  30 |           2317.95  |          174.206 |              2338    |                   22.667 |                     11     |                       0.238 |          30 |
| main         | RH-Lean Bias-10%         |  30 |           2191.2   |          139.299 |              2190.75 |                   17.4   |                      6.9   |                       0.229 |          30 |
| main         | RH-Lean SoC0=0.2         |  30 |           2202.33  |          131.414 |              2159.25 |                   20     |                      9.033 |                       0.234 |          30 |
| main         | RH-Lean SoC0=0.4         |  30 |           2193.64  |          139.314 |              2134.5  |                   20.667 |                      9.6   |                       0.233 |          30 |
| main         | RH-Lean Tp=1             |  30 |           2242.9   |          307.677 |              2133.6  |                   14.6   |                      5.867 |                       0.077 |          30 |
| main         | RH-Lean Tp=1 noise0      |  30 |           2242.9   |          307.677 |              2133.6  |                   14.6   |                      5.867 |                       0.075 |          30 |
| main         | RH-Lean Tp=10            |  30 |           2135.08  |          104.319 |              2123.7  |                   22.6   |                     11.4   |                       0.422 |          30 |
| main         | RH-Lean Tp=2             |  30 |           2227.76  |          222.316 |              2188.8  |                   16.8   |                      6.2   |                       0.116 |          30 |
| main         | RH-Lean Tp=3             |  30 |           2241.52  |          140.617 |              2232.45 |                   17.6   |                      7.433 |                       0.156 |          30 |
| main         | RH-Lean Tp=7             |  30 |           2115.13  |           97.359 |              2106.9  |                   21.067 |                      9.8   |                       0.31  |          30 |
| main         | RH-Lean noise0           |  30 |           2150.16  |           91.743 |              2119.35 |                   15.067 |                      4.7   |                       0.234 |          30 |
| main         | RH-Lean noise15          |  30 |           2220.35  |          175.525 |              2194.5  |                   20.2   |                      9.2   |                       0.234 |          30 |
| main         | RH-Lean noise25          |  30 |           2152.87  |          113.773 |              2159.1  |                   23.333 |                     12.1   |                       0.233 |          30 |
| main         | RH-Lean noise5           |  30 |           2187.88  |          144.862 |              2162.55 |                   17.533 |                      6.6   |                       0.233 |          30 |
| main         | RH-Lean w/o graph repair |  30 |           6721.66  |         1878.7   |              6078.38 |                   12.7   |                      3.8   |                       0.087 |          29 |
| main         | RH-Lean w/o local search |  30 |           4071.52  |          896.641 |              3914.82 |                   23.333 |                      9.733 |                       0.233 |          30 |
| main         | Snapshot-Lean            |  30 |           3361.36  |          959.212 |              3373.2  |                    5.533 |                      0.167 |                       0.086 |          30 |
| main         | Snapshot-Lean SoC0=0.2   |  30 |           3066.35  |          425.07  |              3109.5  |                    5.533 |                      0.033 |                       0.088 |          30 |
| severe       | RH-Lean                  |  30 |          28399.5   |          273.767 |             28373.2  |                   23.8   |                     10.233 |                       0.253 |          30 |
| severe       | RH-Lean Tp=1             |  30 |          29020.4   |          367.668 |             28972.8  |                    9.833 |                      1.8   |                       0.077 |          30 |
| severe       | Snapshot-Lean            |  30 |          31466.4   |         1602.05  |             32060.3  |                    3.367 |                      0.033 |                       0.084 |          30 |
| storage_rich | RH-Lean                  |  30 |           1338.2   |          133.473 |              1323.15 |                   15.067 |                      5     |                       0.244 |          30 |
| storage_rich | RH-Lean Tp=1             |  30 |           1492.59  |          435.244 |              1359.3  |                   11.533 |                      3.167 |                       0.073 |          30 |
| storage_rich | RH-Lean Tp=1 noise0      |  30 |           1492.59  |          435.244 |              1359.3  |                   11.533 |                      3.167 |                       0.073 |          30 |
| storage_rich | RH-Lean Tp=3             |  30 |           1349.84  |          196.793 |              1318.2  |                   12.333 |                      3.4   |                       0.171 |          30 |
| storage_rich | RH-Lean noise0           |  30 |           1278.62  |          132.288 |              1215    |                   10.933 |                      1.933 |                       0.245 |          30 |
| storage_rich | Snapshot-Lean            |  30 |           2785.76  |         1045.85  |              2491.25 |                    4.133 |                      0.033 |                       0.083 |          30 |

## Pre-declared tests
| hypothesis   | scenario     | baseline                 | proposed       | metric      |   n |   mean_baseline |   mean_proposed |   median_baseline |   median_proposed |   reduction_pct |     W |      p |   HL_reduction |   CI_low |   CI_high |   rank_biserial |   p_holm |
|:-------------|:-------------|:-------------------------|:---------------|:------------|----:|----------------:|----------------:|------------------:|------------------:|----------------:|------:|-------:|---------------:|---------:|----------:|----------------:|---------:|
| H1-main      | main         | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |         3361.36 |         2120.75 |           3373.2  |           2107.2  |         36.908  |   0   | 0      |        1139.1  |   845.6  |   1426.5  |          1      |   0      |
| H1-severe    | severe       | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |        31466.4  |        28399.5  |          32060.3  |          28373.2  |          9.7465 |   1   | 0      |        2998.75 |  2487.45 |   3872.8  |          0.9957 |   0      |
| H1-25-29     | f2_25-29     | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |          884.72 |           11.32 |            799.5  |              0    |         98.7205 |   0   | 0      |         817.9  |   780.5  |    904.7  |          1      |   0      |
| H1-27-28     | f2_27-28     | Snapshot-Lean            | RH-Lean        | cum_ens_kwh |  30 |          976.37 |           37.33 |            799.5  |              0    |         96.1767 |   0   | 0      |         800.75 |   695.85 |    913.9  |          1      |   0      |
| H2a          | main         | RH-Lean w/o graph repair | RH-Lean        | cum_ens_kwh |  30 |         6721.66 |         2120.75 |           6078.38 |           2107.2  |         68.449  |   0   | 0      |        4423.25 |  3686.6  |   5335.43 |          1      |   0      |
| H2b          | main         | RH-Lean w/o local search | RH-Lean        | cum_ens_kwh |  30 |         4071.52 |         2120.75 |           3914.82 |           2107.2  |         47.9126 |   0   | 0      |        1835.4  |  1564.4  |   2196.12 |          1      |   0      |
| H3           | storage_rich | RH-Lean Tp=1             | RH-Lean        | cum_ens_kwh |  30 |         1492.59 |         1338.2  |           1359.3  |           1323.15 |         10.3437 | 161.5 | 0.2259 |          73.95 |   -33    |    207.3  |          0.2575 |   0.6778 |
| H3'          | main         | RH-Lean Tp=1             | RH-Lean        | cum_ens_kwh |  30 |         2242.9  |         2120.75 |           2133.6  |           2107.2  |          5.4461 | 175   | 0.2449 |          43.65 |   -27.3  |    223.35 |          0.2473 |   0.6778 |
| H4-main      | main         | RH-Lean                  | RH-Lean noise0 | cum_ens_kwh |  30 |         2120.75 |         2150.16 |           2107.2  |           2119.35 |         -1.3868 | 180   | 0.4174 |         -27.45 |   -87    |     28.65 |         -0.1724 |   0.6778 |
| H4-storage   | storage_rich | RH-Lean                  | RH-Lean noise0 | cum_ens_kwh |  30 |         1338.2  |         1278.62 |           1323.15 |           1215    |          4.4518 | 110   | 0.0342 |          66.75 |     3.3  |    132.6  |          0.4581 |   0.1368 |
