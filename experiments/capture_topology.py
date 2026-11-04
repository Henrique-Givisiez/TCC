"""Explicit capture direction contracts shared by validation and extraction."""
def capture_destination(capture, configuration):
    segment = capture.get('segment')
    mode = configuration.get('topology', {}).get('mode', 'proxy')
    if segment not in ('source_proxy', 'source_victim'):
        raise ValueError('Unknown capture segment: ' + str(segment))
    expected = 'direct' if segment == 'source_victim' else 'proxy'
    if mode != expected or capture.get('topology', expected) != expected:
        raise ValueError('Capture segment contradicts configured topology')
    ip = capture.get('victim_ip' if expected == 'direct' else 'proxy_ip')
    port = capture.get('target_port', 80)
    if not ip or type(port) is not int or not 0 < port < 65536:
        raise ValueError('Capture destination identity/port missing')
    if expected == 'direct' and (not capture.get('target_id') or capture.get('target_ip') != ip):
        raise ValueError('Direct capture lacks consistent victim identity')
    return ip, port
