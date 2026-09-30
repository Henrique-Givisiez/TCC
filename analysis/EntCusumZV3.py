import pandas as pd
import numpy as np
from scipy import stats
import os
import matplotlib.pyplot as plt
from simulator import config

def analisar_bursts_tunavel(input_file='rtt_log.csv', output_prefix=None,
                             window_seconds=20, overlap_percent=50,
                             z_threshold=3.5, baseline_ratio=1.8, show_plot=True,
                             time_col='timestamp', value_col='rtt', value_label='RTT',
                             value_unit='ms', min_samples_per_window=10):
    """
    Detector de burst por janela deslizante (entropia de Shannon + Z-score +
    CUSUM) sobre uma série temporal escalar qualquer -- por padrão RTT
    (rtt_log.csv), mas generalizado (changes.txt) para aceitar também CPU
    (simulation_metrics.csv: time_col='elapsed_time_s', value_col=
    'average_cpu_percent' ou 'host_cpu_percent') via os parâmetros
    time_col/value_col/value_label/value_unit. Os nomes de coluna de SAÍDA
    (xlsx) só mudam se value_label for alterado -- com os defaults (RTT),
    ficam idênticos aos de sempre ("Média RTT", "Status Burst", etc.),
    porque generate_presentation_graphs.py/wedos_graphs.py/
    wedos_ent_cusum_report.py leem esses nomes literalmente.

    min_samples_per_window: mínimo de amostras dentro da janela para ela
    ser analisada (janelas mais esparsas são puladas). RTT tem uma linha
    por requisição (dezenas a centenas por janela de 20s) -- o default 10
    é adequado. CPU tem só 1 linha a cada
    config.MONITOR_INTERVAL_SECONDS (~5s) -- para não descartar toda
    janela, use um window_seconds maior (~50-60s) e/ou um
    min_samples_per_window menor (~5) ao chamar com dado de CPU.
    """
    output_dir = os.path.dirname(input_file)
    base = os.path.splitext(os.path.basename(input_file))[0]
    if output_prefix is None and base == 'rtt_log':
        # Chamado sem argumentos (uso padrão/manual): preserva os nomes de
        # saída originais exatamente como antes.
        xlsx_path = os.path.join(output_dir, 'rtt_bursts_tunaveis.xlsx')
        png_path = os.path.join(output_dir, 'rtt_todos_bursts.png')
    else:
        # Uso em lote (ver run_burst_analysis.py): deriva um sufixo do nome
        # do arquivo de entrada para não sobrescrever a saída de outros runs.
        if output_prefix is None:
            output_prefix = base[len('rtt_log_'):] if base.startswith('rtt_log_') else base
        xlsx_path = os.path.join(output_dir, f'rtt_bursts_{output_prefix}.xlsx')
        png_path = os.path.join(output_dir, f'rtt_todos_bursts_{output_prefix}.png')
    try:
        df = pd.read_csv(input_file)
        df = df.sort_values(time_col).reset_index(drop=True)
        ts_inicial = df[time_col].min()
        df['tempo_rel'] = df[time_col] - ts_inicial

        stride_seconds = window_seconds * (1 - overlap_percent / 100)
        delta_entropia_threshold = 1.5

        resultados = []
        stats_anterior = None
        entropia_anterior = None

        # Baseline = amostras antes do ataque começar (config.ATTACK_START_TIME_
        # SECONDS), em vez de estatísticas do arquivo INTEIRO (que misturava
        # período de ataque no próprio "normal" de referência, subestimando o
        # quão anômalo o ataque realmente é). Serve tanto de referência para o
        # CUSUM (substitui o global_mean/global_std antigo) quanto para o piso
        # de burst logo abaixo.
        baseline = df.loc[df['tempo_rel'] < config.ATTACK_START_TIME_SECONDS, value_col]
        if len(baseline) >= 10:
            global_mean, global_std = baseline.mean(), baseline.std()
        else:
            print(f"[WARNING] Poucas amostras antes do ataque (t<{config.ATTACK_START_TIME_SECONDS}s): "
                  f"{len(baseline)}. Usando o arquivo inteiro como baseline (menos preciso).")
            global_mean, global_std = df[value_col].mean(), df[value_col].std()
        kappa, h = 0.5 * global_std, 5 * global_std

        # Piso de burst relativo ao baseline desta execução, em vez de um
        # valor fixo igual para todo cenário (RPS/WU diferentes têm nível
        # "normal" bem diferente entre si — um piso fixo não separa bem os
        # dois). Não usamos média+k*desvio aqui porque só há ~20s de dado
        # limpo antes do ataque (1 janela), amostra pequena demais para
        # estimar desvio-padrão de janela com confiança — a razão sobre a
        # média (mais estável) funciona melhor com essa quantidade de dado.
        valor_threshold = global_mean * baseline_ratio
        print(f"[INFO] Baseline pré-ataque: média={global_mean:.1f}{value_unit}, "
              f"desvio={global_std:.1f}{value_unit} ({len(baseline)} amostras) "
              f"-> piso de burst = {valor_threshold:.1f}{value_unit} ({baseline_ratio}x a média)")

        # CUSUM -- precomputado 1x por amostra bruta, em ORDEM TEMPORAL, antes
        # do laço de janelas (não reprocessado por janela como antes: com
        # sobreposição de janela > 0, cada amostra aparecia em mais de uma
        # janela, e o laço antigo a somava de novo em cada uma, inflando o
        # CUSUM e tornando sua taxa de crescimento dependente de
        # overlap_percent -- um parâmetro que deveria só controlar
        # granularidade da janela, não sensibilidade de detecção. Bug
        # corrigido, ver changes.txt). Cada janela do relatório abaixo só LÊ
        # o valor já acumulado na última amostra dentro dela.
        cusum_running = np.empty(len(df))
        c = 0.0
        for idx, val in enumerate(df[value_col].values):
            c = max(0.0, c + (val - global_mean) - kappa)
            cusum_running[idx] = c
        df['_cusum_running'] = cusum_running

        # Faixa fixa do histograma de entropia (min/max do arquivo inteiro,
        # não da janela individual) -- antes cada janela recalculava seus
        # próprios limites de bin a partir do próprio min/max, então a
        # "resolução" dos 10 bins mudava de janela pra janela, tornando a
        # entropia não comparável entre elas. Usar o min/max do ARQUIVO
        # INTEIRO (não só do baseline pré-ataque) evita também o problema de
        # np.histogram descartar silenciosamente amostras fora do range
        # informado -- se o range viesse só do baseline, picos de RTT/CPU
        # durante o ataque (fora da faixa "normal") seriam excluídos da
        # contagem em vez de aparecer no bin mais alto, distorcendo a
        # entropia bem no momento que mais interessa medir.
        val_min, val_max = df[value_col].min(), df[value_col].max()

        t_start = 0.0
        while t_start < df['tempo_rel'].max():
            t_end = t_start + window_seconds
            janela_mask = (df['tempo_rel'] >= t_start) & (df['tempo_rel'] < t_end)
            janela = df.loc[janela_mask]

            if len(janela) < min_samples_per_window:
                t_start += stride_seconds
                continue

            ts_aprox_rel = janela['tempo_rel'].mean()
            tempo_formatado = f"{int(ts_aprox_rel // 60):02d}:{ts_aprox_rel % 60:05.1f}"

            valor_medio = janela[value_col].mean()
            valor_std = janela[value_col].std()

            # Entropia (faixa de bins fixa, ver comentário acima)
            hist, _ = np.histogram(janela[value_col], bins=10, range=(val_min, val_max), density=True)
            probs = hist / np.sum(hist) if np.sum(hist) > 0 else np.zeros(10)
            entropia = stats.entropy(probs[probs > 0], base=2) if np.any(probs > 0) else 0.0
            delta_entropia = abs(entropia - entropia_anterior) if entropia_anterior is not None else 0.0
            alarme_entropia = 'Sim' if delta_entropia > delta_entropia_threshold else 'Não'
            entropia_anterior = entropia

            # Z-score tunável
            max_z = 0.0
            alarme_z = 'Não'
            if stats_anterior and stats_anterior['std'] > 0:
                zs = np.abs((janela[value_col] - stats_anterior['media']) / stats_anterior['std'])
                max_z = zs.max()
                alarme_z = 'Sim' if max_z > z_threshold else 'Não'

            # CUSUM -- lê o valor já precomputado (ver acima), não reprocessa
            # a janela.
            cusum_atual = janela['_cusum_running'].iloc[-1]
            alarme_cusum = 'Sim' if cusum_atual > h else 'Não'

            # Status Burst (tunável). Entropia é reportada mas NÃO entra
            # nesta decisão (mantido assim de propósito -- combinar os 3
            # sinais sem medir a taxa de falso-positivo de cada um
            # isoladamente primeiro arriscaria piorar a detecção; decisão
            # registrada em changes.txt).
            status = 'DDoS Burst' if valor_medio > valor_threshold and (alarme_z == 'Sim' or alarme_cusum == 'Sim') else 'Normal/Residual'

            resultados.append({
                'Janela (MM:SS.s)': tempo_formatado,
                f'Média {value_label}': f"{valor_medio:.1f}",
                'Std': f"{valor_std:.1f}",
                'Entropia': f"{entropia:.2f}",
                'Δ Ent.': f"{delta_entropia:.2f}",
                'Al. Ent.': alarme_entropia,
                'Max Z': f"{max_z:.2f}",
                'Al. Z': alarme_z,
                'CUSUM': f"{cusum_atual:.0f}",
                'Al. CUSUM': alarme_cusum,
                'Status Burst': status
            })
            stats_anterior = {'media': valor_medio, 'std': valor_std}
            t_start += stride_seconds

        df_res = pd.DataFrame(resultados)
        print(df_res.to_string(index=False))
        df_res.to_excel(xlsx_path, index=False)

        # Gráfico com bursts destacados
        fig, ax = plt.subplots(figsize=(14,6))
        tempos_seg = [float(row.split(':')[0])*60 + float(row.split(':')[1]) for row in df_res['Janela (MM:SS.s)']]
        col_media = f'Média {value_label}'
        ax.plot(tempos_seg, df_res[col_media].astype(float), 'b-', label=col_media, marker='o')
        bursts = df_res[df_res['Status Burst'] == 'DDoS Burst']
        ax.scatter([tempos_seg[i] for i in bursts.index], bursts[col_media].astype(float), c='r', s=150, marker='X', label='DDoS Bursts Detectados', zorder=5)
        ax.axhline(valor_threshold, color='gray', linestyle='--', alpha=0.6,
                   label=f'Piso de burst ({valor_threshold:.0f}{value_unit})')
        # Janela de ataque lida de config.py em vez de fixa no código, para não
        # ficar desatualizada se ATTACK_START_TIME_SECONDS/PULSE_DURATION mudarem
        # (o ataque agora é uma janela única — ver Fase 1 do roadmap).
        attack_start = config.ATTACK_START_TIME_SECONDS
        attack_end = attack_start + config.PULSE_DURATION
        ax.axvspan(attack_start, attack_end, alpha=0.2, color='orange',
                   label=f'Intervalo Esperado ({attack_start}-{attack_end}s)')
        ax.set_xlabel('Tempo Relativo (s)')
        ax.set_ylabel(f'{col_media} ({value_unit})')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.title(f'Todos os Bursts DDoS (Tunável: Z>{z_threshold}, {value_label}>{baseline_ratio}x baseline)')
        plt.tight_layout()
        plt.savefig(png_path, dpi=300)
        if show_plot:
            plt.show()
        plt.close(fig)

        print(f"\n✅ Bursts detectados: {len(bursts)} | Excel: {xlsx_path} | Gráfico: {png_path}")

        # Retorna o resultado (além de salvar em disco) para permitir uso em
        # lote/scoring sem precisar reabrir o xlsx logo em seguida -- ver
        # scripts de análise estatística (changes.txt).
        return df_res

    except Exception as e:
        print(f"Erro: {e}")
        return None

if __name__ == "__main__":
    analisar_bursts_tunavel(z_threshold=3.5, baseline_ratio=1.8)  # Tune aqui!
