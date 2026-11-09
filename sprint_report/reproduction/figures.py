"""Rebuild six figures and verify fresh numerical coordinates and structures.

Images are regenerated using Matplotlib's bundled fonts. Platform rendering
differences are not numerical failures; manuscript PNGs are never read.
"""
import contextlib,io,json,runpy,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from context import ROOT,OUT,FIGURES
from verification import equivalent,write_json,evidence

checks=[]
def check(name,value):
    checks.append(dict(check=name,passed=bool(value)))
    assert value,name

for script in ['main_figures.py','adapted/draw_knowledge.py','draw_matching.py','adapted/draw_outside_options.py','draw_networks.py']:
    plt.rcdefaults()
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(ROOT/'reproduction'/script),run_name='__main__')

expected=json.loads((ROOT/'reference/figure_values.json').read_text())
fresh={
    'primary_coordinates':json.loads((FIGURES/'coordinates.json').read_text()),
    'knowledge_difference_coordinates':json.loads((FIGURES/'figure_c1_coordinates.json').read_text()),
    'topologies':json.loads((FIGURES/'network_topologies.json').read_text()),
    'maximum_matchings':json.loads((OUT/'figure_d1_manifest.json').read_text())['matchings'],
    'outside_options':json.loads((FIGURES/'figure_d2_coordinates.json').read_text()),
}
for name,values in fresh.items():
    check(name+' numeric/structural values',equivalent(values,expected[name]))
dimensions=json.loads((FIGURES/'manifest.json').read_text())['dimensions']
check('Main figure physical dimensions retained',[(r['width_inches'],r['height_inches']) for r in dimensions]==[(6.5,6.15),(6.5,4.7)])
check('Main figure labels stay inside canvas',not any(r['text_outside_canvas'] for r in dimensions))
check('B1 labels stay inside canvas',not fresh['topologies']['text_outside_canvas'])
images=[]
for name in ['figure_1_completed_links','figure_2_earnings','figure_b1_networks','figure_c1_knowledge_differences','figure_d1_maximum_matchings_print','figure_d2_outside_options']:
    with Image.open(FIGURES/(name+'.png')) as image:
        pixels=np.asarray(image.convert('RGBA'));size=list(image.size)
    check(name+' valid nonempty image',min(size)>100 and np.ptp(pixels[:,:,:3].astype(float))>0)
    check(name+' SVG export exists',(FIGURES/(name+'.svg')).is_file())
    images.append(dict(figure=name,pixel_dimensions=size))
write_json(OUT/'figure_verification.json',dict(figures=6,all_numeric_checks_passed=True,
    checks=checks,images=images,primary_figure_coordinates=len(fresh['primary_coordinates']),
    rendering_policy='Numeric values and graph structures checked; no platform-dependent PNG identity requirement',
    artifacts=evidence([*[p for p in FIGURES.iterdir() if p.is_file()],OUT/'figure_d1_manifest.json',ROOT/'reference/figure_values.json',ROOT/'reproduction/figures.py',ROOT/'reproduction/verification.py',*[ROOT/'reproduction'/p for p in ['main_figures.py','adapted/draw_knowledge.py','draw_matching.py','adapted/draw_outside_options.py','draw_networks.py']]])))
print('All six figures regenerated; numerical coordinates, graph structures and image exports verified',flush=True)
