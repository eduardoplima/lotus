# R1 Replication Gate — dev split

Generated 2026-07-04T18:22:02.598082+00:00 · code 04447aced03a · registration sha256 34d3cfba… · dev < 2025-07-01

Regression: last-30-min return ~ first-30-min return. Expected sign: positive.
Published magnitudes for comparison: **not provided** (papers not supplied; nothing fabricated).

| instrument | n | beta | HAC t | lags | hit rate | pass (sign & t≥2) |
|---|---|---|---|---|---|---|
| SPY (from prev close) | 5064 | 0.0442 | 2.27 | 9 | 0.509 | PASS |
| SPY (from open) | 5065 | -0.0663 | -1.43 | 9 | 0.487 | FAIL |
| BTCUSDT | 2870 | -0.0327 | -1.13 | 8 | 0.489 | FAIL |
| ETHUSDT | 2870 | -0.0110 | -0.42 | 8 | 0.497 | FAIL |
| SOLUSDT | 1784 | 0.0259 | 1.26 | 7 | 0.522 | FAIL |
| BNBUSDT | 2789 | -0.0304 | -0.90 | 8 | 0.496 | FAIL |
| ADAUSDT | 2630 | 0.0247 | 1.25 | 8 | 0.485 | FAIL |

## Per-year stability

| instrument | year | n | beta | HAC t |
|---|---|---|---|---|
| SPY (from prev close) | 2005 | 249 | 0.0731 | 2.00 |
| SPY (from prev close) | 2006 | 248 | 0.0338 | 0.95 |
| SPY (from prev close) | 2007 | 245 | 0.1423 | 2.74 |
| SPY (from prev close) | 2008 | 248 | 0.1295 | 1.39 |
| SPY (from prev close) | 2009 | 248 | 0.0421 | 1.16 |
| SPY (from prev close) | 2010 | 249 | 0.0333 | 1.18 |
| SPY (from prev close) | 2011 | 249 | 0.0639 | 1.17 |
| SPY (from prev close) | 2012 | 244 | 0.0571 | 2.93 |
| SPY (from prev close) | 2013 | 245 | 0.0962 | 3.76 |
| SPY (from prev close) | 2014 | 246 | 0.0337 | 1.06 |
| SPY (from prev close) | 2015 | 248 | -0.0028 | -0.07 |
| SPY (from prev close) | 2016 | 249 | -0.0014 | -0.04 |
| SPY (from prev close) | 2017 | 246 | -0.0147 | -0.52 |
| SPY (from prev close) | 2018 | 245 | -0.0787 | -1.08 |
| SPY (from prev close) | 2019 | 246 | 0.0055 | 0.23 |
| SPY (from prev close) | 2020 | 249 | 0.0809 | 1.30 |
| SPY (from prev close) | 2021 | 249 | -0.0786 | -2.35 |
| SPY (from prev close) | 2022 | 248 | -0.0206 | -0.75 |
| SPY (from prev close) | 2023 | 245 | 0.0222 | 0.91 |
| SPY (from prev close) | 2024 | 246 | -0.0330 | -1.33 |
| SPY (from prev close) | 2025 | 122 | -0.0221 | -0.54 |
| SPY (from open) | 2005 | 250 | 0.0869 | 1.17 |
| SPY (from open) | 2006 | 248 | 0.0089 | 0.15 |
| SPY (from open) | 2007 | 245 | -0.0116 | -0.12 |
| SPY (from open) | 2008 | 248 | -0.2854 | -2.79 |
| SPY (from open) | 2009 | 248 | 0.0768 | 1.33 |
| SPY (from open) | 2010 | 249 | 0.0782 | 0.92 |
| SPY (from open) | 2011 | 249 | -0.0117 | -0.10 |
| SPY (from open) | 2012 | 244 | 0.1894 | 3.32 |
| SPY (from open) | 2013 | 245 | 0.1543 | 2.34 |
| SPY (from open) | 2014 | 246 | -0.0885 | -1.54 |
| SPY (from open) | 2015 | 248 | 0.0497 | 0.58 |
| SPY (from open) | 2016 | 249 | 0.0036 | 0.06 |
| SPY (from open) | 2017 | 246 | 0.0082 | 0.13 |
| SPY (from open) | 2018 | 245 | 0.0009 | 0.01 |
| SPY (from open) | 2019 | 246 | -0.0106 | -0.19 |
| SPY (from open) | 2020 | 249 | -0.1372 | -0.44 |
| SPY (from open) | 2021 | 249 | -0.1157 | -2.01 |
| SPY (from open) | 2022 | 248 | -0.0753 | -1.05 |
| SPY (from open) | 2023 | 245 | -0.0055 | -0.13 |
| SPY (from open) | 2024 | 246 | -0.1020 | -1.34 |
| SPY (from open) | 2025 | 122 | 0.1251 | 1.17 |
| BTCUSDT | 2017 | 136 | -0.0399 | -0.27 |
| BTCUSDT | 2018 | 361 | -0.0682 | -1.30 |
| BTCUSDT | 2019 | 365 | 0.0051 | 0.11 |
| BTCUSDT | 2020 | 366 | -0.0368 | -0.94 |
| BTCUSDT | 2021 | 365 | -0.0400 | -0.87 |
| BTCUSDT | 2022 | 365 | -0.0002 | -0.00 |
| BTCUSDT | 2023 | 365 | -0.0535 | -0.78 |
| BTCUSDT | 2024 | 366 | 0.0649 | 1.63 |
| BTCUSDT | 2025 | 181 | 0.0090 | 0.22 |
| ETHUSDT | 2017 | 136 | -0.0967 | -0.93 |
| ETHUSDT | 2018 | 361 | -0.0537 | -0.90 |
| ETHUSDT | 2019 | 365 | -0.0168 | -0.21 |
| ETHUSDT | 2020 | 366 | 0.0494 | 0.87 |
| ETHUSDT | 2021 | 365 | 0.0212 | 0.45 |
| ETHUSDT | 2022 | 365 | 0.0268 | 0.45 |
| ETHUSDT | 2023 | 365 | -0.0411 | -1.00 |
| ETHUSDT | 2024 | 366 | 0.0240 | 0.72 |
| ETHUSDT | 2025 | 181 | 0.0266 | 0.82 |
| SOLUSDT | 2020 | 142 | 0.0010 | 0.03 |
| SOLUSDT | 2021 | 365 | 0.0157 | 0.39 |
| SOLUSDT | 2022 | 365 | 0.0867 | 1.66 |
| SOLUSDT | 2023 | 365 | -0.0179 | -0.37 |
| SOLUSDT | 2024 | 366 | 0.0416 | 1.36 |
| SOLUSDT | 2025 | 181 | 0.0593 | 0.92 |
| BNBUSDT | 2018 | 361 | -0.0072 | -0.12 |
| BNBUSDT | 2019 | 365 | -0.0386 | -0.72 |
| BNBUSDT | 2020 | 366 | -0.0103 | -0.19 |
| BNBUSDT | 2021 | 365 | 0.0308 | 0.76 |
| BNBUSDT | 2022 | 365 | -0.0096 | -0.22 |
| BNBUSDT | 2023 | 365 | -0.0265 | -0.68 |
| BNBUSDT | 2024 | 366 | 0.1017 | 1.83 |
| BNBUSDT | 2025 | 181 | 0.0582 | 0.87 |
| ADAUSDT | 2018 | 257 | -0.0885 | -1.80 |
| ADAUSDT | 2019 | 365 | 0.0174 | 0.34 |
| ADAUSDT | 2020 | 366 | 0.0041 | 0.10 |
| ADAUSDT | 2021 | 365 | 0.0980 | 2.12 |
| ADAUSDT | 2022 | 365 | 0.0358 | 0.90 |
| ADAUSDT | 2023 | 365 | -0.0080 | -0.19 |
| ADAUSDT | 2024 | 366 | 0.0913 | 2.63 |
| ADAUSDT | 2025 | 181 | 0.0239 | 0.55 |

## Gate verdict (mechanical)

Required: SPY canonical (prev-close) AND BTCUSDT AND ETHUSDT — sign>0, HAC t≥2.

**R1 GATE: FAIL — cemetery entry, sprint ends**
