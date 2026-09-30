"""
Lê /proc/stat para calcular a % de CPU do HOST inteiro (todos os núcleos
somados), como complemento ao CPU% por container que stats_collector.py já
coleta. Existe pra dar evidência direta de que um teto de capacidade
observado é saturação real de CPU do host (WSL2/Linux), não um artefato do
simulador -- ver changes.txt para o contexto completo dessa investigação.

Não usa psutil (não está no ambiente do projeto) -- só parseia /proc/stat,
disponível em qualquer kernel Linux, inclusive dentro do WSL2.

Padrão stateful (como get_average_rtt_ms em normal_traffic.py): guarda a
leitura anterior em módulo, e cada chamada calcula a % de uso NÃO-ocioso
desde a chamada anterior (não é uma foto instantânea -- /proc/stat só dá
contadores acumulados desde o boot, então a % vem da diferença entre duas
leituras). A primeira chamada de uma execução não tem leitura anterior para
comparar e retorna 0.0, mesma convenção usada em outras métricas "desde a
última leitura" do projeto.
"""

_prev_total = None
_prev_idle = None


def _read_cpu_jiffies():
    with open("/proc/stat") as f:
        primeira_linha = f.readline()
    # Formato: "cpu  user nice system idle iowait irq softirq steal guest guest_nice"
    valores = [int(v) for v in primeira_linha.split()[1:]]
    idle = valores[3] + valores[4]  # idle + iowait
    total = sum(valores)
    return total, idle


def get_host_cpu_percent():
    """% de CPU do host (agregada, todos os núcleos) desde a última chamada.
    Chamar uma vez por tick do laço principal (mesmo cadenciamento de
    config.MONITOR_INTERVAL_SECONDS). Retorna 0.0 se /proc/stat não estiver
    disponível (ex.: rodando fora de Linux) em vez de derrubar a simulação —
    esse dado é evidência complementar, não deve ser um ponto de falha."""
    global _prev_total, _prev_idle
    try:
        total, idle = _read_cpu_jiffies()
    except (OSError, ValueError, IndexError) as e:
        print(f"[host_stats] Não foi possível ler /proc/stat: {e}")
        return 0.0

    if _prev_total is None:
        _prev_total, _prev_idle = total, idle
        return 0.0

    delta_total = total - _prev_total
    delta_idle = idle - _prev_idle
    _prev_total, _prev_idle = total, idle

    if delta_total <= 0:
        return 0.0

    return 100.0 * (1.0 - (delta_idle / delta_total))


if __name__ == "__main__":
    import time
    print("--- host_stats.py self-test: 5 amostras, 1s de intervalo ---")
    for _ in range(5):
        print(f"  host_cpu_percent = {get_host_cpu_percent():.1f}%")
        time.sleep(1)
