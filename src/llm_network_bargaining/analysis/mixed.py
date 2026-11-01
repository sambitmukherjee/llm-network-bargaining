"""One common-row maximum-likelihood mixed model per point benchmark."""

import warnings

import pandas as pd
from statsmodels.regression.mixed_linear_model import MixedLM

from .data import Dataset, outcome_rows
from .predictions import BENCHMARKS, class_predictions

MIXED_COLUMNS = ["predictor", "intercept", "intercept_se", "pred", "pred_se", "slot1_norm",
                 "slot1_norm_se", "log_likelihood", "aic", "n_obs", "n_groups", "converged", "error", "warnings"]


def fit_mixed_models(ds: Dataset, config: str = "minimum_study",
                      window: str = "second_half") -> pd.DataFrame:
    """Fit points ~ pred + slot1_norm with a random intercept for each episode.

    Undefined benchmark networks are removed before any fit, so all four use
    identical rows. Fits use ML (reml=False); a failed fit is a reported error.
    """
    rows = outcome_rows(ds, window)
    rows = rows[rows.config_name == config]
    predictions = []
    for network in sorted(rows.network_id.unique()):
        table = class_predictions(network)
        if table[list(BENCHMARKS)].notna().all().all():
            predictions.append(table)
    if not predictions:
        return pd.DataFrame(columns=MIXED_COLUMNS)
    data = rows.merge(pd.concat(predictions), on=["network_id", "node_class"], validate="many_to_one")
    results = []
    for predictor in BENCHMARKS:
        frame = data.copy()
        frame["pred"] = frame[predictor]
        row = dict(predictor=predictor, n_obs=len(frame), n_groups=frame.episode_uid.nunique(),
                    converged=False, error=None, warnings=[])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                fit = MixedLM.from_formula("points ~ pred + slot1_norm", groups="episode_uid", data=frame).fit(reml=False)
                for term, name in [("Intercept", "intercept"), ("pred", "pred"), ("slot1_norm", "slot1_norm")]:
                    row[name], row[f"{name}_se"] = float(fit.params[term]), float(fit.bse[term])
                row.update(log_likelihood=float(fit.llf), aic=float(fit.aic), converged=bool(fit.converged))
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["warnings"] = list(dict.fromkeys(str(item.message) for item in caught))
        results.append(row)
    return pd.DataFrame(results).reindex(columns=MIXED_COLUMNS)
