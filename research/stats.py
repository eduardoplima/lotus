"""OLS with Newey-West (HAC) standard errors, on numpy.

Implemented directly (statsmodels is not a project dependency): standard OLS
beta, Bartlett-kernel HAC covariance with the Newey-West (1994) automatic lag
L = floor(4·(T/100)^(2/9)). Sanity property (unit-tested): with iid data and
L=0 the HAC t equals the classical OLS t.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OlsHacResult:
    beta: float
    intercept: float
    t_hac: float
    se_hac: float
    n: int
    lags: int
    hit_rate: float  # sign-agreement of y with beta*x direction


def newey_west_lags(n: int) -> int:
    return int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def ols_hac(x: np.ndarray, y: np.ndarray, lags: int | None = None) -> OlsHacResult:
    """Regress y on [1, x]; report the slope's HAC t-stat."""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 30:
        raise ValueError(f"too few observations for inference: {n}")
    if lags is None:
        lags = newey_west_lags(n)

    X = np.column_stack([np.ones(n), x])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta_vec = XtX_inv @ X.T @ y
    resid = y - X @ beta_vec

    # Bartlett-kernel long-run covariance of the score X'e.
    scores = X * resid[:, None]
    S = scores.T @ scores / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        gamma = scores[lag:].T @ scores[:-lag] / n
        S += w * (gamma + gamma.T)
    cov = n * XtX_inv @ S @ XtX_inv
    se_slope = float(np.sqrt(cov[1, 1]))

    slope = float(beta_vec[1])
    sign_pred = np.sign(x) * np.sign(slope)
    hit = float((np.sign(y) == sign_pred)[np.sign(x) != 0].mean())
    return OlsHacResult(
        beta=slope,
        intercept=float(beta_vec[0]),
        t_hac=slope / se_slope,
        se_hac=se_slope,
        n=n,
        lags=lags,
        hit_rate=hit,
    )


def hac_mean_t(y: np.ndarray, lags: int | None = None) -> tuple[float, float, int]:
    """HAC t-stat that mean(y) != 0 (regression on a constant only)."""
    y = y[np.isfinite(y)]
    n = len(y)
    if lags is None:
        lags = newey_west_lags(n)
    mu = float(y.mean())
    e = y - mu
    S = float(e @ e) / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        S += 2.0 * w * float(e[lag:] @ e[:-lag]) / n
    se = np.sqrt(S / n)
    return mu, mu / se, n


def annualized_sharpe(returns: np.ndarray, periods_per_year: float) -> float:
    r = returns[np.isfinite(returns)]
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    return float(r.mean() / sd * np.sqrt(periods_per_year))
