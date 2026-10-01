"""Technical protocol/retry checks; never an official scientific dataset."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

import docker
import requests
from simulator import config
from simulator.http_proxy import HttpProxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    client = docker.from_env(environment={'DOCKER_HOST': config.DOCKER_ENGINE_SOCKET})
    victims = []
    proxy = None
    capture = None
    output = None
    token = uuid.uuid4().hex[:8]
    try:
        for index in range(2):
            victims.append(client.containers.run(config.DOCKER_IMAGE_NAME,
                           name=f'stage4_protocol_{token}_{index}', detach=True,
                           network=config.DOCKER_NETWORK_NAME, environment={'WORK_UNITS':'0'},
                           restart_policy={'Name':'no'}))
        proxy = HttpProxy(client, directory/'proxy_artifacts')
        proxy.start(victims)
        network = client.networks.get(config.DOCKER_NETWORK_NAME)
        victim_ips = [v.attrs['NetworkSettings']['Networks'][config.DOCKER_NETWORK_NAME]['IPAddress'] for v in victims]
        output = (directory/'backend_capture.txt').open('w')
        capture = subprocess.Popen(['tcpdump','-i','br-'+network.id[:12],'-l','-n','-tt','-S',
                                   'tcp and ('+' or '.join('host '+ip for ip in victim_ips)+')'],
                                   stdout=output, stderr=subprocess.PIPE, text=True)
        time.sleep(.3)
        bodies = []
        with requests.Session() as session:
            session.trust_env=False
            for n in range(10):
                r = session.get(config.SERVICE_ENDPOINT+'/protocol/path?work=17&sleep=0.001&encoded=a%2Fb&n='+str(n),
                                headers={'X-Edos-Request-Id':f'protocol_{n}'},timeout=3)
                assert r.status_code==200 and r.raw.version==11
                assert 'work=17 sleep=0.0010s' in r.text
                bodies.append(r.text)
        # Two successful persistent backend streams, reused across HTTP requests.
        time.sleep(.2)
        capture.terminate(); _,err=capture.communicate(timeout=5); output.close()
        (directory/'capture_stderr.txt').write_text(err)
        capture=None
        backend_lines=(directory/'backend_capture.txt').read_text().splitlines()
        syns=[line for line in backend_lines if 'Flags [S]' in line]
        assert not syns, 'readiness upstream keepalive connections were not reused'
        assert any('length ' in line and not line.endswith('length 0') for line in backend_lines)
        victims[0].stop(timeout=1)
        results=[]
        with requests.Session() as session:
            session.trust_env=False
            for n in range(4):
                r=session.get(config.SERVICE_ENDPOINT+'/?work=0&sleep=0',
                              headers={'X-Edos-Request-Id':f'failure_{n}'},timeout=6)
                results.append(r.status_code)
        assert 200 in results and any(status in (502,504) for status in results)
        proxy.close(True); proxy=None
        logs=[json.loads(line) for line in (directory/'proxy_artifacts/proxy_access.log').read_text().splitlines()]
        normal=[r for r in logs if r['request_id'].startswith('protocol_')]
        failure=[r for r in logs if r['request_id'].startswith('failure_')]
        assert len(normal)==10 and len(failure)==4
        assert len({r['upstream'] for r in normal})==2
        assert all('/protocol/path?work=17&sleep=0.001&encoded=a%2Fb&n=' in r['request'] for r in normal)
        assert all(',' not in r['upstream'] and r['upstream'] for r in failure)
        assert sum(r['status'] in (502,504) for r in failure)==2 and sum(r['status']==200 for r in failure)==2
        summary=dict(protocol='HTTP/1.1', uri_query_preserved=True, upstream_keepalive=True,
                     backend_syns_during_requests=len(syns), hostname_responses=bodies,
                     backend_failure_http_statuses=results, retries_observed=0,
                     technical_only=True, daemon_id=client.info()['ID'])
        (directory/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary,indent=2))
    finally:
        if capture is not None:
            capture.terminate(); capture.communicate(timeout=5)
        if output is not None and not output.closed:
            output.close()
        if proxy is not None:
            proxy.close(True)
        for victim in victims:
            victim.stop(timeout=1); victim.remove()


if __name__=='__main__':
    main()
