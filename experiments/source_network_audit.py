"""Pre-window comparison of actual source/proxy capture points and direct routes."""
import json
from pathlib import Path
import re
import subprocess
import time
from simulator.http_proxy import write_json


TUPLE = re.compile(r'IP (\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+):')


def audit(manager, proxy, backend_inventory, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    ip = proxy.identity['source_ip']
    bpf = f'tcp and ((dst host {ip} and dst port 80) or (src host {ip} and src port 80))'
    network = manager.network
    network.reload()
    bridge = network.attrs.get('Options', {}).get('com.docker.network.bridge.name', 'br-'+network.id[:12])
    # Proxy is created on backend network and then attached to source network.
    iface = proxy.container.exec_run(['sh','-c', 'for n in /sys/class/net/*; do echo "${n##*/} $(cat "$n/iflink")"; done'])
    addresses = proxy.container.exec_run(['ip','-4','addr']).output.decode()
    blocks = re.split(r'(?m)^\d+: ', addresses)
    block = next((b for b in blocks if re.search(r'inet '+re.escape(ip)+r'/', b)), None)
    if block is None:
        raise RuntimeError('cannot identify proxy frontend interface: '+addresses)
    interface = block.split(':',1)[0].split('@',1)[0]
    peers = dict(line.split() for line in iface.output.decode().splitlines())
    index = int(peers[interface])
    veth = next(p.name for p in Path('/sys/class/net').iterdir() if int((p/'ifindex').read_text())==index)
    candidates = ['lo',bridge,veth,'any']
    captures = []
    try:
        for name in candidates:
            diagnostic = (root/(name+'.stderr')).open('w+')
            process = subprocess.Popen(['tcpdump','--immediate-mode','-i',name,'-U','-n','-w',str(root/(name+'.pcap')),bpf],
                                       stdout=subprocess.DEVNULL, stderr=diagnostic)
            captures.append((name,process,diagnostic))
        deadline = time.monotonic()+5
        while not all('listening on' in p.read_text() for p in root.glob('*.stderr')):
            if time.monotonic()>deadline or any(p.poll() is not None for _,p,_ in captures):
                raise RuntimeError('audit tcpdump readiness failed')
            time.sleep(.02)
        replies = []
        for entry, container in zip(manager.entries, manager.containers):
            code = 'import requests,json; s=requests.Session(); s.trust_env=False; r=[s.get("http://edos_service:80/?work=0&sleep=0",headers={"X-Edos-Phase":"capture_audit"},timeout=2).text for _ in range(5)]; print(json.dumps(r))'
            response = container.exec_run(['python','-c',code])
            if response.exit_code:
                raise RuntimeError('source cannot reach proxy: '+response.output.decode())
            replies.append(dict(source_id=entry['source_id'], responses=json.loads(response.output)))
        time.sleep(.2)
    finally:
        for _,process,_ in captures:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        for _,_,diagnostic in captures:
            diagnostic.close()
    summaries = []
    sources = {e['ip'] for e in manager.entries}
    for name in candidates:
        result = subprocess.run(['tcpdump','-nn','-tt','-S','-r',str(root/(name+'.pcap'))],capture_output=True,text=True,check=True)
        lines = result.stdout.splitlines()
        (root/(name+'.txt')).write_text(result.stdout)
        incoming, outgoing, excluded, signatures = set(), set(), [], []
        for line in lines:
            match = TUPLE.search(line)
            if not match:
                excluded.append(line)
                continue
            src,sport,dst,dport = match.groups()
            if src in sources and dst==ip and dport=='80':
                incoming.add(src)
            elif src==ip and sport=='80' and dst in sources:
                outgoing.add(dst)
            else:
                excluded.append(line)
            signatures.append(line[match.start():])
        summaries.append(dict(interface=name, packets=len(lines), source_ips=sorted(incoming), response_ips=sorted(outgoing),
                              outside_segment=len(excluded), repeated_descriptions=len(signatures)-len(set(signatures))))
    valid = [s for s in summaries if set(s['source_ips'])==sources and set(s['response_ips'])==sources and
             not s['outside_segment'] and not s['repeated_descriptions'] and s['interface']!='any']
    if not valid:
        write_json(root/'comparison.json', summaries)
        raise RuntimeError('no empirically valid capture point')
    # The real fault test showed proxy veth disappearance; the validated bridge
    # survives proxy shutdown and preserves the same frontend tuple coverage.
    selected = next((s for s in valid if s['interface']==bridge), valid[0])
    evidence = dict(proxy_ip=ip,bpf=bpf,candidates=summaries, selected_interface=selected['interface'],replies=replies)
    write_json(root/'comparison.json', evidence)
    isolation = []
    for entry, container in zip(manager.entries,manager.containers):
        victim = backend_inventory[0]
        code = '''import socket,json
result={}
for label,address in [('victim_name',%r),('victim_ip',%r)]:
 try:
  with socket.create_connection((address,80),timeout=.3): result[label]='CONNECTED'
 except OSError as exc: result[label]=type(exc).__name__
print(json.dumps(result))
''' % (victim['name'],victim['ip'])
        response = container.exec_run(['python','-c',code])
        if response.exit_code:
            raise RuntimeError('isolation probe failed')
        probes = json.loads(response.output)
        if 'CONNECTED' in probes.values():
            raise RuntimeError('direct source→victim route exists: '+entry['source_id'])
        container.reload()
        if set(container.attrs['NetworkSettings']['Networks'])!={manager.network.name}:
            raise RuntimeError('source connected to unexpected network')
        isolation.append(dict(source_id=entry['source_id'], probes=probes,
                              networks=list(container.attrs['NetworkSettings']['Networks'])))
    write_json(root/'isolation.json',dict(probes=isolation, note='Technical exec probes receive a victim address; generator manifests never do.'))
    return evidence
