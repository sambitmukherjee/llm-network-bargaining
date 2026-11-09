from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import networkx as nx
from context import ROOT,DATA,FIGURES as OUT
from llm_network_bargaining.networks import get_network

NETS=['line3','line4','line5','star3','star4','stem']
ALL=['pair',*NETS,'triangle']
NAMES=dict(zip(ALL,['Pair','Three-node line','Four-node line','Five-node line','Three-leaf star','Four-leaf star','Stem','Triangle']))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'axes.titlesize':9,
    'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,
    'axes.spines.top':False,'axes.spines.right':False,'axes.axisbelow':True,
    'svg.hashsalt':'appendix-c-phase2','figure.facecolor':'white'})
outputs=[]
diff=pd.read_csv(DATA/'appendices/knowledge/power_use_differences.csv').query("window=='primary'")
effects=pd.read_csv(DATA/'section_6/effect_intervals.csv').query("window=='primary'")
def save(fig,name):
    for extension in ['png','svg']:
        p=OUT/(name+'.'+extension)
        fig.savefig(p,dpi=300,bbox_inches='tight',metadata={'Software':None} if extension=='png' else {'Creator':None,'Date':None})
        outputs.append(p)
    plt.close(fig)

def interval(ax,x,r,c,m,horizontal=False):
    if horizontal:
        ax.errorbar(r['mean'],x,xerr=[[r['mean']-r['ci_low']],[r['ci_high']-r['mean']]],fmt=m,color=c,capsize=2,ms=3.5,lw=1,zorder=5)
    else:
        ax.errorbar(x,r['mean'],yerr=[[r['mean']-r['ci_low']],[r['ci_high']-r['mean']]],fmt=m,color=c,capsize=2,ms=3.5,lw=1,zorder=5)

def differences():
    fig,ax=plt.subplots(figsize=(7.2,3.7))
    for i,net in enumerate(NETS):
        r=diff[diff.network_id.eq(net)].iloc[0]
        interval(ax,i,{'mean':r.difference,'ci_low':r.ci_low,'ci_high':r.ci_high},'#242424','o',True)
    r=effects[effects.measure.eq('H5_difference')].iloc[0]
    interval(ax,7,{'mean':r.estimate,'ci_low':r.ci_low,'ci_high':r.ci_high},'#0072B2','D',True)
    ax.axvline(0,color='#777777',ls='--',lw=.8);ax.axhline(6,color='#cccccc',lw=.7)
    ax.set(title='Full map minus own links: differences in mean power-use index',
        yticks=list(range(6))+[7],yticklabels=[NAMES[n] for n in NETS]+['Average difference\nacross the six networks'],ylim=(8,-.8),
        xlim=(-.11,.36),xlabel='Difference in mean power-use index')
    ax.grid(axis='x',color='#dddddd',lw=.5)
    fig.subplots_adjust(left=.31,right=.98,bottom=.17,top=.87)
    save(fig,'appendix_c6_knowledge_differences')

if __name__=='__main__':
 differences()
 for ext in ['png','svg']:(OUT/('appendix_c6_knowledge_differences.'+ext)).replace(OUT/('figure_c1_knowledge_differences.'+ext))
 records=diff.to_dict('records')+effects[effects.measure.eq('H5_difference')].to_dict('records')
 (OUT/'figure_c1_coordinates.json').write_text(json.dumps(records,indent=2)+'\n')
