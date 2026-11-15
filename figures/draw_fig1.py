"""Reproducible Fig. 1 architecture (PNG, PDF and editable SVG)."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
# Liberation Sans (metric-compatible with Arial) matches Fig. 2; DejaVu Sans is the fallback.
FONT='Liberation Sans' if any('Liberation Sans' in f.name for f in font_manager.fontManager.ttflist) else 'DejaVu Sans'
plt.rcParams.update({'font.family':FONT,'svg.fonttype':'none','pdf.fonttype':42})
fig,ax=plt.subplots(figsize=(8,2.9));fig.subplots_adjust(0,0,1,1)
ax.set(xlim=(0,100),ylim=(0,42));ax.axis('off')
navy='#1f3a56';teal='#32666f';light='#f1f5f7'
CHECKS=[]  # (text, box x0, x1, y0, y1) for the overflow check
def box(x,y,w,h,title,body,header=5):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.1,rounding_size=0.7',fc='white',ec=navy,lw=1))
 t1=ax.text(x+w/2,y+h-2.5,title,ha='center',va='center',fontsize=10.2,weight='bold',color=navy)
 ax.plot([x+1,x+w-1],[y+h-header,y+h-header],color=teal,lw=1)
 t2=ax.text(x+w/2,y+(h-header)/2,body,ha='center',va='center',fontsize=9.2,color=navy,linespacing=1.35)
 CHECKS.extend([(t1,x,x+w,y,y+h),(t2,x,x+w,y,y+h-header)])
def arrow(points):
 xs,ys=zip(*points);ax.plot(xs,ys,color=navy,lw=1.2,zorder=0)
 ax.annotate('',xy=points[-1],xytext=points[-2],arrowprops=dict(arrowstyle='-|>',color=navy,lw=1.2,shrinkA=0,shrinkB=0))
ax.add_patch(FancyBboxPatch((22,10),56,30,boxstyle='round,pad=0.1,rounding_size=0.8',fc=light,ec=navy,lw=1,zorder=-2))
ax.text(50,37.5,'Rolling-horizon restoration controller',ha='center',va='center',fontsize=12,weight='bold',color=navy)
box(1,14,18,22,'Inputs','Faults and switches\nVoltages and SoC\nLoad / DER forecasts')
box(24,18,16,16,'Formulation','Current state\nFixed weights\nTerminal reserve')
box(43,18,16,16,'SAGM-GWO','Candidate search\nGraph repair\nReserve projection\nBranch exchange')
box(62,18,14,16,'AC screening','BFS power flow\nSource checks\nVoltage / current\nEnergy limits')
box(81,23,18,14.5,'Release action','Recheck AC state\nExecute first action\nFallback if required')
box(81,9,18,11,'Network','Load / DER response\nVoltages and SoC')
arrow([(19,26),(24,26)]);arrow([(40,26),(43,26)]);arrow([(59,26),(62,26)])
arrow([(76,26),(79,26),(79,30),(81,30)])
arrow([(90,23),(90,20)])
arrow([(69,18),(69,16),(51,16),(51,18)])
ax.text(62,15.9,' Candidate evaluation ',ha='center',va='center',fontsize=8.5,color=navy,bbox=dict(fc=light,ec='none',pad=.3))
ax.text(50,12.5,'Released-state P/Q → lagged-flow scoring, Eq. (9)',ha='center',va='center',fontsize=9,color=navy)
arrow([(81,14),(79,14),(79,12.5),(75,12.5)])
arrow([(27,12.5),(21,12.5),(21,35),(51,35),(51,34)])
arrow([(90,9),(90,5),(10,5),(10,14)])
ax.text(50,5,' Refresh measurements and SoC; advance the horizon ',ha='center',va='center',fontsize=10,weight='bold',color=navy,bbox=dict(fc='white',ec='none',pad=2))
ax.text(50,1.5,'Only the first action is executed; the remaining horizon is replanned.',ha='center',va='center',fontsize=9,color=navy)
# Overflow check: every box text keeps a small margin inside its box.
fig.canvas.draw();rend=fig.canvas.get_renderer();inv=ax.transData.inverted();bad=[]
for t,x0,x1,y0,y1 in CHECKS:
 (bx0,by0),(bx1,by1)=inv.transform(t.get_window_extent(rend).get_points())
 if not (bx0>=x0+0.6 and bx1<=x1-0.6 and by0>=y0+0.3 and by1<=y1-0.3): bad.append((t.get_text().replace(chr(10),' / '),round(bx0,2),round(bx1,2),(x0,x1)))
assert not bad,'text overflow: '+repr(bad)
# Outputs use the repository root irrespective of the caller's working directory.
out=Path(__file__).resolve().parents[1]/'outputs';out.mkdir(exist_ok=True)
for ext in ('png','pdf','svg'):fig.savefig(out/f'Fig1_RH_Architecture.{ext}',dpi=600,facecolor='white')
print('Saved Fig. 1')
