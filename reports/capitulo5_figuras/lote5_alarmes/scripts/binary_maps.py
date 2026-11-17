#!/usr/bin/env python3
"""Mapas binários TEST por bloco, sem reexecutar detectores ou agregar decisões."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import (FEATURE_NAMES, FEATURES, METHODS, MNAMES, OUT, SCENARIOS, VIZ,
                   source_rows, style)

COLORS = ("#F5F7F8", "#173B61", "#9AA5AD")
CMAP = ListedColormap(COLORS)
NORM = BoundaryNorm([-.5, .5, 1.5, 2.5], CMAP.N)
PROTECTED = ("f53d_alarmes_post.pdf", "f53d_alarmes_post.png",
             "f53c_alarmes_assimetrico.pdf", "f53c_alarmes_assimetrico.png",
             "f53c_alarmes_flooding.pdf", "f53c_alarmes_flooding.png")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrices(rows: pd.DataFrame) -> dict[tuple[str, str], np.ndarray]:
    previous = pd.read_csv(OUT / "processed/proporcao_alarmes_por_segundo.csv")
    assert len(previous) == 3 * 16 * 360
    result = {}
    for scenario, _, _ in SCENARIOS:
        for method in METHODS:
            matrix = np.full((80, 360), 2, dtype=np.uint8)
            for j, feature in enumerate(FEATURES):
                z = rows[(rows.scenario == scenario) & (rows.method == method) &
                         (rows.feature == feature)]
                assert len(z) == 20 * 360
                assert z.groupby("block").entry_id.nunique().eq(1).all()
                assert set(z.block) == set(range(1, 21))
                for block in range(1, 21):
                    b = z[z.block == block].sort_values("second")
                    assert np.array_equal(b.second.to_numpy(), np.arange(30, 390))
                    matrix[j * 20 + block - 1] = b.decision.map({False: 0, True: 1}).fillna(2).astype(np.uint8)
                # A soma das linhas individuais deve reproduzir a curva percentual anterior.
                old = previous[(previous.scenario == scenario) &
                               (previous.method == method) &
                               (previous.feature == feature)].sort_values("second")
                assert np.array_equal(old.second.to_numpy(), np.arange(30, 390))
                block_matrix = matrix[j * 20:(j + 1) * 20]
                valid = (block_matrix != 2).sum(axis=0)
                alarms = (block_matrix == 1).sum(axis=0)
                assert np.array_equal(valid, old.available_executions.to_numpy())
                assert np.array_equal(alarms, old.alarm_executions.to_numpy())
                assert np.allclose(100 * alarms / valid, old.alarm_pct.to_numpy(),
                                   atol=1e-12, rtol=0)
            result[(scenario, method)] = matrix
    return result


def draw_panel(ax: plt.Axes, matrix: np.ndarray, method: str, *, show_phase: bool) -> None:
    ax.imshow(matrix, cmap=CMAP, norm=NORM, interpolation="nearest", aspect="auto",
              extent=(30, 390, 80, 0), rasterized=False)
    ax.set_xlim(30, 390)
    ax.set_ylim(80, 0)
    ax.set_yticks([10, 30, 50, 70], FEATURE_NAMES, fontsize=9)
    ax.tick_params(axis="y", length=0, pad=9)
    ax.set_xticks([30, 90, 150, 210, 270, 330, 390])
    ax.tick_params(axis="x", length=3, color="#75818A", labelsize=9)
    for boundary in (150, 270):
        ax.axvline(boundary, color="#44535B", lw=.85, zorder=3)
    for boundary in (20, 40, 60):
        ax.axhline(boundary, color="white", lw=1.8, zorder=3)
    ax.set_title(MNAMES[method], loc="left", fontsize=11, fontweight="bold", pad=5)
    if show_phase:
        for center, label in ((90, "Período anterior"), (210, "Emissão ofensiva"),
                              (330, "Período pós-ataque")):
            ax.text(center, 1.12, label, transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=8.8, color="#45545B")
    for spine in ax.spines.values():
        spine.set_visible(False)


def legend(fig: plt.Figure, y: float) -> None:
    handles = [Patch(facecolor=COLORS[0], edgecolor="#BCC5CA", label="Sem alarme"),
               Patch(facecolor=COLORS[1], label="Com alarme"),
               Patch(facecolor=COLORS[2], label="Sem decisão válida (NA)")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, y),
               ncol=3, frameon=False, fontsize=9)


def export(fig: plt.Figure, stem: str) -> None:
    folder = OUT / "figures"
    fig.savefig(folder / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(folder / f"{stem}.png", bbox_inches="tight", facecolor="white", dpi=240)
    plt.close(fig)


def consolidated(data: dict, scenario: str, title: str, stem: str) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(10.8, 14.2), sharex=True,
                             gridspec_kw={"hspace": .22})
    for i, (ax, method) in enumerate(zip(axes, METHODS)):
        draw_panel(ax, data[(scenario, method)], method, show_phase=i == 0)
    axes[-1].set_xlabel("Tempo experimental (s)", labelpad=9)
    legend(fig, .043)
    fig.suptitle(f"Decisões temporais de alarme — {title}", fontsize=13.5,
                 fontweight="bold", y=.99)
    fig.text(.5, .024, "Cada característica: blocos 1–20, de cima para baixo · 1 segundo por coluna",
             ha="center", fontsize=8.7, color="#263238")
    fig.subplots_adjust(left=.235, right=.985, top=.925, bottom=.095)
    export(fig, f"f53c_alarmes_binarios_{stem}")


def divided(data: dict, scenario: str, title: str, stem: str) -> None:
    for method in METHODS:
        fig, ax = plt.subplots(figsize=(10.8, 5.7))
        draw_panel(ax, data[(scenario, method)], method, show_phase=True)
        ax.set_xlabel("Tempo experimental (s)", labelpad=9)
        legend(fig, .075)
        fig.suptitle(f"Decisões de alarme — {title}", fontsize=13.2,
                     fontweight="bold", y=.99)
        fig.text(.5, .025, "Cada característica: blocos 1–20, de cima para baixo · 1 segundo por coluna",
                 ha="center", fontsize=8.5, color="#263238")
        fig.subplots_adjust(left=.235, right=.985, top=.79, bottom=.245)
        export(fig, f"f53c_binario_{stem}_{method.replace('-', '_')}")


def main() -> None:
    style()
    folder = OUT / "figures"
    protected_hashes = {name: digest(folder / name) for name in PROTECTED}
    rows, _, test, _ = source_rows()  # confronta o CSV auditado com os manifests TEST
    assert len(test) == 60
    values = pd.read_csv(VIZ / "processed/detectors.csv", usecols=["t", "value", "unavailable_reason"])
    values = values[values.t.between(31, 390)]
    assert len(values) == 60 * 16 * 360
    assert values.value.notna().all() and values.unavailable_reason.isna().all()
    offensive = rows[rows.scenario.isin(("A3", "F96"))]
    assert len(offensive) == 2 * 20 * 16 * 360
    assert offensive.decision.notna().all()
    data = matrices(offensive)
    for scenario, title, stem in SCENARIOS:
        consolidated(data, scenario, title, stem)
        divided(data, scenario, title, stem)
    assert all(digest(folder / name) == value for name, value in protected_hashes.items())
    print("40 execuções ofensivas; 20 blocos; 16 combinações; 360 segundos; "
          "decisões individuais iguais às séries anteriores; F5.3-D preservada.")


if __name__ == "__main__":
    main()
