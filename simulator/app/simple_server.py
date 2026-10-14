# app/simple_server.py
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ProcessPoolExecutor
import time
import os
import math

from urllib.parse import urlparse, parse_qs


# Server-owned CPU budgets. Neither query parameters nor legacy env defaults
# change these operations. Keep the same deterministic CPU kernel and pool.
OPERATION_WORK_UNITS = {
    "/light": 10000,
    "/medium": 100000,
    "/expensive": 1000000,
}


def request_workload(path):
    parsed = urlparse(path)
    if parsed.path in OPERATION_WORK_UNITS:
        return OPERATION_WORK_UNITS[parsed.path], 0.0
    # Historical catch-all paths retain query/env behavior for old experiments,
    # proxy readiness and protocol/network regression checks.
    default_work = int(os.getenv("WORK_UNITS", "1000000"))
    default_sleep = float(os.getenv("PROCESSING_TIME", "0"))
    qs = parse_qs(parsed.query)
    return (int(qs.get("work", [default_work])[0]),
            float(qs.get("sleep", [default_sleep])[0]))


def _burn_cpu(work_units):
    """
    Função de trabalho executada nos processos persistentes do pool (_pool).
    Precisa ser definida no nível do módulo para ser "picklable" pelo
    ProcessPoolExecutor.
    """
    for _ in range(work_units):
        _ = math.sqrt(123.456) * math.sin(123.456)


# Pool de processos persistente, criado uma única vez no startup do servidor
# (ver bloco __main__). Isso dá paralelismo real entre núcleos para o trabalho
# de CPU, sem pagar o custo de criar um processo novo a cada requisição.
_pool = None


class SimpleAppHandler(BaseHTTPRequestHandler):
    # Habilita keep-alive (reaproveitamento de conexão TCP entre requisições).
    # Sem isso, cada requisição abre e fecha uma conexão nova, o que sob alta
    # taxa de requisições esgota as portas efêmeras/tabela de conexões do
    # ambiente (sockets em TIME_WAIT se acumulam mais rápido do que expiram).
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        work_units, processing_time = request_workload(self.path)

        t0 = time.perf_counter()

        _pool.submit(_burn_cpu, work_units).result()
        if processing_time > 0:
            time.sleep(processing_time)
        t1 = time.perf_counter()

        hostname = os.getenv("HOSTNAME", "unknown_container")
        body = f"host={hostname} work={work_units} sleep={processing_time:.4f}s elapsed={t1-t0:.4f}s\n".encode()

        # Content-Length é obrigatório com keep-alive (HTTP/1.1): sem ele o
        # cliente não tem como saber onde a resposta termina numa conexão
        # que continua aberta para a próxima requisição.
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    # Dentro do container, mantenha 80; no host você mapeia pra 8080
    server_port = int(os.getenv("APP_PORT", "80"))
    pool_size = int(os.getenv("INSTANCE_MAX_CONCURRENT_REQUESTS", "2"))
    _pool = ProcessPoolExecutor(max_workers=pool_size)

    httpd = ThreadingHTTPServer(('', server_port), SimpleAppHandler)
    print(f"Simple app server running on port {server_port} (threading + persistent process pool, pool_size={pool_size})")
    httpd.serve_forever()
