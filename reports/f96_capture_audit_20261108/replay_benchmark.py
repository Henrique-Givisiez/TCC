import sys,io,time,tempfile,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path.cwd()))
from simulator.tcpdump_sniffer import TcpdumpSniffer
from simulator.ground_truth import GroundTruth
with tempfile.TemporaryDirectory() as d:
 gt=GroundTruth('bench',Path(d)/'events.csv'); gt.plan_event('a','e','continuous',150,270)
 line=f'{gt.clock.epoch_initial+160:.6f} IP 172.20.0.3.40000 > 172.20.0.2.80: tcp 10\n'
 times=[]
 for repeat in range(3):
  s=TcpdumpSniffer('offline',Path(d)/'capture.csv',gt); s.process=SimpleNamespace(stdout=io.StringIO(line*100000))
  t=time.perf_counter(); s._reader_loop(); times.append(time.perf_counter()-t)
  assert s.reader_error is None
 print(json.dumps(times))
