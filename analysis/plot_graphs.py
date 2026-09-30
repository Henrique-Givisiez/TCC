import pandas as pd
import matplotlib.pyplot as plt
import os

# === CONFIG ===
CSV_FILE = "experiment_results/metrics_rps16_att4.csv"
OUTPUT_DIR = "results/graficos"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_data():
    df = pd.read_csv(CSV_FILE)

    # ordenar corretamente
    df = df.sort_values(by="elapsed_time_s").reset_index(drop=True)

    # 🔥 garantir que CPU é numérico
    df["average_cpu_percent"] = pd.to_numeric(
        df["average_cpu_percent"], errors="coerce"
    )

    # remover valores inválidos
    df = df.dropna(subset=["average_cpu_percent"])

    # evitar problema com log (não pode ter zero)
    df["average_cpu_percent"] = df["average_cpu_percent"].replace(0, 0.1)

    return df


def save_plot(fig_name):
    path = f"{OUTPUT_DIR}/{fig_name}.png"
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[OK] Salvo: {path}")


def plot_cpu(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["average_cpu_percent"])
    plt.title("CPU ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("CPU (%)")
    plt.grid()
    save_plot("cpu_tempo")


def plot_instances(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["num_instances"])
    plt.title("Número de instâncias ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Instâncias")
    plt.grid()
    save_plot("instancias_tempo")


def plot_memory(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["mem_usage"])
    plt.title("Uso de memória ao longo do tempo")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Memória (MB)")
    plt.grid()
    save_plot("memoria_tempo")


def plot_cpu_vs_instances(df):
    plt.figure()
    plt.plot(df["elapsed_time_s"], df["average_cpu_percent"], label="CPU (%)")
    plt.plot(df["elapsed_time_s"], df["num_instances"], label="Instâncias")
    plt.title("CPU vs Instâncias")
    plt.xlabel("Tempo (s)")
    plt.legend()
    plt.grid()
    save_plot("cpu_vs_instancias")


def plot_with_attack_labels(df):
    plt.figure()

    # linha contínua
    plt.plot(df["elapsed_time_s"], df["average_cpu_percent"], label="CPU", zorder=1)

    # destacar pontos de ataque
    attack = df[df["label"] == "attack"]

    plt.scatter(
        attack["elapsed_time_s"],
        attack["average_cpu_percent"],
        label="Attack",
        zorder=2
    )

    # escala log base 2
    plt.yscale("log", base=2)
    ticks = [2, 4, 8, 16, 32, 64, 100]
    plt.yticks(ticks, ticks)

    plt.title("CPU com destaque de ataque")
    plt.xlabel("Tempo (s)")
    plt.ylabel("CPU (%)")
    plt.legend()
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)

    save_plot("cpu_attack_highlight")
    
def main():
    df = load_data()

    print("DEBUG dtype CPU:", df["average_cpu_percent"].dtype)

    plot_cpu(df)
    plot_instances(df)
    plot_memory(df)
    plot_cpu_vs_instances(df)
    plot_with_attack_labels(df)

    print("\n✅ Todos os gráficos foram gerados na pasta 'results/graficos/'")


if __name__ == "__main__":
    main()