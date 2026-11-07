"""Shared code for the exploratory notebooks over the frozen datasets.

Notebooks stay thin: they pick a domain, call these functions and look at the
output. Anything a second notebook would copy lives here instead.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from saos_appeals import config

DOMAIN_TITLES = {
    "civil": "Civil cases (C → Ca / ACa)",
    "social_insurance": "Social-insurance cases (U → Ua / AUa)",
    "labour": "Labour-law cases (P → Pa / APa)",
    "criminal": "Criminal cases (K → Ka / AKa)",
    "commercial": "Commercial cases (GC → Ga / AGa)",
    "family": "Family cases (RC → RCa)",
}

# Journal keys ("year/entry" of Dziennik Ustaw) of the acts that dominate citations.
ACTS = {
    "1964/296": "k.p.c. (civil procedure)",
    "1964/93": "k.c. (civil code)",
    "1974/141": "k.p. (labour code)",
    "1997/553": "k.k. (criminal code)",
    "1997/555": "k.p.k. (criminal procedure)",
    "1998/887": "u.s.u.s. (social insurance system)",
    "1998/1118": "u.e.r. (pensions from FUS)",
    "1999/636": "u.ś.p. (sickness benefits)",
    "2002/1368": "u.ś.p. (sickness benefits, 2002 text)",
    "2004/1693": "u.p.z. (employment promotion)",
    "2003/1835": "u.e.p. (bridging pensions)",
    "1997/593": "k.r.o. amendments (1997/593)",
    "2005/1398": "u.k.s.c. (court fees)",
    "1982/19": "Karta Nauczyciela",
    "2002/1270": "lawyers' fee regulation (2002)",
    "2015/1800": "lawyers' fee regulation (2015)",
    "1997/483": "Constitution",
    "2002/1071": "pre-retirement benefits",
    "2003/1996": "u.w.u.s. (accident insurance)",
}

# Categorical palette (fixed order) and sequential hue, see docs/dataviz notes.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
INK_MUTED = "#898781"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": AXIS,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.titlelocation": "left",
        "axes.titleweight": "bold",
        "axes.labelcolor": INK_MUTED,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "legend.frameon": False,
    }
)


# --- loading -----------------------------------------------------------------


def dataset_path(domain: str, processed: Path = config.PROCESSED_DIR) -> Path:
    files = sorted(processed.glob(f"appeals-{domain}-*.parquet"))
    if not files:
        raise FileNotFoundError(f"no appeals-{domain}-*.parquet in {processed}; run saos-dataset")
    if len(files) > 1:
        raise RuntimeError(f"several files for {domain}: {[f.name for f in files]}; keep one")
    return files[0]


def load_domain(domain: str, processed: Path = config.PROCESSED_DIR) -> pd.DataFrame:
    """The frozen dataset of one domain, with a few derived columns."""
    df = pd.read_parquet(dataset_path(domain, processed))
    df["first_date"] = pd.to_datetime(df["first_judgment_date"], errors="coerce")
    df["appeal_dt"] = pd.to_datetime(df["appeal_date"], errors="coerce")
    df["days_to_appeal"] = (df["appeal_dt"] - df["first_date"]).dt.days
    df["judges_n"] = df["first_judges"].map(len)
    df["anon_tokens"] = df["first_reasons_text"].str.count(r"\(\.\.\.\)")
    df["anon_per_1k"] = 1000 * df["anon_tokens"] / df["first_reasons_len"].clip(lower=1)
    return df


# --- tables ------------------------------------------------------------------


def _span(years: pd.Series) -> str:
    return f"{int(years.min())}–{int(years.max())}"


def overview(df: pd.DataFrame) -> pd.Series:
    return pd.Series(
        {
            "rows": len(df),
            "granted share": round(df["label"].mean(), 3),
            "first-instance years": _span(df["first_judgment_year"]),
            "appeal years": _span(df["appeal_year"]),
            "first-instance courts": df["first_court_id"].nunique(),
            "appellate courts": df["appeal_court_id"].nunique(),
            "median operative chars": int(df["first_operative_len"].median()),
            "median reasons chars": int(df["first_reasons_len"].median()),
            "median days to appeal": int(df["days_to_appeal"].median()),
        }
    )


def outcome_table(df: pd.DataFrame) -> pd.DataFrame:
    t = df["outcome"].value_counts().rename("n").to_frame()
    t["share"] = (t["n"] / len(df)).round(3)
    t["label"] = t.index.map({"dismissed": 0}).fillna(1).astype(int)
    return t


def by_group(df: pd.DataFrame, col: str, min_n: int = 20, top: int | None = None) -> pd.DataFrame:
    """Rows and granted share per value of ``col``; small groups are dropped."""
    t = df.groupby(col)["label"].agg(n="size", granted="mean")
    t = t[t["n"] >= min_n].sort_values("n", ascending=False)
    t["granted"] = t["granted"].round(3)
    t["ci95"] = (1.96 * np.sqrt(t["granted"] * (1 - t["granted"]) / t["n"])).round(3)
    return t.head(top) if top else t


def by_quantile(df: pd.DataFrame, col: str, bins: int = 5) -> pd.DataFrame:
    """Granted share across quantile bins of a numeric column."""
    q = pd.qcut(df[col], bins, duplicates="drop")
    t = df.groupby(q, observed=True)["label"].agg(n="size", granted="mean")
    t["granted"] = t["granted"].round(3)
    return t


def top_items(df: pd.DataFrame, col: str, top: int = 20, names: dict | None = None) -> pd.DataFrame:
    """For a list column: how many rows mention each item and their granted share."""
    counts: Counter[str] = Counter()
    granted: Counter[str] = Counter()
    for items, label in zip(df[col], df["label"], strict=False):
        for item in set(items):
            counts[item] += 1
            granted[item] += int(label)
    t = pd.DataFrame(
        {
            "rows": pd.Series(counts),
            "share of rows": pd.Series({k: v / len(df) for k, v in counts.items()}),
            "granted": pd.Series({k: granted[k] / counts[k] for k in counts}),
        }
    ).sort_values("rows", ascending=False)
    t["share of rows"] = t["share of rows"].round(3)
    t["granted"] = t["granted"].round(3)
    if names:
        t.insert(0, "name", [names.get(k, "") for k in t.index])
    return t.head(top)


def split_balance(df: pd.DataFrame) -> pd.DataFrame:
    s = df.groupby("split")["label"].agg(n="size", granted="mean").round(3)
    f = df.groupby("fold")["label"].agg(n="size", granted="mean").round(3)
    f.index = [f"fold {i}" for i in f.index]
    return pd.concat([s.loc[["train", "valid", "test"]], f])


# --- plots -------------------------------------------------------------------


def _finish(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)


def plot_counts(series: pd.Series, title: str, xlabel: str = "", color: str = SERIES[0]) -> None:
    """Vertical bars of counts; the index is the category or year."""
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.bar(series.index.astype(str), series.values, color=color, width=0.7)
    _finish(ax, title, xlabel, "rows")
    if len(series) > 12:
        ax.tick_params(axis="x", rotation=90)
    fig.tight_layout()


def plot_granted(
    table: pd.DataFrame,
    title: str,
    baseline: float | None = None,
    xlabel: str = "share of appeals granted (any change)",
) -> None:
    """Horizontal bars of a share per group (``granted`` column) with ``n`` printed at the end."""
    t = table.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(t) + 1.2))
    ax.barh(t.index.astype(str), t["granted"], color=SERIES[0], height=0.7)
    if "ci95" in t:
        ax.errorbar(
            t["granted"], t.index.astype(str), xerr=t["ci95"], fmt="none", ecolor=INK_MUTED, lw=1
        )
    ci = t["ci95"] if "ci95" in t else pd.Series(0.0, index=t.index)
    for y, (share, err, n) in enumerate(zip(t["granted"], ci, t["n"], strict=False)):
        ax.text(share + err + 0.01, y, f"n={n}", va="center", fontsize=8, color=INK_MUTED)
    if baseline is not None:
        ax.axvline(baseline, color=SERIES[1], lw=1.2, ls="--", label=f"all rows {baseline:.0%}")
        ax.legend(loc="lower right")
    ax.set_xlim(0, min(1, (t["granted"] + ci).max() + 0.15))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.grid(axis="x")
    ax.grid(False, axis="y")
    _finish(ax, title, xlabel)
    fig.tight_layout()


def plot_hist(df: pd.DataFrame, col: str, title: str, log: bool = True, bins: int = 40) -> None:
    """Histogram of a numeric column, split by label (two series, fixed colours)."""
    fig, ax = plt.subplots(figsize=(8, 3.2))
    values = df[col].clip(lower=1) if log else df[col]
    edges = np.logspace(np.log10(values.min()), np.log10(values.max()), bins) if log else bins
    for label, name, color in ((0, "dismissed", SERIES[0]), (1, "granted", SERIES[1])):
        ax.hist(
            values[df["label"] == label],
            bins=edges,
            alpha=0.75,
            color=color,
            label=name,
            density=True,
        )
    if log:
        ax.set_xscale("log")
    ax.legend()
    _finish(ax, title, col, "density")
    fig.tight_layout()


def plot_year(df: pd.DataFrame, title: str) -> None:
    """Two stacked panels on one x axis: rows per appeal year, granted share per year."""
    t = df.groupby("appeal_year")["label"].agg(n="size", granted="mean")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True, height_ratios=[1, 1])
    ax1.bar(t.index, t["n"], color=SERIES[0], width=0.7)
    _finish(ax1, title, "", "rows")
    ax2.plot(t.index, t["granted"], color=SERIES[1], lw=2, marker="o", ms=4)
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax2.set_ylim(0, 1)
    _finish(ax2, "", "appeal year", "granted share")
    fig.tight_layout()


def describe_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    return df[list(cols)].describe(percentiles=[0.1, 0.5, 0.9]).T.round(1)
