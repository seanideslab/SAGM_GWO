from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];O=R/'figures'
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
cs=['#425c76','#b47a2b','#16857d'];cfg=['Snapshot-Lean','RH-Lean Tp=1','RH-Lean'];lab=['Snapshot-SAGM','RH ($T_p=1$)','Full RH ($T_p=5$)']
f,aa=plt.subplots(3,1,figsize=(6.4,7.1),sharex=True,layout='constrained');rows=[]
for c,l,col in zip(cfg,lab,cs):
 ds=[pd.read_csv(R/'runs_r2/main'/c.replace(' ','_')/f'seed_{s:02d}.csv') for s in range(1,31)]
 e=np.array([x.ens_kwh for x in ds]);soc=np.array([x.soc_mean for x in ds])*100
 for i,a in enumerate([e,soc,e.cumsum(1)]):
  m=a.mean(0);sd=a.std(0,ddof=1);aa[i].plot(range(24),m,label=l,color=col,lw=1.8)
  if i==2:aa[i].fill_between(range(24),np.maximum(0,m-sd),m+sd,color=col,alpha=.15)
  rows.extend(dict(config=c,panel=i,t=t,mean=m[t],sd=sd[t]) for t in range(24))
for a,title,y in zip(aa,['(a) Hourly unserved energy','(b) Aggregate BESS state of charge','(c) Cumulative unserved energy'],['ENS (kWh)','SoC (%)','ENS (kWh)']):
 a.set_title(title,loc='left');a.set_ylabel(y);a.grid(alpha=.15);a.set_xlim(-.3,23.3)
 for t in [0,2,3,4,6]:a.axvline(t,color='#888888',lw=.6,ls=':')
for t,n,y in [(0,'F1',.97),(2,'D1',.97),(3,'R1',.84),(4,'F2',.97),(6,'D2',.97)]:aa[0].text(t+.1,y,n,transform=aa[0].get_xaxis_transform(),fontsize=8,va='top')
aa[0].legend(fontsize=8,frameon=False);aa[1].axhline(20,color='gray',ls='--');aa[1].text(22.9,21,'20% reserve',ha='right',fontsize=8)
aa[-1].set_xticks([0,4,8,12,16,20,23],['08:00','12:00','16:00','20:00','00:00','04:00','07:00']);aa[-1].set_xlabel('Time of day')
for ext in ['png','pdf','svg']:f.savefig(O/f'Fig3_Trajectories.{ext}',dpi=320)
pd.DataFrame(rows).to_csv(O/'Fig3_source.csv',index=False);plt.close(f)
d=pd.read_csv(R/'results_r2/machine_main_runs.csv');f,aa=plt.subplots(1,2,figsize=(7.2,3.4),layout='constrained');rows=[]
for s,hs,col in [('main',[1,2,3,5,7,10],cs[2]),('storage_rich',[1,3,5],cs[0])]:
 m=[];sd=[]
 for h in hs:
  c='RH-Lean' if h==5 else f'RH-Lean Tp={h}';v=d[(d.scenario==s)&(d.configuration==c)].cum_ens_kwh;m.append(v.mean());sd.append(v.std());rows.append(dict(panel='a',scenario=s,config=c,x=h,mean=v.mean(),sd=v.std()))
 aa[0].errorbar(hs,m,yerr=sd,marker='o',capsize=3,color=col,label='Main case' if s=='main' else 'Storage-rich')
for ns,cs2,col,label in [([0,5,10,15,25],['RH-Lean noise0','RH-Lean noise5','RH-Lean','RH-Lean noise15','RH-Lean noise25'],cs[2],'White'),([10,25],['RH-Lean AR1 noise10','RH-Lean AR1 noise25'],cs[0],'AR(1), ρ=0.8')]:
 m=[];sd=[]
 for n,c in zip(ns,cs2):
  v=d[(d.scenario=='main')&(d.configuration==c)].cum_ens_kwh;m.append(v.mean());sd.append(v.std());rows.append(dict(panel='b',scenario='main',config=c,x=n,mean=v.mean(),sd=v.std()))
 aa[1].errorbar(ns,m,yerr=sd,marker='o',capsize=3,color=col,label=label)
for x,c,l,col in [(9,'RH-Lean Bias-10%','−10% bias','#886ca9'),(11,'RH-Lean Bias+10%','+10% bias',cs[1])]:
 v=d[(d.scenario=='main')&(d.configuration==c)].cum_ens_kwh;aa[1].errorbar([x],[v.mean()],yerr=[v.std()],marker='D',capsize=3,color=col,label=l);rows.append(dict(panel='b',scenario='main',config=c,x=10,mean=v.mean(),sd=v.std()))
aa[0].set(title='(a) Prediction horizon',xlabel='$T_p$ (h)',ylabel='Cumulative ENS (kWh)');aa[0].set_xticks([1,2,3,5,7,10]);aa[0].legend(fontsize=8,loc='lower right',frameon=False)
aa[1].set(title='(b) Forecast perturbation',xlabel='Approximate 95% error band (±%)',ylabel='Cumulative ENS (kWh)',ylim=(1850,2750));aa[1].set_xticks([0,5,10,15,25]);aa[1].legend(fontsize=7,loc='upper center',ncol=2,frameon=False)
for a in aa:a.grid(alpha=.15)
for ext in ['png','pdf','svg']:f.savefig(O/f'Fig4_Sensitivity.{ext}',dpi=320)
pd.DataFrame(rows).to_csv(O/'Fig4_source.csv',index=False)
