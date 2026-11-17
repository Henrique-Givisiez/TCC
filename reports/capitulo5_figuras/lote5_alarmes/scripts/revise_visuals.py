#!/usr/bin/env python3
"""Revisão apenas gráfica: mapas temporais e nomenclatura da F5.3-D."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import (FEATURE_NAMES, FEATURES, METHODS, MNAMES, OUT, SCENARIOS,
                   plot_post, save, style)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validated_temporal(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    required = {"scenario", "method", "feature", "second", "alarm_pct",
                "available_executions", "alarm_executions", "missing_executions"}
    assert required <= set(data.columns)
    assert len(data) == 3 * 16 * 360
    assert set(data.scenario) == {"L2", "A3", "F96"}
    assert set(data.method) == set(METHODS) and set(data.feature) == set(FEATURES)
    assert not data.duplicated(["scenario", "method", "feature", "second"]).any()
    assert data.groupby(["scenario", "method", "feature"]).second.nunique().eq(360).all()
    assert set(data.second) == set(range(30, 390))
    assert data.available_executions.eq(20).all() and data.missing_executions.eq(0).all()
    assert np.allclose(data.alarm_pct,
                       100 * data.alarm_executions / data.available_executions,
                       atol=1e-12, rtol=0)
    return data


def plot_temporal_map(data: pd.DataFrame, scenario: str, title: str, stem: str) -> None:
    matrix = np.full((16, 360), np.nan)
    for i, method in enumerate(METHODS):
        for j, feature in enumerate(FEATURES):
            z = data[(data.scenario == scenario) & (data.method == method) &
                     (data.feature == feature)].sort_values("second")
            assert np.array_equal(z.second.to_numpy(), np.arange(30, 390))
            matrix[4 * i + j, :] = z.alarm_pct.to_numpy()
    assert np.isfinite(matrix).all() and ((matrix >= 0) & (matrix <= 100)).all()

    fig, ax = plt.subplots(figsize=(10.8, 6.3))
    cmap = plt.get_cmap("cividis_r").copy()  # baixo: claro; alto: azul escuro
    cmap.set_bad("#D9D9D9")
    mesh = ax.pcolormesh(np.arange(30, 391), np.arange(17), matrix,
                         cmap=cmap, vmin=0, vmax=100, shading="flat", rasterized=False)
    ax.set_xlim(30, 390)
    ax.set_ylim(16, 0)
    ax.set_xticks([30, 90, 150, 210, 270, 330, 390])
    ax.set_xlabel("Tempo experimental (s)", labelpad=10)
    ax.set_yticks(np.arange(16) + .5, list(FEATURE_NAMES) * 4)
    ax.tick_params(axis="y", length=0, pad=7, labelsize=9)
    ax.tick_params(axis="x", length=3, color="#75818A")
    for boundary in (150, 270):
        ax.axvline(boundary, color="#263238", lw=1.0, alpha=.8, zorder=3)
    for boundary in (4, 8, 12):
        ax.axhline(boundary, color="white", lw=2.2, zorder=3)
    for i, method in enumerate(METHODS):
        ax.text(-.55, 1 - (4 * i + 2) / 16, MNAMES[method], transform=ax.transAxes,
                ha="left", va="center", fontsize=9.5, fontweight="bold", color="#263238")
    for center, label in ((90, "Período anterior"), (210, "Emissão ofensiva"),
                          (330, "Período pós-ataque")):
        ax.text(center, 1.025, label, transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=9, color="#45545B")
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(mesh, ax=ax, fraction=.024, pad=.025,
                            ticks=[0, 25, 50, 75, 100])
    colorbar.set_label("Execuções com alarme (%)", labelpad=9)
    colorbar.outline.set_visible(False)
    fig.suptitle(f"Evolução temporal dos alarmes — {title}", fontsize=13.5,
                 fontweight="bold", y=.985)
    fig.text(.5, .025, "20 execuções por cenário · Decisões por segundo",
             ha="center", fontsize=8.5, color="#263238")
    fig.subplots_adjust(left=.315, right=.92, top=.87, bottom=.13)
    save(fig, f"f53c_mapa_temporal_{stem}")


def main() -> None:
    style()
    temporal_path = OUT / "processed/proporcao_alarmes_por_segundo.csv"
    post_path = OUT / "tables/alarmes_post_resumo.csv"
    before = {p: sha256(p) for p in (temporal_path, post_path)}
    temporal = validated_temporal(temporal_path)
    post = pd.read_csv(post_path)
    assert len(post) == 32 and set(post.scenario) == {"A3", "F96"}
    assert post.groupby(["scenario", "method", "feature"]).size().eq(1).all()
    for scenario, title, stem in SCENARIOS:
        plot_temporal_map(temporal, scenario, title, stem)
    plot_post(post)
    assert all(sha256(p) == h for p, h in before.items())
    print("Mapas: 16 combinações × 360 segundos por cenário; denominador 20; "
          "dados processados preservados; F5.3-D apenas com rodapé revisado.")


if __name__ == "__main__":
    main()
