import pandas as pd
import numpy as np

INPUT_FILE = "rtt_log.csv"
WINDOW_SIZE = 20


def shannon_entropy(series, bins=None):
    if len(series) == 0:
        return 0

    if bins is None:
        bins = min(10, int(np.sqrt(len(series))))

    counts, _ = np.histogram(series, bins=bins)

    probs = counts / np.sum(counts)
    probs = probs[probs > 0]

    return -np.sum(probs * np.log2(probs))



def main():
    print("[INFO] Carregando RTT log...")
    df = pd.read_csv(INPUT_FILE)

    # remover RTT inválido
    df = df[df["rtt"] > 0]

    print("[INFO] Normalizando tempo...")
    df["timestamp"] = df["timestamp"] - df["timestamp"].min()

    print("[INFO] Criando janelas de tempo...")
    df["window"] = (df["timestamp"] // WINDOW_SIZE).astype(int)

    results = []

    print("[INFO] Calculando métricas por janela...")

    for w, group in df.groupby("window"):

        rtt_series = group["rtt"]
        rtt_series = rtt_series[rtt_series < 500]

        entropy = shannon_entropy(rtt_series, bins=10)

        # normalizar
        entropy = entropy / np.log2(10)

        # dispersão
        std_dev = rtt_series.std()

        # volume (quantidade de RTTs)
        volume = len(group)

        results.append({
            "window": w,
            "start_time": w * WINDOW_SIZE,
            "end_time": (w + 1) * WINDOW_SIZE,
            "entropy_rtt": entropy,
            "std_rtt": std_dev,
            "volume": volume
        })

    df_out = pd.DataFrame(results)

    print("\n=== RESULTADO ===")
    print(df_out)

    df_out.to_csv("rtt_entropy.csv", index=False)
    print("\n[INFO] Salvo em rtt_entropy.csv")


if __name__ == "__main__":
    main()