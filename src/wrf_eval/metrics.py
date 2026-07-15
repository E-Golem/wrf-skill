from __future__ import annotations

import math

import numpy as np

DEFAULT_SCORE_METRICS = ["pcc", "bias", "mae", "rmse", "normalized_crmse", "rsd"]


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
        for key in [
            "bias",
            "mae",
            "rmse",
            "crmse",
            "normalized_crmse",
            "pcc",
            "rsd",
            "mape",
            "nse",
            "obs_mean",
            "model_mean",
            "obs_std",
            "model_std",
        ]:
            metrics[key] = math.nan
        return metrics

    err = mod - obs
    obs_std = float(np.std(obs, ddof=1)) if n > 1 else math.nan
    mod_std = float(np.std(mod, ddof=1)) if n > 1 else math.nan
    centered_err = (mod - np.mean(mod)) - (obs - np.mean(obs))
    crmse = float(np.sqrt(np.mean(centered_err**2))) if n > 0 else math.nan
    normalized_crmse = float(crmse / obs_std) if n > 1 and obs_std > 0 else math.nan
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
            "crmse": crmse,
            "normalized_crmse": normalized_crmse,
            "pcc": pcc,
            "rsd": rsd,
            "mape": mape,
            "nse": nse,
        }
    )
    return metrics


def normalize_metric_names(metric_names: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if metric_names is None:
        return list(DEFAULT_SCORE_METRICS)
    if isinstance(metric_names, str):
        raw_names = metric_names.split(",")
    else:
        raw_names = list(metric_names)
    aliases = {
        "corr": "pcc",
        "correlation": "pcc",
        "pearson": "pcc",
        "ncrmse": "normalized_crmse",
        "normalized_crmse": "normalized_crmse",
        "normalized-crmse": "normalized_crmse",
        "normalized crmse": "normalized_crmse",
        "normalized c-rmse": "normalized_crmse",
        "normalized cRMSE".lower(): "normalized_crmse",
    }
    normalized = []
    for name in raw_names:
        key = str(name).strip().lower()
        if not key:
            continue
        key = aliases.get(key, key)
        if key not in {"pcc", "bias", "mae", "rmse", "normalized_crmse", "rsd"}:
            raise ValueError(f"Unsupported score metric: {name!r}")
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise ValueError("At least one score metric must be selected.")
    return normalized


def score_from_metrics(
    metrics: dict[str, float],
    observed_std: float | None = None,
    selected_metrics: list[str] | tuple[str, ...] | str | None = None,
) -> float:
    """Build a bounded 0-100 score from selected verification metrics."""
    obs_std = observed_std if observed_std is not None else metrics.get("obs_std", math.nan)
    if not obs_std or not np.isfinite(obs_std) or obs_std <= 0:
        obs_std = max(abs(metrics.get("obs_mean", math.nan)), 1.0)

    components = []
    for metric in normalize_metric_names(selected_metrics):
        value = metrics.get(metric, math.nan)
        if metric == "pcc":
            component = np.clip((value + 1.0) / 2.0, 0.0, 1.0) if np.isfinite(value) else 0.0
        elif metric == "bias":
            component = 1.0 / (1.0 + abs(value) / obs_std) if np.isfinite(value) else 0.0
        elif metric in {"rmse", "mae"}:
            component = 1.0 / (1.0 + value / obs_std) if np.isfinite(value) else 0.0
        elif metric == "normalized_crmse":
            component = 1.0 / (1.0 + value) if np.isfinite(value) else 0.0
        elif metric == "rsd":
            component = 1.0 / (1.0 + abs(value - 1.0)) if np.isfinite(value) else 0.0
        else:
            raise ValueError(f"Unsupported score metric: {metric!r}")
        components.append(component)

    score = 100.0 * float(np.mean(components))
    return float(np.clip(score, 0.0, 100.0))
