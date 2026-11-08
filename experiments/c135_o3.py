"""Pinned C1.3.5 launcher; all arguments forwarded to existing controller."""
import os
from pathlib import Path
import subprocess
import sys
import hashlib

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json'
SHA256 = 'c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018'


def environment():
    if hashlib.sha256(PATH.read_bytes()).hexdigest() != SHA256:
        raise ValueError('C1.3.5 specification hash differs')
    env = dict(os.environ)
    for key, expected in [('SCIENTIFIC_SPEC_PATH',str(PATH)),('SCIENTIFIC_SPEC_SHA256',SHA256)]:
        if key in env and env[key] != expected:
            raise ValueError('Conflicting scientific selection: '+key)
        env[key] = expected
    return env


def main():
    return subprocess.call([sys.executable,'-B','-m','experiments.scientific_campaign',*sys.argv[1:]],
                           cwd=ROOT, env=environment())


if __name__ == '__main__':sys.exit(main())
