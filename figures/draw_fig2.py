
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,Polygon,FancyArrowPatch
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','pdf.fonttype':42})
out=Path('outputs');out.mkdir(exist_ok=True);fig,ax=plt.subplots(figsize=(7.2,7.65))
fig.subplots_adjust(0,0,1,1);ax.set(xlim=(0,12),ylim=(0,13));ax.axis('off')
ink='#19344B';blue='#EAF1F7';green='#EAF3EF';grey='#F4F5F6';accent='#226B80'
def box(x,y,w,h,title,body='',fill=blue,fs=9.3):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.04,rounding_size=0.10',lw=1.0,edgecolor=ink,facecolor=fill,zorder=3))
 if body:
  ax.text(x+w/2,y+h-.20,title,ha='center',va='top',fontsize=fs,fontweight='bold',color=ink,zorder=4)
  ax.text(x+w/2,y+h-.49,body,ha='center',va='top',fontsize=fs-.5,linespacing=1.32,color=ink,zorder=4)
 else:ax.text(x+w/2,y+h/2,title,ha='center',va='center',fontsize=fs,fontweight='bold',color=ink,zorder=4)
def arrow(points,color=ink,dashed=False):
 for a,b in zip(points[:-2],points[1:-1]):ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=1.0,ls='--' if dashed else '-',zorder=2)
 ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=10,lw=1.0,color=color,linestyle='--' if dashed else '-',zorder=2))
cx=7.15; x=3.7;w=6.9
box(x,11.9,w,.80,'1  Refresh measurements and build forecasts','Faults / switch states, load / PV, BESS SoC and voltages')
box(.45,9.35,2.75,2.00,'2  Lagged-flow scores','Eq. (9): previous P, Q\nfrom the released action\nOpen edge: P = Q = 0\nt = 0: pre-fault state',fill=grey,fs=9.0)
box(x,10.72,w,.80,'3  Generate GWO candidates','Switch states and BESS horizon set-points')
box(x,9.55,w,.80,'4a  DFS–MST radial repair','Apply lagged-flow edge scores; retain low-score edges')
box(x,8.38,w,.80,'4b  Source-admissibility and sufficiency check','Substation / GFM root; available P/Q and energy support')
box(x,7.21,w,.80,'4c  BESS reserve projection','Project set-points; propagate SoC and enforce reserve')
box(x,5.82,w,1.02,'5  Nonlinear screening and candidate ranking','Backward/forward sweep; voltage, current and BESS limits\nFeasibility-first ranking, then objective (1)')
box(x,4.29,w,1.10,'6  Branch-exchange refinement','If an admissible radial incumbent exists: up to 3 passes\nRe-evaluate each move using stages 4a–5',fill=green)
for top,bottom in [(11.9,11.52),(10.72,10.35),(9.55,9.18),(8.38,8.01),(7.21,6.84),(5.82,5.39)]:arrow([(cx,top),(cx,bottom)])
ax.text(cx+.13,5.59,'GWO stopping rule met',fontsize=8.3,color=ink,va='center')
# GWO loop on the right; refinement rechecks are explicitly stated within stage 6.
arrow([(10.6,6.32),(11.55,6.32),(11.55,11.12),(10.6,11.12)],accent,True)
ax.text(11.35,8.8,'Next GWO iteration',rotation=90,ha='center',va='center',fontsize=8.3,color=accent,backgroundcolor='white')
arrow([(3.2,9.95),(3.7,9.95)],accent)

arrow([(cx,12.70),(cx,12.90),(1.82,12.90),(1.82,11.35)],accent)
# Candidate release decision
ax.add_patch(Polygon([(cx,4.02),(9.25,3.46),(cx,2.90),(5.05,3.46)],closed=True,facecolor='white',edgecolor=ink,lw=1.0,zorder=3))
ax.text(cx,3.46,'7  Feasible plan available?',ha='center',va='center',fontsize=9.0,fontweight='bold',color=ink,zorder=4)
arrow([(cx,4.29),(cx,4.02)])
box(.45,2.60,3.00,1.62,'Deterministic fallback','Retain switch states;\nde-energize unrooted islands;\nshed regular load first;\nbook all deficits as ENS',fill=grey,fs=8.8)
arrow([(5.05,3.46),(3.45,3.46)]);ax.text(4.25,3.61,'No',fontsize=8.4,ha='center',color=ink)
box(x,1.70,w,.78,'Execute the first action only','Plant evaluation and full-epoch ENS accounting',fill=green)
arrow([(cx,2.90),(cx,2.48)]);ax.text(cx+.15,2.68,'Yes',fontsize=8.4,color=ink)
arrow([(1.95,2.60),(1.95,2.08),(3.7,2.08)])
box(x,.45,w,.87,'8  Update the released state; advance t','Topology, SoC and converged branch P/Q/voltages',fill=green)
arrow([(cx,1.70),(cx,1.32)])
# Updated released flows feed the next epoch, not a candidate's future solution.
arrow([(3.7,.89),(.16,.89),(.16,12.30),(3.7,12.30)],accent,True)
ax.text(.37,6.60,'Next epoch: released state and lagged flows',rotation=90,ha='center',va='center',fontsize=8.2,color=accent,backgroundcolor='white')
ax.text(6.0,.10,'Reported fixed-weight controller • ERB disabled',ha='center',fontsize=8,color='#52616D')
for ext in ['png','pdf','svg']:fig.savefig(out/('Fig2_SAGM_Workflow.'+ext),dpi=600,facecolor='white')
plt.close(fig)
print('Figure generated')
