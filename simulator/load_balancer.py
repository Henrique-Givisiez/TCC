"""
Balanceamento de carga no lado do cliente (client-side load balancing --
mesmo padrão usado por Netflix Ribbon, client-go do Kubernetes com serviços
headless, balanceamento no lado do cliente em gRPC): fica só no plano de
CONTROLE (decide qual URL usar), nunca no plano de DADOS (a requisição HTTP
sai direto do worker pra instância, nunca passa por aqui). Por isso não
afeta o RTT medido -- a consulta a get_next_target() é uma chamada de
função em memória, protegida por lock, sem custo de rede.

Cada LoadBalancer é um objeto independente por tipo de tráfego (normal_
traffic.py e traffic_injectorV0.py têm o seu próprio), pra não misturar o
índice de round-robin de um tipo de tráfego com o do outro.

Decisão de design (ver changes.txt): não faz restart de worker nenhum --
update_targets() só atualiza a lista de alvos, os workers continuam vivos e
mandando tráfego no mesmo ritmo o tempo todo. É isso que resolve tanto o
bug de normal_traffic.py (instância nova nunca recebia tráfego, porque a
URL era decidida uma vez na criação da thread) quanto o buraco de ~1s sem
tráfego que existia no reinício do injetor de ataque (stop -> sleep(1) ->
start).
"""
import threading


class LoadBalancer:
    def __init__(self, label):
        self.label = label
        self._lock = threading.Lock()
        self._targets = []
        self._next_idx = 0

    def update_targets(self, target_urls):
        """
        Chamado pelo orquestrador a cada iteração do loop, com a lista
        atual de URLs das instâncias ativas. Seguro de chamar sempre,
        mesmo que a lista não tenha mudado (idempotente) -- não reinicia
        nada, só substitui o estado interno.
        """
        target_urls = list(target_urls)
        with self._lock:
            if target_urls != self._targets:
                print(f"[LoadBalancer:{self.label}] Alvos atualizados: {target_urls}")
            self._targets = target_urls

    def get_next_target(self):
        """
        Chamado por um worker imediatamente antes de cada envio. Devolve a
        próxima URL da rotação round-robin, ou None se ainda não há
        nenhuma instância ativa registrada (ex.: chamado antes do primeiro
        update_targets()).
        """
        with self._lock:
            if not self._targets:
                return None
            url = self._targets[self._next_idx % len(self._targets)]
            self._next_idx += 1
            return url

    def has_targets(self):
        with self._lock:
            return bool(self._targets)


if __name__ == "__main__":
    print("--- Running load_balancer.py self-test ---")

    lb = LoadBalancer("SelfTest")
    assert lb.get_next_target() is None, "Sem alvos configurados, deveria devolver None"
    assert not lb.has_targets()

    lb.update_targets(["http://localhost:8080", "http://localhost:8081"])
    assert lb.has_targets()
    seq = [lb.get_next_target() for _ in range(5)]
    print("Sequência round-robin (2 alvos):", seq)
    assert seq == [
        "http://localhost:8080", "http://localhost:8081",
        "http://localhost:8080", "http://localhost:8081",
        "http://localhost:8080",
    ]

    # Atualização de alvos no meio da rotação não deve travar nem reiniciar nada --
    # só passa a devolver a partir da nova lista.
    lb.update_targets(["http://localhost:8080", "http://localhost:8081", "http://localhost:8082"])
    seq2 = [lb.get_next_target() for _ in range(3)]
    print("Sequência após update_targets (3 alvos):", seq2)
    assert len(set(seq2)) <= 3

    # Concorrência: várias threads chamando get_next_target() ao mesmo tempo
    # não podem corromper o índice (cada URL só sai uma vez por volta completa).
    lb.update_targets(["http://a", "http://b", "http://c", "http://d"])
    results = []
    results_lock = threading.Lock()

    def worker():
        for _ in range(100):
            url = lb.get_next_target()
            with results_lock:
                results.append(url)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 800
    counts = {u: results.count(u) for u in ["http://a", "http://b", "http://c", "http://d"]}
    print("Distribuição sob concorrência (8 threads x 100 chamadas):", counts)
    assert sum(counts.values()) == 800
    assert max(counts.values()) - min(counts.values()) <= 1, "Round-robin deveria distribuir igualmente"

    print("--- load_balancer.py self-test OK ---")
