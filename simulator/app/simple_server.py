# app/simple_server.py
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ProcessPoolExecutor
import time
import os
import math

from urllib.parse import urlparse, parse_qs


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
        # Parametrização por env: WORK_UNITS (CPU) e PROCESSING_TIME (latência)
        #Valores defaults
        default_work = int(os.getenv("WORK_UNITS", "1000000"))      # 1e6 = pesado; use 0 para "sem loop"
        default_sleep = float(os.getenv("PROCESSING_TIME", "0"))  # em segundos; ex.: 0.05

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        work_units = int(qs.get("work",[default_work])[0])
        processing_time = float(qs.get("sleep",[default_sleep])[0])

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
