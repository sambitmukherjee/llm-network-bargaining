"""Recompute only retained sprint results from saved study logs; never call models."""
from pathlib import Path
from itertools import combinations,permutations,product
from functools import cache
from math import factorial,comb
from collections import Counter
import json,hashlib,csv
from io import StringIO
import numpy as np
import pandas as pd
import networkx as nx
from context import ROOT,PROJECT,OUT,DATA,CONFIGS,NETWORKS,study_roots
from llm_network_bargaining.analysis.data import load_dataset,outcome_rows
from llm_network_bargaining.analysis.metrics import condition_class_summary,episode_node_metrics,episode_class_metrics,power_use
from llm_network_bargaining.analysis.benchmarks import benchmark_errors,_class_data
from llm_network_bargaining.analysis.hypotheses import run_hypotheses
from llm_network_bargaining.analysis.predictions import class_predictions
from llm_network_bargaining.analysis.stats import json_ready
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.structure import max_deals
from llm_network_bargaining.seeds import derive_seed,make_rng
from llm_network_bargaining.runlog import find_logs,read_log
from llm_network_bargaining.theory import in_core

SEED,BOOT=1,2000
ELIGIBLE=['line3','line4','line5','star3','star4','stem'];H1_NETS=['line3','line5','star3','star4']
FOCI={'pair':'A|B','triangle':'A|B|C','line3':'B','line4':'B|C','line5':'B|D','star3':'H','star4':'H','stem':'B'}
LEAVES={'line3':2,'star3':3,'star4':4}
CHECKS=[];ARRAYS={};COMPARISONS=[]

def check(name,value,detail=None):
 CHECKS.append(dict(name=name,passed=bool(value),detail=detail))
 if not value:raise AssertionError((name,detail))

def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(json_ready(obj),indent=2,sort_keys=True,allow_nan=False)+'\n')

def save(name,frame):
 p=DATA/name;p.parent.mkdir(parents=True,exist_ok=True);frame.to_csv(p,index=False)

def compare(name,reference,actual,keys,fields=None,query=None):
 from verification import reference_frame
 frozen,keys=reference_frame(reference,keys)
 fields=[c for c in (fields or actual.columns) if c in frozen.columns]
 if query:frozen=frozen.query(query)
 cols=fields or [c for c in actual.columns if c in frozen.columns]
 a=actual[cols].sort_values(keys).reset_index(drop=True);b=frozen[cols].sort_values(keys).reset_index(drop=True)
 check(name+' row count',len(a)==len(b),(len(a),len(b)))
 maximum=0.
 for col in cols:
  if pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
   good=np.allclose(a[col],b[col],rtol=0,atol=1e-10,equal_nan=True)
   finite=np.isfinite(a[col])&np.isfinite(b[col]);diff=np.max(np.abs(a.loc[finite,col].to_numpy(dtype=float)-b.loc[finite,col].to_numpy(dtype=float))) if finite.any() else 0
   maximum=max(maximum,float(diff))
  else:good=a[col].astype(object).fillna('').astype(str).equals(b[col].astype(object).fillna('').astype(str))
  check(name+' '+col,good)
 COMPARISONS.append(dict(name=name,reference=reference,rows=len(a),columns=cols,unused_reference_columns=[c for c in frozen if c not in cols],maximum_absolute_difference=maximum))

# These five functions are verbatim copies, executed with this module's globals.
exec(compile((ROOT/'reproduction/adapted/statistical_helpers.py').read_text(),str(ROOT/'reproduction/adapted/statistical_helpers.py'),'exec'),globals())


def analyse():
 print('Loading the 160 study logs',flush=True)
 CHECKS.clear();ARRAYS.clear();COMPARISONS.clear()
 ds=load_dataset(study_roots(),configs=CONFIGS)
 check('Only 160 study episodes',len(ds.episodes)==160 and set(ds.episodes.config_name)==set(CONFIGS))
 rows=ds.node_rounds.merge(ds.episodes[['episode_uid','condition_key','episode_index']],on='episode_uid',validate='many_to_one')
 all_nodes=[];all_classes=[];all_summaries=[];rmse=[];h1=[];tests=[];effects=[];powers=[];differences=[];holm=[];nulls=[];h2draws={}
 for window,selector,start,end in [('primary','second_half',13,24),('no_last','second_half_no_last',13,23)]:
  print('Recomputing '+window+' estimates, exact/Monte Carlo tests and original bootstrap streams',flush=True)
  nodes,classes=independent_classes(rows,start,end)
  all_nodes.append(nodes.assign(window=window));all_classes.append(classes.assign(window=window))
  summary=condition_class_summary(ds,window=selector,n_boot=BOOT,seed=SEED)
  defined=nodes.groupby(['condition_key','node_class']).share_mean.count();defined_ep=classes.groupby(['condition_key','node_class']).share_mean.count()
  summary['defined_node_shares_across_episodes']=[int(defined.loc[(r.condition_key,r.node_class)]) for r in summary.itertuples()]
  summary['defined_episode_shares']=[int(defined_ep.loc[(r.condition_key,r.node_class)]) for r in summary.itertuples()]
  all_summaries.append(summary.assign(window=selector))
  for config,knowledge in [('minimum_study','full_map'),('own_links_arm','own_links')]:
   result=benchmark_errors(ds,config=config,window=selector,n_boot=BOOT,seed=SEED)
   groups=_class_data(ds,config,selector,BOOT,SEED)
   for g in groups:
    key=g['condition_key'];pivot=classes[classes.condition_key.eq(key)].pivot(index='episode_uid',columns='node_class',values='points_mean').sort_index(axis=1)
    indices=make_rng(derive_seed(SEED,'grouped_bootstrap',key)).integers(len(pivot),size=(BOOT,len(pivot)))
    tag=selector+'__'+key.replace('/','__');h2draws[tag+'__indices']=indices.astype(np.uint8);h2draws[tag+'__means']=pivot.to_numpy()[indices].mean(axis=1)
    defined_refs=[x for x in ['equal_split','myerson','position_value','balanced'] if g['predictions'][x].notna().all()]
    errors=np.stack([np.sqrt(np.mean((g['boot']-g['predictions'][x].to_numpy())**2,axis=1)) for x in defined_refs],axis=1)
    win=np.isclose(errors,errors.min(axis=1,keepdims=True),rtol=0,atol=1e-12);credits=(win/win.sum(axis=1,keepdims=True)).mean(axis=0)
    for i,ref in enumerate(defined_refs):
     item=next(r for r in result['per_network'] if r['network_id']==g['network_id'] and r['predictor']==ref)
     rmse.append(dict(window=selector,config_name=config,knowledge=knowledge,scope=g['network_id'],n_defined_bootstrap=BOOT,p_best=float(credits[i]),**{k:v for k,v in item.items() if k not in ['network_id','condition_key']}))
   for item in result['overall']:rmse.append(dict(window=selector,config_name=config,knowledge=knowledge,scope='overall',n_episodes=70,n_defined_bootstrap=BOOT,**item))
  canonical=run_hypotheses(ds,window=selector,n_boot=BOOT,seed=SEED).to_dict()
  dump(OUT/f'hypotheses_{window}.json',canonical)
  pui=power_use(ds,selector).sort_values(['network_id','episode_uid']).reset_index(drop=True)
  a,_=audit_nulls(classes,pui,canonical,window);nulls.extend(a)
  for net,item in canonical['h1_per_network'].items():h1.append(dict(window=window,network_id=net,node_class=FOCI[net],**item))
  for test in ['H1','H3','H4','H5']:
   v=canonical['results'][test];tests.append(dict(window=window,test=test,**{k:v[k] for k in ['statistic','p_value','p_adjusted','decision','method']},n_episodes=40 if test=='H1' else v['n'],n_resamples=1024 if test=='H1' else v['n_resamples']))
  families={'main':{h:canonical['results'][h]['p_value'] for h in ['H1','H3','H4','H5']},'H1_networks':{n:v['p_value'] for n,v in canonical['h1_per_network'].items()}}
  for family,values in families.items():
   running=0
   for rank,(test,p) in enumerate(sorted(values.items(),key=lambda x:(x[1],x[0]))):
    multiplier=len(values)-rank;product_value=multiplier*p;running=max(running,product_value)
    holm.append(dict(window=window,family=family,test=test,rank=rank+1,p_value=p,multiplier=multiplier,product=product_value,p_adjusted=min(1.,running)))
  full=[];own=[]
  for net in ELIGIBLE:
   v=canonical['results']['H5']['per_network'][net];balanced=float(pui[pui.network_id.eq(net)].balanced.iloc[0])
   for knowledge,destination in [('full_map',full),('own_links',own)]:
    powers.append(dict(window=window,network_id=net,node_class=FOCI[net],balanced=balanced,knowledge=knowledge,**v[knowledge]))
    vals=pui[pui.network_id.eq(net)&pui.knowledge.eq(knowledge)].sort_values('episode_uid').pui.to_numpy();destination.append(resample(vals,window,'H5_overall',net,knowledge))
   differences.append(dict(window=window,network_id=net,difference=v['difference'],ci_low=v['ci_low'],ci_high=v['ci_high'],n_full=v['n_b'],n_own=v['n_a'],points_difference=v['difference']*(balanced-12)))
  full=np.array(full).mean(axis=0);own=np.array(own).mean(axis=0)
  for name,draws in [('full_map',full),('own_links',own),('difference',full-own)]:
   ARRAYS[f'{window}_H5_boot_{name}']=draws
   point=canonical['results']['H5']['statistic'] if name=='difference' else np.mean([v[name]['mean'] for v in canonical['results']['H5']['per_network'].values()])
   effects.append(dict(window=window,measure='H5_'+name,estimate=point,**ci(draws)))
  for test,nets,clss,metric in [('H3',['line3','star3','star4'],['B','H','H'],'share_mean'),('H4',['line4','line5'],['A|D','A|E'],'points_mean')]:
   boot=[];means=[]
   for net,cl in zip(nets,clss):
    values=classes[classes.network_id.eq(net)&classes.knowledge.eq('full_map')&classes.node_class.eq(cl)].sort_values('episode_uid')[metric].to_numpy()
    means.append(values.mean());boot.append(resample(values,window,test,net))
   draws=(boot[2]-boot[0])/2 if test=='H3' else boot[0]-boot[1];point=(means[2]-means[0])/2 if test=='H3' else means[0]-means[1]
   ARRAYS[f'{window}_{test}_bootstrap']=draws;effects.append(dict(window=window,measure=test,estimate=point,**ci(draws)))
 summaries=pd.concat(all_summaries,ignore_index=True);classes=pd.concat(all_classes,ignore_index=True);nodes=pd.concat(all_nodes,ignore_index=True)
 primary=summaries.query("window=='second_half'").copy()
 save('section_6/class_earnings.csv',primary)
 compare('C1 class earnings','section_6/class_earnings.csv',primary,['condition_key','node_class'])
 earn=primary.query("knowledge=='full_map' and network_id not in ['pair','triangle']").drop(columns='window').copy()
 for i,r in earn.iterrows():
  n=nodes[nodes.window.eq('primary')&nodes.condition_key.eq(r.condition_key)&nodes.node_class.eq(r.node_class)]
  counts=n.groupby('episode_uid').share_mean.count()
  for field,value in dict(defined_node_episode_shares=int(n.share_mean.count()),possible_node_episode_shares=len(n),min_defined_members_per_episode=int(counts.min()),max_defined_members_per_episode=int(counts.max()),product_of_separate_means=24*r.deal_rate*r.share_mean).items():earn.loc[i,field]=value
 save('section_6/main_earnings_summary.csv',earn)
 ep=episode_class_metrics(ds,'second_half').query("knowledge=='full_map' and network_id not in ['pair','triangle']").assign(window='second_half')
 save('section_6/main_earnings_episodes.csv',ep)
 rmse=pd.DataFrame(rmse);primary_rmse=rmse.query("window=='second_half'")
 save('section_6/rmse.csv',primary_rmse);compare('Primary benchmark RMSE','section_6/rmse.csv',primary_rmse,['config_name','scope','predictor'])
 overall=rmse.query("scope=='overall'");save('section_6/h2_overall_both_windows.csv',overall);compare('C2 both-window H2','section_6/h2_overall_both_windows.csv',overall,['window','config_name','predictor'])
 for name,records,reference,keys in [
  ('hypothesis_summary',tests,'section_6/hypothesis_summary.csv',['window','test']),('h1_networks',h1,'section_6/h1_networks.csv',['window','network_id']),('effect_intervals',effects,'section_6/effect_intervals.csv',['window','measure']),
  ('null_audit',nulls,'appendices/statistics/null_audit.csv',['window','test']),('holm_steps',holm,'appendices/statistics/holm_steps.csv',['window','family','test']),
  ('power_use_summary',powers,'appendices/knowledge/power_use_summary.csv',['window','network_id','knowledge']),('power_use_differences',differences,'appendices/knowledge/power_use_differences.csv',['window','network_id'])]:
  frame=pd.DataFrame(records);save(reference,frame);compare(name,reference,frame,keys)
 # Draw arrays are generated afresh, never read as runtime inputs. The
 # manifests support the migration audit; acceptance uses compact results and
 # exact null-tail checks, allowing documented floating-point tolerance.
 streams={}
 for filename,fresh in [('h2_bootstrap.npz',h2draws),('null_and_effect_draws.npz',ARRAYS)]:
  streams[filename]={key:dict(shape=list(value.shape),dtype=str(value.dtype),sha256=hashlib.sha256(value.tobytes()).hexdigest()) for key,value in fresh.items()}
  np.savez_compressed(OUT/filename,**fresh)
 dump(OUT/'draw_streams.json',streams)
 links=[];refs=[];rounds=[];eff=[];ineff=[];pair=[]
 meta=ds.episodes.set_index('episode_uid');deals=ds.deals.merge(ds.episodes[['episode_uid','condition_key','config_name','network_id','knowledge','episode_index']],on='episode_uid',validate='many_to_one')
 for net in NETWORKS:
  network=get_network(net);myerson,position,equal,_=independent_theory(net);pred=class_predictions(net)
  for r in pred.itertuples():
   for field,values in [('myerson',myerson),('position_value',position),('equal_split',equal)]:check('Independent theory '+net+'/'+r.node_class+'/'+field,np.isclose(getattr(r,field),np.mean([values[n] for n in r.node_class.split('|')]),rtol=0,atol=1e-10))
  matching=[m for m in combinations(network.edges,max_deals(network)) if len({n for e in m for n in e})==2*len(m)]
  for a,b in network.edges:
   frequencies=[int((a,b) in m) for m in matching]
   refs.append(dict(network_id=net,edge=a+'–'+b,a=a,b=b,frequency_reference=np.mean(frequencies),efficient_frequency_min=min(frequencies),efficient_frequency_max=max(frequencies)))
  for arm in ['full_map','own_links']:
   subset=deals[deals.network_id.eq(net)&deals.knowledge.eq(arm)&deals['round'].between(13,24)]
   for a,b in network.edges:
    count=sum(set((r.maker,r.recipient))==set((a,b)) for r in subset.itertuples())
    condition=ds.episodes[ds.episodes.network_id.eq(net)&ds.episodes.knowledge.eq(arm)].condition_key.iloc[0]
    links.append(dict(condition_key=condition,network_id=net,knowledge=arm,edge=a+'–'+b,window='primary',n_episodes=10,deal_frequency=count/120,deals=count,network_rounds=120))
 for episode,context in meta.iterrows():
  sub=deals[deals.episode_uid.eq(episode)];maximum=max_deals(get_network(context.network_id))
  for r in range(1,25):
   n=len(sub[sub['round'].eq(r)]);rounds.append(dict(episode_uid=episode,network_id=context.network_id,knowledge=context.knowledge,episode_index=context.episode_index,round=r,deals=n,maximum_deals=maximum,efficient=n==maximum))
   if n<maximum:ineff.append(dict(episode_uid=episode,network_id=context.network_id,knowledge=context.knowledge,episode_index=context.episode_index,round=r,deals=n,maximum_deals=maximum,points=24*n,primary_window=13<=r<=24,sensitivity_window=13<=r<=23))
 rounds=pd.DataFrame(rounds)
 for w,start,end in [('all',1,24),('primary',13,24),('no_last',13,23)]:
  sub=rounds[rounds['round'].between(start,end)]
  eff.append(dict(window=w,n_network_rounds=len(sub),n_efficient_rounds=int(sub.efficient.sum()),n_inefficient_rounds=int((~sub.efficient).sum()),n_deals=int(sub.deals.sum()),maximum_deals=int(sub.maximum_deals.sum())))
  for arm in ['full_map','own_links']:
   d=deals[deals.network_id.eq('pair')&deals.knowledge.eq(arm)&deals['round'].between(start,end)]
   pair.append(dict(window=w,knowledge=arm,deals=len(d),equal_deals=int(d.maker_points.eq(12).sum()),unequal_deals=int(d.maker_points.eq(13).sum()),mean_maker_share=(d.maker_points/24).mean()))
 for reference,frame,keys,query in [
  ('completed_links/edge_summary.csv',pd.DataFrame(links),['network_id','knowledge','edge'],"window=='primary'"),('completed_links/edge_references.csv',pd.DataFrame(refs),['network_id','edge'],None),
  ('section_6/efficiency_counts.csv',pd.DataFrame(eff),['window'],None),('section_6/pair_splits.csv',pd.DataFrame(pair),['window','knowledge'],None),('appendices/health/inefficient_rounds.csv',pd.DataFrame(ineff),['episode_uid','round'],None)]:
  save(reference,frame)
  if not reference.startswith('completed_links/'):
   compare(reference,reference,frame,keys,query=query)
 # Individual histories and accepted-offer authors need no note coding.
 history=pd.concat([episode_node_metrics(ds,selector).assign(window=w) for w,selector in [('primary','second_half'),('all','all')]],ignore_index=True)
 save('appendices/individual/episode_nodes.csv',history)
 triangle=history.query("window=='primary' and network_id=='triangle' and knowledge=='own_links' and episode_index==5").sort_values('node').copy();triangle['total_points']=np.rint(triangle.points_mean*12).astype(int)
 save('appendices/individual/triangle_worked_example.csv',triangle);compare('Actual triangle example','appendices/individual/triangle_worked_example.csv',triangle,['node'])
 deals=deals.rename(columns={'phase':'acceptance_phase'})
 save('appendices/individual/deal_offers.csv',deals)
 never=history.query("window=='primary' and n_deals==0")
 check('Eight late no-deal cases are star leaves',len(never)==8 and never.node.str.startswith('L').all())
 check('All 600 agents trade somewhere in full episodes',history.query("window=='all'").n_deals.gt(0).all())
 star=deals.query("network_id=='star4' and knowledge=='full_map' and round>=13")
 check('94/120 star deals accepted from leaf-made offers',len(star)==120 and star.maker.str.startswith('L').sum()==94)
 # Fixed theoretical allocations are also checked independently of their display file.
 theoretical=[];names={'pair':'Pair','line3':'Three-node line','line4':'Four-node line','line5':'Five-node line','star3':'Three-leaf star','star4':'Four-leaf star','stem':'Stem','triangle':'Triangle'}
 for net in NETWORKS:
  for r in class_predictions(net).itertuples():
   cl='Leaves '+r.node_class.replace('|','–',1).split('–')[0]+'–'+r.node_class.split('|')[-1] if r.node_class.startswith('L1') else r.node_class.replace('|',', ')
   theoretical.append({'Network':names[net],'Node class':cl,'Equal-split earnings reference':r.equal_split,'Myerson value':r.myerson,'Position value':r.position_value,'Balanced outcome reference':'Undefined' if pd.isna(r.balanced) else str(float(r.balanced)).removesuffix('.0')})
 theory=pd.DataFrame(theoretical);save('appendices/theoretical_allocations.csv',theory)
 compare('All fixed theoretical allocations','appendices/theoretical_allocations.csv',theory,['Network','Node class'])
 protocol(ds,history,rounds)
 from verification import evidence
 artifacts=evidence([*DATA.rglob('*.csv'),*[OUT/name for name in ['hypotheses_primary.json','hypotheses_no_last.json','draw_streams.json','h2_bootstrap.npz','null_and_effect_draws.npz','protocol_summary.json']],ROOT/'reference/claims.json',ROOT/'reproduction/selected_analysis.py',ROOT/'reproduction/adapted/statistical_helpers.py'])
 dump(OUT/'analysis_verification.json',dict(artifacts=artifacts,passed=sum(r['passed'] for r in CHECKS),total=len(CHECKS),checks=CHECKS,comparisons=COMPARISONS,bootstrap_repetitions=BOOT,analysis_root_seed=SEED,new_model_calls=False))
 print('Selected analyses reproduced; '+str(len(CHECKS))+' checks passed',flush=True)

def protocol(ds,history,rounds):
 attempts=[];models=Counter();headers=[]
 for path in find_logs(study_roots()):
  records=read_log(path);h=records.header
  if h.get('config_name') not in CONFIGS:continue
  headers.append(h)
  for row in records.quizzes+[e for e in records.events if e['type']=='turn' and not e['auto']]:
   models[str(row['meta'].get('returned_model'))]+=1
   attempts.extend(dict(a,config_name=h['config_name']) for a in row['meta']['attempts'])
 coverage=ds.episodes.groupby(['config_name','network_id','knowledge'],as_index=False).agg(episodes=('episode_uid','size'),rounds_per_episode=('n_rounds','first'),nodes_per_episode=('n_nodes','first'))
 coverage['planned_episodes']=10;save('appendices/health/coverage.csv',coverage)
 check('All episodes completed on their first attempt',ds.episodes.attempt.eq(1).all())
 check('All 600 rules quizzes score 3/3',len(ds.quizzes)==600 and ds.quizzes.score.eq(3).all())
 check('No invalid requested actions',ds.turns.loc[~ds.turns.auto,'valid'].all())
 check('All 17601 participant replies identify requested model',models=={'gpt-6.1-terra':17601})
 check('Exactly 17001 requested and 8503 automatic game turns',int((~ds.turns.auto).sum())==17001 and int(ds.turns.auto.sum())==8503)
 check('Exactly one successful attempt per participant request',len(attempts)==17601 and all(a['outcome']=='ok' for a in attempts))
 check('All 16 planned conditions completed',len(coverage)==16 and coverage.episodes.eq(10).all() and coverage.rounds_per_episode.eq(24).all())
 result=dict(episodes=len(ds.episodes),conditions=len(coverage),asked_turns=int((~ds.turns.auto).sum()),automatic_passes=int(ds.turns.auto.sum()),quizzes=len(ds.quizzes),perfect_quizzes=int(ds.quizzes.score.eq(3).sum()),requested_invalid_actions=int((~ds.turns.loc[~ds.turns.auto,'valid']).sum()),returned_models=dict(models),participant_api_attempts=len(attempts),participant_retries=len(attempts)-len(ds.quizzes)-int((~ds.turns.auto).sum()),header_commits=sorted({h['git_commit'] for h in headers}),new_model_calls=False)
 dump(OUT/'protocol_summary.json',result)

if __name__=='__main__':analyse()
