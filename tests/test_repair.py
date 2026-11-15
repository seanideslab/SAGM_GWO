"""Regression tests for reserve projection and the final release gate."""
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim import core
from sim.evaluator import Evaluator
from sim.network import load_net
from sim.optimizer import rank_value

def test_charging_reaches_reserve():
    n=load_net(ROOT/'config/ieee33_main.json');ev=Evaluator(n)
    m=ev(n.init_state,np.zeros((n.bess_bus.size,1)),np.zeros(n.nl),True,n.init_state,
         np.ones(n.nl,bool),np.zeros((1,n.nb)),np.zeros((1,n.nb)),np.zeros((1,n.nb)),
         np.full(n.bess_bus.size,.15),dg_on=False).copy()
    np.testing.assert_allclose(ev.out_soc1,.20,atol=1e-12)
    assert m[core.M_TERM] < 1e-6 and m[core.M_RESERVE_STEP]==0
    assert rank_value(1.,m)==1.

def test_projection_energy_identity():
    for eta in (.8,.95,1.):
        for dt in (.25,1.,2.):
            for energy in (30.,40.,60.):
                p=core.reserve_power_ceiling(energy,40.,eta,dt)
                e1=energy-p/eta*dt if p>=0 else energy-p*eta*dt
                assert abs(e1-40.)<1e-10

def test_residuals_are_rejected():
    for index in (core.M_FINAL_NONCONV,core.M_VVIOL,core.M_OVERLOAD,core.M_SOCVIOL,
                  core.M_BESSVIOL,core.M_RESERVE_STEP,core.M_TERM,core.M_STRUCT_INF):
        m=np.zeros(core.N_METRICS);m[index]=1
        assert rank_value(1.,m)>=1e6
    m=np.zeros(core.N_METRICS);m[core.M_NONCONV]=3
    assert rank_value(1.,m)==1.
    m[core.M_VMAX]=np.nan
    assert rank_value(1.,m)>=1e6

def test_capture_replaces_fallback_trial():
    from unittest.mock import patch
    from threephase import CaptureEpisode
    from sim.controller import Episode, Variant
    from sim.network import build_truth
    n=load_net(ROOT/'config/ieee33_main.json')
    ep=CaptureEpisode(n,build_truth(n),Variant('test'),1);ep.cap=[]
    out={'closed':n.init_state,'served':np.ones(n.nb),'V':np.ones(n.nb)}
    with patch.object(Episode,'plant',return_value=(np.zeros(core.N_METRICS),out)):
        ep.plant(n.init_state,np.zeros(n.bess_bus.size),0,n.soc0,n.init_state,repair=True)
        ep.plant(n.init_state,np.zeros(n.bess_bus.size),0,n.soc0,n.init_state,repair=False)
    assert len(ep.cap)==1 and ep.cap[0]['t']==0

if __name__=='__main__':
    for name,f in list(globals().items()):
        if name.startswith('test_'):
            f();print('PASS',name,flush=True)
