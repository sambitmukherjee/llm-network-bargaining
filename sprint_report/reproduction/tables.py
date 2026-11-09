"""Rebuild all fifteen paper tables and exact protocol examples from standalone inputs."""
from pathlib import Path
import json,re
import numpy as np
import pandas as pd
from context import ROOT,PROJECT,OUT,DATA
from llm_network_bargaining.engine import Episode
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.prompts import render_prompt
from llm_network_bargaining.quiz import render_quiz,quiz_response_format
from llm_network_bargaining.schema import response_format
from llm_network_bargaining.config import load_config
from llm_network_bargaining.model_client import build_chat_kwargs
from llm_network_bargaining.theory import balanced_outcome,in_core
from llm_network_bargaining.analysis.predictions import advantaged_class

NAMES={'pair':'Pair','line3':'Three-node line','line4':'Four-node line','line5':'Five-node line','star3':'Three-leaf star','star4':'Four-leaf star','stem':'Stem','triangle':'Triangle'}
REFS={'equal_split':'Equal-split earnings reference','myerson':'Myerson value','position_value':'Position value','balanced':'Balanced outcome reference'}
checks=[];directory=OUT/'tables';directory.mkdir(exist_ok=True)
def label(c):return 'Leaves L1–'+c.split('|')[-1] if c.startswith('L1|') else c.replace('|',', ')
def load(name):return pd.read_csv(DATA/name)
def one(frame,**keys):
 for k,v in keys.items():frame=frame[frame[k].eq(v)]
 assert len(frame)==1,(keys,len(frame));return frame.iloc[0]
def interval(r,field='mean',low='ci_low',high='ci_high',digits=3,scale=1):return f'{scale*r[field]:.{digits}f} [{scale*r[low]:.{digits}f}–{scale*r[high]:.{digits}f}]'
SPEC=json.loads((ROOT/'reference/tables.json').read_text())['tables']
SPECS={r['id']:r for r in SPEC}
def table_id(number):return 'Table '+number if number[0].isdigit() or number.startswith('C') else number
def original(number):
 item=SPECS[table_id(number)]
 text='\n'.join('| '+' | '.join(row)+' |' for row in [item['columns'],['---']*len(item['columns']),*item['rows']])
 return item['caption'],text

def table(number,rows):
 ident=table_id(number);item=SPECS[ident]
 assert rows==item['rows'],(ident,[(a,b) for a,b in zip(rows,item['rows']) if a!=b])
 result='\n'.join('| '+' | '.join(row)+' |' for row in [item['columns'],['---']*len(item['columns']),*rows])+'\n'
 (directory/(ident.replace(' ','_')+'.md')).write_text((item['caption']+'\n\n' if item['caption'] else '')+result)
 checks.append(dict(table=ident,rows=len(rows),all_cells_match=True,empirical=item['empirical']))

cs=load('section_6/class_earnings.csv');rows=[]
for net,name in NAMES.items():
 for cl in cs[cs.network_id.eq(net)].node_class.drop_duplicates():
  g=cs[cs.network_id.eq(net)&cs.node_class.eq(cl)]
  rows.append([name,label(cl),*[interval(one(g,knowledge=k),field='points_mean',low='points_mean_ci_low',high='points_mean_ci_high') for k in ['full_map','own_links']]])
# Network classes are displayed in the source's fixed A...H...Leaves order.
_,source=original('C1');order=[tuple(x.strip() for x in line.strip('|').split('|')[:2]) for line in source.splitlines()[2:]]
rows.sort(key=lambda r:order.index(tuple(r[:2])));table('C1',rows)
h2=load('section_6/h2_overall_both_windows.csv');rows=[]
for knowledge,title in [('full_map','Full map'),('own_links','Own links')]:
 for predictor,name in REFS.items():rows.append([title,name,*[interval(one(h2,knowledge=knowledge,predictor=predictor,window=w),field='rmse') for w in ['second_half','second_half_no_last']]])
table('C2',rows)
tests=load('section_6/hypothesis_summary.csv');effects=load('section_6/effect_intervals.csv');h1=load('section_6/h1_networks.csv');rows=[]
for h in ['H1','H3','H4','H5']:
 r=one(tests,window='primary',test=h);est=[]
 for w in ['primary','no_last']:
  est.append('Four constituent shares: Table C4' if h=='H1' else interval(one(effects,window=w,measure='H5_difference' if h=='H5' else h),field='estimate',scale=100 if h=='H3' else 1))
 rows.append([h,*est,str(int(r.n_episodes)),f'{r.p_value:.9f}',f'{r.p_adjusted:.9f}'])
table('C3',rows)
rows=[]
for net in ['line3','line5','star3','star4']:
 g=h1[h1.network_id.eq(net)];rows.append([NAMES[net],label(g.node_class.iloc[0]),*[interval(one(g,window=w),digits=2,scale=100) for w in ['primary','no_last']]])
table('C4',rows)
rows=[]
for net in ['line3','line4','line5','star3','star4','stem']:
 p=advantaged_class(net);rows.append([NAMES[net],label(p['node_class']),str(int(p['balanced']))])
table('C5',rows)
protocol=json.loads((OUT/'protocol_summary.json').read_text());replay=json.loads((OUT/'replay_verification.json').read_text())
rows=[['Completed episodes',f'{protocol["episodes"]} / 160'],['Episode replays matching the saved records',f'{replay["episodes"]} / 160'],['Invalid requested game actions',f'{protocol["requested_invalid_actions"]} / {protocol["asked_turns"]:,}'],['Rules quizzes scoring 3/3',f'{protocol["perfect_quizzes"]} / 600'],['Requested game decisions',f'{protocol["asked_turns"]:,}'],['Automatic passes without a model request',f'{protocol["automatic_passes"]:,}'],['Participant API attempts, including quizzes',f'{protocol["participant_api_attempts"]:,}'],['Participant API retries recorded',str(protocol['participant_retries'])]]
table('C6',rows)
pairs=load('section_6/pair_splits.csv');rows=[]
for k,labelk in [('full_map','Full map'),('own_links','Own links')]:
 r=one(pairs,knowledge=k,window='primary');rows.append([labelk,str(int(r.deals)),str(int(r.equal_deals)),str(int(r.unequal_deals))])
table('C7',rows)
triangle=load('appendices/individual/triangle_worked_example.csv');table('C8',[[r.node,f'{r.points_mean:.3f}'] for r in triangle.sort_values('node').itertuples()])
primary=h1[h1.window.eq('primary')].set_index('network_id')
h1_text='; '.join(name+f': {100*primary.loc[net,"mean"]:.2f}%' for net,name in [('line3','Three-node line B'),('line5','Five-node line B/D'),('star3','Three-leaf star H'),('star4','Four-leaf star H')])
rows=[['H1',h1_text,'Four separate intervals: Appendix C.2',f'{one(tests,window="primary",test="H1").p_adjusted:.6f}']]
for test,unit,scale in [('H3','percentage points per extra leaf',100),('H4','points per agent per round',1)]:
 e=one(effects,window='primary',measure=test);h=one(tests,window='primary',test=test)
 rows.append([test,f'{e.estimate*scale:.3f} {unit}',f'{e.ci_low*scale:.3f}–{e.ci_high*scale:.3f}',f'{h.p_adjusted:.6f}'])
table('2',rows)
# The restored question table specifies comparisons rather than empirical data.
spec=json.loads((ROOT/'data/protocol/hypotheses.json').read_text())
assert [x.strip() for x in original('1')[1].splitlines()[0].strip('|').split('|')]==spec['columns']
table('1',spec['rows'])
# Re-render the exact selected task stimuli and schemas using only offline helpers.
protocol_dir=OUT/'protocol';protocol_dir.mkdir(exist_ok=True)
names={'A':'Talin','B':'Orsa','C':'Pell','D':'Vash'}
for knowledge in ['full_map','own_links']:
 game=Episode(get_network('stem'),knowledge=knowledge,n_rounds=24,episode_seed=0,turn_order=lambda r,p:('B','A','C','D'))
 turn=game.next_turn();text=render_prompt(turn.observation,names)+'\n';f=f'early_{knowledge}.txt'
 assert text==(ROOT/'data/protocol'/f).read_text();(protocol_dir/f).write_text(text)
from late_prompt import capture_late
text=capture_late()+'\n'
assert text==(ROOT/'data/protocol/late_own_links.txt').read_text()
(protocol_dir/'late_own_links.txt').write_text(text)
text=render_quiz(get_network('stem'),'B',names,knowledge='full_map',n_rounds=24,episode_seed=0)+'\n'
assert text==(ROOT/'data/protocol/quiz_full_map.txt').read_text();(protocol_dir/'quiz_full_map.txt').write_text(text)
for name,value in [('action_schema.json',response_format()),('quiz_schema.json',quiz_response_format())]:
 assert value==json.loads((ROOT/'data/protocol'/name).read_text());(protocol_dir/name).write_text(json.dumps(value,indent=2)+'\n')
for config in ['minimum_study','own_links_arm']:
 c=load_config(PROJECT/'configs'/f'{config}.yaml');assert c.models['terra'].model_id=='gpt-6.1-terra'
 body=build_chat_kwargs(c.models['terra'],[{'role':'user','content':''}],response_format())
 settings={k:v for k,v in body.items() if k not in ['messages','response_format']}
 assert settings==json.loads((ROOT/'data/protocol/verified_specification.json').read_text())['configs'][config]['request_settings']
 (protocol_dir/(config+'_request_settings.json')).write_text(json.dumps(settings,indent=2)+'\n')
# Resolve every condition/seed from the unchanged YAML, independently of the
# saved specification, then compare the declared protocol and logged headers.
from dataclasses import asdict
from llm_network_bargaining.config import expand_conditions
from llm_network_bargaining.quiz import QUIZ_VERSION
from llm_network_bargaining.runlog import find_logs,read_log
from context import study_roots,NETWORKS
verified=json.loads((ROOT/'data/protocol/verified_specification.json').read_text())
conditions={}
configs={}
for config in ['minimum_study','own_links_arm']:
 c=load_config(PROJECT/'configs'/f'{config}.yaml');configs[config]=c
 resolved=[asdict(condition) for condition in expand_conditions(c)]
 for condition in resolved:condition['settings']=condition['settings'].model_dump() if hasattr(condition['settings'],'model_dump') else condition['settings']
 assert json.loads(json.dumps(resolved,default=lambda value:value.model_dump()))==verified['configs'][config]['conditions']
 assert c.source_sha256==verified['configs'][config]['config_sha256']
 conditions.update({r['key']:r for r in resolved})
headers=[]
for path in find_logs(study_roots()):
 header=read_log(path).header;condition=conditions[header['condition_key']]
 assert header['episode_seed']==condition['episode_seeds'][header['episode_index']]
 assert header['node_models']==condition['node_models']
 headers.append(dict(condition_key=header['condition_key'],episode_index=header['episode_index'],episode_seed=header['episode_seed']))
(protocol_dir/'verified_conditions.json').write_text(json.dumps(dict(conditions=list(conditions.values()),episodes=headers),indent=2,default=lambda value:value.model_dump())+'\n')
rows=[]
for net in NETWORKS:
 n=get_network(net);rows.append([NAMES[net]+', `'+net+'`',', '.join(n.nodes),', '.join('–'.join(e) for e in n.edges)])
table('B1_network_specification',rows)
setting_rows=[]
for config,c in configs.items():
 spec=c.models['terra'];body=build_chat_kwargs(spec,[{'role':'user','content':''}],response_format())
 assert spec.provider=='openai' and 'temperature' not in body and 'top_p' not in body and 'seed' not in body
 assert spec.prompt_cache=='off' and body['extra_body']['prompt_cache_options']['mode']=='explicit'
 assert body['store'] is False
 setting_rows.append([
 ['Provider and API interface','OpenAI, Chat Completions'],
 ['Requested model identifier','`'+body['model']+'`'],
 ['Requested reasoning effort','`'+json.dumps(body['reasoning_effort'])+'`'],
 ['Maximum completion tokens',str(body['max_completion_tokens'])],
 ['Temperature','Not supplied; no numerical value is imposed by the harness'],
 ['Other sampling controls','No `top_p` or model sampling seed is supplied'],
 ['Prompt cache setting','`'+spec.prompt_cache+'`; request uses explicit mode with no cache breakpoints'],
 ['Storage request','`store: '+json.dumps(body['store'])+'`'],
 ['Per-request timeout',f'{spec.timeout_s:g} seconds'],
 ['Decision-prompt version','`'+c.settings.prompt_version+'`'],
 ['Quiz version','`'+QUIZ_VERSION+'`']])
assert setting_rows[0]==setting_rows[1]
table('B3_request_settings',setting_rows[0])
from verification import worked_examples,write_json,evidence
worked=worked_examples()
table('D1_four_round_example',[[str(i),'–'.join(r[:2]),*[str(v) for v in r[2:]]] for i,r in enumerate(worked['four_round_sequence'],1)])
table('D2_link_contributions',[[ ' → '.join(r['order']),str(int(r['credit']['A–B'])),str(int(r['credit']['B–C']))] for r in worked['link_contributions']])
table('D4_episode_example',[[str(i),*[str(v) for v in row]] for i,row in enumerate(worked['episode_toy_rows'],1)])
write_json(OUT/'worked_examples.json',worked)
assert len(checks)==15 and sum(r['empirical'] for r in checks)==8
artifacts=evidence([*directory.glob('*.md'),*protocol_dir.iterdir(),* (ROOT/'data/protocol').iterdir(),OUT/'worked_examples.json',ROOT/'reference/tables.json',ROOT/'reference/claims.json',ROOT/'reproduction/tables.py',ROOT/'reproduction/late_prompt.py',ROOT/'reproduction/verification.py'])
write_json(OUT/'table_verification.json',dict(artifacts=artifacts,tables_total=15,empirical_tables=8,theoretical_anchor_tables=1,definition_tables=1,specification_and_teaching_tables=5,all_cells_match=True,tables=checks,exact_protocol_and_request_examples=8,conditions_and_header_seeds_verified=160,worked_examples_calculated=True))
print('All 15 tables, eight exact protocol/request examples and 160 condition/header seed checks reproduced',flush=True)
