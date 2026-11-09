"""Paths and imports for the offline sprint reproduction, including clean copies."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1]
PROJECT=Path(os.environ.get('SPRINT_PROJECT_ROOT',ROOT.parent)).resolve()
OUT=ROOT/'results'
DATA=OUT/'data';FIGURES=OUT/'figures'
for p in [OUT,DATA,FIGURES,ROOT/'.cache/tmp',ROOT/'.cache/matplotlib']:p.mkdir(parents=True,exist_ok=True)
os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
for k in ['TMPDIR','TMP','TEMP']:os.environ[k]=str(ROOT/'.cache/tmp')
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'src'))
CONFIGS=['minimum_study','own_links_arm']
NETWORKS=['pair','line3','line4','line5','star3','star4','stem','triangle']

def study_roots():
    return [PROJECT/'runs'/name for name in CONFIGS]

