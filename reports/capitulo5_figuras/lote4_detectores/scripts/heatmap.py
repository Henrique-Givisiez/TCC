#!/usr/bin/env python3
"""F5.3-B: recalls oficiais TEST em dois mapas; preserva figura e IC anteriores."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from generate import FEATURES, METHODS, MNAMES, OUT, extract, load

XLABELS = ("Requisições\nHTTP", "Pacotes\nTCP", "Payload\nTCP", "Duração\nHTTP")
SCENARIOS = (("A3", "Ataque computacional assimétrico"), ("F96", "Inundação HTTP"))


def checked_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    official, test, _ = load()
    main, _, _, contrasts, _ = extract(official, test)
    previous = pd.read_csv(OUT / "tables/t53a_desempenho_detectores.csv")
    keys = ["method", "feature"]
    fields = ["recall_A3_pct", "recall_F96_pct"]
    assert len(previous) == len(main) == 16
    assert previous[keys].equals(main[keys])
    for field in fields:
        assert np.allclose(previous[field], main[field], atol=1e-12, rtol=0)
        assert previous[field].between(0, 100).all()
    assert all(main.iloc[i].method == method and main.iloc[i].feature == feature
               for i, (method, feature) in enumerate((m, f) for m in METHODS for f in FEATURES))
    assert len(test) == 60 and all(sum(e["scenario"] == s for e in test.values()) == 20 for s, _ in SCENARIOS)
    for block in range(1, 21):
        assert {e["scenario"] for e in test.values() if e["block"] == block} == {"L2", "A3", "F96"}
    # Cópia organizada: estimativas e IC inferenciais continuam sendo os oficiais.
    supplemental = main[["detector", "caracteristica", "method", "feature", *fields]].merge(
        contrasts[["method", "feature", "contrast", "n_paired_blocks", "estimate_pp",
                   "ci_low_pp", "ci_high_pp", "ci_level", "ci_method", "resamples"]],
        on=keys, validate="one_to_one")
    assert len(supplemental) == 16
    assert (supplemental.n_paired_blocks == 20).all()
    return main, supplemental


def draw(main: pd.DataFrame) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42,
                         "text.color": "#263238", "axes.labelcolor": "#263238"})
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.5), sharey=True)
    cmap = plt.get_cmap("cividis")
    for ax, (scenario, title) in zip(axes, SCENARIOS):
        values = main[f"recall_{scenario}_pct"].to_numpy().reshape(4, 4)
        im = ax.imshow(values, cmap=cmap, vmin=0, vmax=100, interpolation="nearest", aspect="equal")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=11)
        ax.set_xticks(range(4), XLABELS, fontsize=9)
        ax.set_yticks(range(4), [MNAMES[m] for m in METHODS], fontsize=10)
        ax.tick_params(length=0, pad=6)
        ax.set_xticks(np.arange(-.5, 4, 1), minor=True)
        ax.set_yticks(np.arange(-.5, 4, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=.8)
        ax.tick_params(which="minor", bottom=False, left=False)
        for y in range(4):
            for x in range(4):
                value = float(values[y, x])
                red, green, blue, _ = cmap(value / 100)
                luminance = .2126 * red + .7152 * green + .0722 * blue
                color = "#FFFFFF" if luminance < .48 else "#17202A"
                ax.text(x, y, f"{value:.1f}%".replace(".", ","), ha="center", va="center",
                        color=color, fontsize=10, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_visible(False)
    cax = fig.add_axes([.91, .255, .016, .515])
    colorbar = fig.colorbar(im, cax=cax, ticks=[0, 25, 50, 75, 100])
    colorbar.set_label("Recall por janela (%)", labelpad=9)
    colorbar.outline.set_visible(False)
    fig.suptitle("Recall dos detectores nos mecanismos ofensivos", fontsize=14,
                 fontweight="bold", y=.96)
    fig.text(.5, .045, "20 execuções por cenário · Recall médio por execução · Período [150,270) s",
             ha="center", fontsize=9, color="#263238")
    fig.subplots_adjust(left=.135, right=.89, top=.79, bottom=.21, wspace=.18)
    directory = OUT / "figures"
    for ext, options in (("pdf", {}), ("png", {"dpi": 240})):
        fig.savefig(directory / f"f53b_recall_heatmap.{ext}", facecolor="white", bbox_inches="tight", **options)
    plt.close(fig)


def main() -> None:
    main_table, supplemental = checked_data()
    supplemental.to_csv(OUT / "processed/recalls_e_contrastes.csv", index=False)
    draw(main_table)
    print("32 recalls conferidos com T5.3-A e resumo oficial; 16 contrastes oficiais preservados.")


if __name__ == "__main__":
    main()
