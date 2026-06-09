from __future__ import annotations

import math

import numpy as np


def _paired_arrays(observed, modeled) -> tuple[np.ndarray, np.ndarray]:
    obs = np.asarray(observed, dtype=float)
    mod = np.asarray(modeled, dtype=float)
    if obs.shape != mod.shape:
        raise ValueError(f"Observed and modeled arrays must have same shape, got {obs.shape} and {mod.shape}.")
    mask = np.isfinite(obs) & np.isfinite(mod)
    return obs[mask], mod[mask]


def compute_metrics(observed, modeled) -> dict[str, float]:
    """Compute station verification metrics for paired observed and modeled values."""
    obs, mod = _paired_arrays(observed, modeled)
    n = int(obs.size)
    metrics: dict[str, float] = {"n": n}
    if n == 0:
        for key in ["bias", "mae", "rmse", "pcc", "rsd", "mape", "nse", "obs_mean", "model_mean", "obs_std", "model_std"]:
            metrics[key] = math.nan
        return metrics

    err = mod - obs
    obs_std = float(np.std(obs, ddof=1)) if n > 1 else math.nan
    mod_std = float(np.std(mod, ddof=1)) if n > 1 else math.nan
    pcc = float(np.corrcoef(obs, mod)[0, 1]) if n > 1 and obs_std > 0 and mod_std > 0 else math.nan
    rsd = float(mod_std / obs_std) if n > 1 and obs_std > 0 else math.nan
    denominator = float(np.sum((obs - np.mean(obs)) ** 2))
    nse = float(1 - np.sum(err**2) / denominator) if denominator > 0 else math.nan
    nonzero_obs = np.abs(obs) > 1.0e-12
    mape = float(np.mean(np.abs(err[nonzero_obs] / obs[nonzero_obs])) * 100) if np.any(nonzero_obs) else math.nan

    metrics.update(
        {
            "obs_mean": float(np.mean(obs)),
            "model_mean": float(np.mean(mod)),
            "obs_std": obs_std,
            "model_std": mod_std,
            "bias": float(np.mean(err)),
            "mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err**2))),
            "pcc": pcc,
            "rsd": rsd,
            "mape": mape,
            "nse": nse,
        }
    )
    return metrics


def score_from_metrics(metrics: dict[str, float], observed_std: float | None = None) -> float:
    """Build a bounded 0-100 score from correlation, normalized errors, and spread ratio."""
    obs_std = observed_std if observed_std is not None else metrics.get("obs_std", math.nan)
    if not obs_std or not np.isfinite(obs_std) or obs_std <= 0:
        obs_std = max(abs(metrics.get("obs_mean", math.nan)), 1.0)

    pcc = metrics.get("pcc", math.nan)
    rmse = metrics.get("rmse", math.nan)
    mae = metrics.get("mae", math.nan)
    rsd = metrics.get("rsd", math.nan)

    corr_component = np.clip((pcc + 1.0) / 2.0, 0.0, 1.0) if np.isfinite(pcc) else 0.0
    rmse_component = 1.0 / (1.0 + rmse / obs_std) if np.isfinite(rmse) else 0.0
    mae_component = 1.0 / (1.0 + mae / obs_std) if np.isfinite(mae) else 0.0
    rsd_component = 1.0 / (1.0 + abs(rsd - 1.0)) if np.isfinite(rsd) else 0.0

    score = 100.0 * (
        0.35 * corr_component
        + 0.30 * rmse_component
        + 0.20 * mae_component
        + 0.15 * rsd_component
    )
    return float(np.clip(score, 0.0, 100.0))
