"""Replay the saved study requests through the original engine, offline."""
from dataclasses import asdict
import json
from context import PROJECT,OUT,CONFIGS,study_roots
from llm_network_bargaining.replay import replay_log
from llm_network_bargaining.runlog import find_logs,read_log

def replay():
 results=[]
 for path in find_logs(study_roots()):
  if read_log(path).header.get('config_name') not in CONFIGS:continue
  result=replay_log(path);row=asdict(result);row['path']=str(path.relative_to(PROJECT));results.append(row)
  assert result.ok,(row['path'],result.mismatches)
  if len(results)%20==0:print(f'Replayed {len(results)}/160 saved episodes',flush=True)
 assert len(results)==160
 (OUT/'replay_verification.json').write_text(json.dumps(dict(episodes=160,all_matched=True,new_model_calls=False,results=results),indent=2)+'\n')
 print('160/160 saved episodes replay exactly; no model calls',flush=True)
if __name__=='__main__':replay()
