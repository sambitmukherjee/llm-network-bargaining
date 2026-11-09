"""Print-size presentation of all five source maximum matchings; no model calls."""
from pathlib import Path
from itertools import combinations
import os,sys,json,hashlib
from context import ROOT,OUT,FIGURES

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
from llm_network_bargaining.networks import get_network

cases={'line3':[(('A','B'),),(('B','C'),)],'line5':[(('A','B'),('C','D')),(('A','B'),('D','E')),(('B','C'),('D','E'))]}
records=[]
fig=plt.figure(figsize=(6.5,2.3))
fig.text(.5,.95,'Three-node line: one deal per matching',ha='center',fontsize=10)
fig.text(.5,.52,'Five-node line: two deals per matching',ha='center',fontsize=10)
for name,sets in cases.items():
    net=get_network(name);nodes=list(net.nodes);edges=list(net.edges)
    allowed=[s for k in range(len(edges)+1) for s in combinations(edges,k) if len({v for e in s for v in e})==2*k]
    maximum=max(map(len,allowed));best={frozenset(s) for s in allowed if len(s)==maximum}
    assert best=={frozenset(s) for s in sets}
    for i,chosen in enumerate(sets):
        n=len(sets);x=(i+.08)/n;w=.84/n;y=.67 if name=='line3' else .24
        ax=fig.add_axes([x,y,w,.18]);pos={v:(j,0) for j,v in enumerate(nodes)}
        active={v for e in chosen for v in e};absent=sorted(set(nodes)-active)
        inactive=[e for e in edges if e not in chosen]
        if inactive:nx.draw_networkx_edges(net.graph(),pos,ax=ax,edgelist=inactive,edge_color='#9a9a9a',width=1,style='dashed')
        nx.draw_networkx_edges(net.graph(),pos,ax=ax,edgelist=chosen,edge_color='#0072B2',width=3)
        nx.draw_networkx_nodes(net.graph(),pos,ax=ax,nodelist=nodes,node_color=['#dceaf3' if v in active else 'white' for v in nodes],node_size=180,edgecolors='#222222',linewidths=.8)
        nx.draw_networkx_labels(net.graph(),pos,ax=ax,font_size=9)
        ax.set(xlim=(-.35,len(nodes)-.65),ylim=(-.35,.35));ax.axis('off')
        fig.text(x+w/2,y-.045,'Excluded: '+', '.join(absent),ha='center',fontsize=9)
        records.append(dict(network=name,matching=[list(e) for e in chosen],excluded=absent))
fig.legend(handles=[Line2D([],[],color='#0072B2',linewidth=3,label='Completed deal'),Line2D([],[],color='#9a9a9a',linestyle='--',linewidth=1,label='Available link without a completed deal')],loc='lower center',bbox_to_anchor=(.5,-.01),ncol=2,frameon=False,fontsize=8.5)
base=FIGURES/'figure_d1_maximum_matchings_print'
for ext in ['png','svg','pdf']:
    metadata={'Date':None} if ext=='svg' else {'CreationDate':None,'ModDate':None} if ext=='pdf' else {}
    fig.savefig(base.with_suffix('.'+ext),dpi=200,facecolor='white',metadata=metadata)
plt.close(fig)
report=dict(width_inches=6.5,height_inches=2.3,min_label_pt=8.5,matchings=records,source='sources/phase4/paper/build_appendix_g_figures.py:maximum_matching_panels',outputs={str(base.with_suffix('.'+e).relative_to(ROOT)):hashlib.sha256(base.with_suffix('.'+e).read_bytes()).hexdigest() for e in ['png','svg','pdf']})
(OUT/'figure_d1_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
