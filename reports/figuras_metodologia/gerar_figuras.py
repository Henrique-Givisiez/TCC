"""Gera as figuras metodológicas em SVG editável, PDF vetorial e PNG."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5,
    "pdf.fonttype": 42, "svg.fonttype": "none",
    "savefig.facecolor": "white", "figure.facecolor": "white",
})

INK = "#20282d"
BLUE = "#38687c"
BLUE_PALE = "#e9f2f5"
ORANGE = "#a16a36"
ORANGE_PALE = "#faf1e5"
GREEN = "#55745f"
GREEN_PALE = "#eaf1eb"
GRAY = "#5e6669"
GRAY_PALE = "#f3f5f5"


def canvas(width, height):
    fig, ax = plt.subplots(figsize=(width / 2.54, height / 2.54), dpi=300)
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    return fig, ax


def box(ax, x, y, w, h, label, *, fc="white", ec=INK, size=8.2,
        weight="normal", radius=0.10, lw=0.85, ha="center"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2))
    tx = x + w / 2 if ha == "center" else x + 0.18
    ax.text(tx, y + h / 2, label, ha=ha, va="center", color=INK,
            fontsize=size, fontweight=weight, linespacing=1.18, zorder=3)


def text(ax, x, y, label, *, size=8.0, color=INK, weight="normal", ha="left"):
    ax.text(x, y, label, fontsize=size, color=color, fontweight=weight,
            ha=ha, va="center", linespacing=1.15, zorder=3)


def arrow(ax, start, end, *, color=INK, lw=1.0, style="solid", head=8,
          connection="arc3"):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
        mutation_scale=head, linewidth=lw, linestyle=style,
        color=color, connectionstyle=connection, zorder=4))


def region(ax, x, y, w, h, title, color, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.15",
        facecolor=fc, edgecolor=color, linewidth=0.95, zorder=1))
    if title:
        text(ax, x + 0.22, y + h - 0.25, title, size=8.4, color=color, weight="bold")


def save(fig, stem):
    for ext in ("svg", "pdf", "png"):
        fig.savefig(ROOT / f"{stem}.{ext}", dpi=300, transparent=False)
    plt.close(fig)


def arquitetura():
    fig, ax = canvas(16.0, 11.5)
    region(ax, 0.30, 6.65, 5.25, 4.50, "FONTES DE TRÁFEGO", BLUE, BLUE_PALE)
    box(ax, 0.58, 9.46, 4.67, 1.26,
        "Legítimas · 2 contêineres\nHTTP → /medium\nEm L2: apenas este grupo",
        fc="white", ec=BLUE, size=7.9, weight="medium")
    box(ax, 0.58, 7.05, 4.67, 1.96,
        "Ofensivas · 2 contêineres\nA3 ou F96 (alternativos)\nA3: /expensive · 8 RPS · conc. 64\nF96: /medium · 64 RPS · conc. 96",
        fc="white", ec=ORANGE, size=7.25)
    text(ax, 0.64, 6.80, "Taxas nominais agregadas", size=7.05, color=GRAY)

    region(ax, 6.70, 6.65, 9.00, 4.50, "APLICAÇÃO VÍTIMA · 1 CONTÊINER", GREEN, GREEN_PALE)
    box(ax, 7.00, 8.14, 2.04, 1.93, "Servidor\nHTTP", fc="white", ec=GREEN,
        size=9.2, weight="bold")
    box(ax, 9.78, 9.40, 2.30, 0.92, "/medium", fc="white", ec=GREEN, size=8.8)
    box(ax, 9.78, 8.28, 2.30, 0.92, "/expensive", fc="white", ec=GREEN, size=8.8)
    box(ax, 12.77, 8.36, 2.60, 1.86,
        "Pool persistente\n2 processos\ncomputacionais", fc="white", ec=GREEN,
        size=8.2)
    arrow(ax, (5.25, 10.10), (7.00, 9.55), color=BLUE, lw=1.25)
    arrow(ax, (5.25, 8.05), (7.00, 8.80), color=ORANGE, lw=1.25)
    arrow(ax, (9.04, 9.42), (9.78, 9.86), color=GREEN)
    arrow(ax, (9.04, 8.82), (9.78, 8.73), color=GREEN)
    arrow(ax, (12.08, 9.86), (12.77, 9.56), color=GREEN)
    arrow(ax, (12.08, 8.73), (12.77, 9.00), color=GREEN)
    text(ax, 6.10, 10.34, "HTTP direto", size=7.4, color=GRAY, ha="center")
    text(ax, 11.08, 7.13, "O pool não limita a 2 conexões HTTP.",
         size=7.4, color=GRAY, ha="center")

    region(ax, 0.30, 3.72, 15.40, 2.45, "", GRAY, GRAY_PALE)
    text(ax, 0.55, 3.94, "OBSERVAÇÃO DURANTE AS EXECUÇÕES",
         size=8.4, color=GRAY, weight="bold")
    obs = [
        (0.55, "Pacotes TCP\ninterface do host"),
        (4.37, "Tentativas e\nrespostas HTTP"),
        (8.19, "Eventos\ncomputacionais"),
        (12.01, "CPU e memória\nda vítima"),
    ]
    for x, label in obs:
        box(ax, x, 4.18, 3.42, 1.42, label, fc="white", ec=GRAY, size=8.0)
    for x in (2.26, 6.08, 9.90, 13.72):
        arrow(ax, (x, 6.64), (x, 6.17), color=GRAY, lw=0.8,
              style=(0, (3, 2)), head=7)

    text(ax, 4.20, 3.38, "PROCESSAMENTO OFFLINE", size=8.4,
         color=GREEN, weight="bold")
    labels = [
        "Dados coletados",
        "Dataset\nvalidado",
        "Características\ntemporais\n(janelas de 1 s)",
        "Detectores estatísticos\nZ-Score · CoV\nEWMA · CUSUM-freeze",
    ]
    xs = [0.35, 4.27, 8.19, 12.11]
    for x, label in zip(xs, labels):
        box(ax, x, 0.76, 3.48, 1.62, label, fc="white", ec=GREEN,
            size=7.1 if "Detectores" in label else 7.7)
    for i in range(3):
        arrow(ax, (xs[i] + 3.48, 1.57), (xs[i + 1], 1.57), color=GREEN,
              lw=1.15, head=9)
    arrow(ax, (2.26, 3.72), (2.26, 2.38), color=GRAY, lw=0.9, head=8)
    text(ax, 8.00, 0.33,
         "CPU e memória: indicadores operacionais; não são entradas dos detectores desta campanha.",
         size=7.1, color=GRAY, ha="center")
    save(fig, "figura_4_1_arquitetura")


def percurso():
    fig, ax = canvas(16.0, 13.0)
    region(ax, 0.30, 9.14, 15.40, 3.52,
           "I · CARACTERIZAÇÃO EXPLORATÓRIA E SELEÇÃO", BLUE, BLUE_PALE)
    box(ax, 0.58, 10.89, 7.15, 1.09,
        "A2 · custo dos endpoints\nA1 · carga legítima",
        fc="white", ec=BLUE, size=8.0)
    box(ax, 8.27, 10.89, 7.15, 1.09,
        "B1 · ataques isolados\nB2 · cenários combinados",
        fc="white", ec=BLUE, size=8.0)
    box(ax, 4.72, 9.78, 6.56, 0.72,
        "Seleção: L2 · A3 · F96", fc="white", ec=BLUE, size=9.0,
        weight="bold")
    arrow(ax, (4.10, 10.89), (6.50, 10.50), color=BLUE)
    arrow(ax, (11.90, 10.89), (9.50, 10.50), color=BLUE)
    box(ax, 4.72, 9.15, 6.56, 0.43,
        "Protocolo experimental congelado", fc="white", ec=BLUE, size=8.8)
    arrow(ax, (8.00, 9.78), (8.00, 9.58), color=BLUE)

    region(ax, 0.30, 5.02, 15.40, 3.20,
           "II · CAMPANHA CIENTÍFICA DEFINITIVA", GREEN, GREEN_PALE)
    text(ax, 15.35, 7.98, "energy-powersaver-20261109", size=7.0,
         color=GREEN, weight="bold", ha="right")
    arrow(ax, (8.00, 9.15), (8.00, 8.22), color=GREEN)
    blocks = [
        (0.58, "BASELINE · 4\nreferência benigna"),
        (4.43, "CAL_A · 8\nlimiares"),
        (8.28, "CAL_B · 8\nverificação"),
        (12.13, "TEST · 60\n20 blocos L2/A3/F96"),
    ]
    for x, label in blocks:
        box(ax, x, 6.42, 3.30, 1.03, label, fc="white", ec=GREEN, size=8.1)
    for i in range(3):
        arrow(ax, (blocks[i][0] + 3.30, 6.94),
              (blocks[i + 1][0], 6.94), color=GREEN, lw=1.15, head=8)
    box(ax, 1.18, 5.36, 13.64, 0.67,
        "Em cada execução: coleta → validação do dataset → características em janelas de 1 s",
        fc="white", ec=GREEN, size=8.1)
    for x in (2.23, 6.08, 9.93, 13.78):
        arrow(ax, (x, 6.42), (x, 6.03), color=GREEN, lw=0.7,
              style=(0, (3, 2)), head=6)

    region(ax, 0.30, 0.34, 15.40, 4.27, "", GRAY, GRAY_PALE)
    text(ax, 8.00, 4.35, "III · PROCESSAMENTO E AVALIAÇÃO",
         size=8.4, color=GRAY, weight="bold", ha="center")
    box(ax, 0.60, 2.14, 7.18, 1.72,
        "RAMO OPERACIONAL\nRegistros → atendimento e recursos\n→ comparação dos efeitos",
        fc="white", ec=GRAY, size=8.2)
    box(ax, 8.22, 2.14, 7.18, 1.72,
        "RAMO DOS DETECTORES (OFFLINE)\nCaracterísticas → detectores com ajustes fixos\n→ alarmes e métricas em TEST",
        fc="white", ec=GRAY, size=8.05)
    arrow(ax, (4.00, 5.02), (4.00, 3.86), color=GRAY, lw=0.95)
    arrow(ax, (12.00, 5.02), (12.00, 3.86), color=GRAY, lw=0.95)
    box(ax, 3.40, 0.77, 9.20, 0.72,
        "Caracterização experimental comparativa",
        fc="white", ec=GRAY, size=8.1, weight="bold")
    arrow(ax, (4.19, 2.14), (6.45, 1.49), color=GRAY)
    arrow(ax, (11.81, 2.14), (9.55, 1.49), color=GRAY)
    save(fig, "figura_4_2_percurso")


if __name__ == "__main__":
    arquitetura()
    percurso()
