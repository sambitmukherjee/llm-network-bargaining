"""Recheck retained run chronology and saved version evidence without the archive."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,subprocess,sys
from context import ROOT,PROJECT,OUT,CONFIGS
from llm_network_bargaining.runlog import find_logs,read_log
PRE='e5e52ea46adf34297147dea7c8587e7cef762f8d';STUDY='ff692b507bf1192d07c1e0ddd39b7e7b14382f3a'
record=ROOT/'provenance/study_provenance.json'
names=['configs/minimum_study.yaml','configs/own_links_arm.yaml','predictions/class_predictions.csv','predictions/node_predictions.csv','predictions/metadata.json','pyproject.toml']
def git(*args):return subprocess.check_output(['git',*args],cwd=PROJECT)
def sha(data):return hashlib.sha256(data).hexdigest()
def verify():
 frozen=json.loads(record.read_text())
 assert all(sha((PROJECT/p).read_bytes())==h for p,h in frozen['files'].items())
 assert frozen['tracked_code_config_dependency_changes']==[]
 if '--verify-git' in sys.argv:
  assert all(sha(git('show',PRE+':'+p))==h for p,h in frozen['files'].items())
  assert git('diff','--name-only',PRE,STUDY,'--','src','configs','pyproject.toml').decode().splitlines()==[]
 runs={}
 for config in CONFIGS:
  records=[read_log(p) for p in find_logs([PROJECT/'runs'/config])]
  assert len(records)==80
  assert all(r.header['git_commit']==PRE and r.header['git_dirty'] is True for r in records)
  assert all(r.header['config_sha256']==frozen['files']['configs/'+config+'.yaml'] for r in records)
  start=min(datetime.fromisoformat(r.header['started_at']) for r in records).astimezone(ZoneInfo('Asia/Kolkata'))
  finish=max(datetime.fromisoformat(r.footer['finished_at']) for r in records).astimezone(ZoneInfo('Asia/Kolkata'))
  assert start.date().isoformat()==finish.date().isoformat()=='2026-11-06'
  expected=('21:06:26','21:39:26') if config=='minimum_study' else ('21:37:44','22:12:44')
  assert (start.strftime('%H:%M:%S'),finish.strftime('%H:%M:%S'))==expected
  runs[config]=dict(episodes=80,start_ist=start.isoformat(),finish_ist=finish.isoformat())
 (OUT/'provenance_verification.json').write_text(json.dumps(dict(runs=runs,version_fingerprints_match=True,git_history_rechecked='--verify-git' in sys.argv,saved_git_record_sha256=sha(record.read_bytes()),modified_tree_qualification='A dirty flag does not identify modified files',new_model_calls=False),indent=2)+'\n')
 print('Run chronology, logged config hashes and six retained pre-sprint file fingerprints verified',flush=True)
if __name__=='__main__':
 verify()
