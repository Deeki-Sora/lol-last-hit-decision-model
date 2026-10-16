"""Paired belief-scenario rollouts + restricted matrix game; no VOD-fitting loop."""
from simulator import *
from scipy.optimize import linprog
import nashpy as nash
import argparse, warnings, platform, importlib.metadata, time

POLICIES=[(m,c) for m in range(4) for c in range(3)]
OPPONENTS=['aa_only','q_secure','push']

def interval(v):
    a=np.asarray(v,float);return dict(mean=float(a.mean()),p05=float(np.quantile(a,.05)),p95=float(np.quantile(a,.95)))

def main(n=128):
    out=BASE/'results';out.mkdir(exist_ok=True);rows=[];start=time.perf_counter()
    for seed in range(n):
        p=particle(seed)
        for pi in POLICIES:
            for op in OPPONENTS:rows.append(Wave(p,pi,op).run())
        if (seed+1)%16==0:print(f'{seed+1}/{n} paired particles completed',flush=True)
    write_csv(out/'rollouts.csv',rows)
    measures=['A_cs','B_cs','A_gold','B_gold','A_xp','B_xp','A_xp_rate','B_xp_rate','A_hp_loss','B_hp_loss','A_mana_spent','A_cd_area','B_cd_area','A_pending_xp','B_pending_xp','A_enemy_alive','B_enemy_alive','utility']
    summary=[]
    for pi in POLICIES:
        name=f'{pi[0]}-{pi[1]}';group=[r for r in rows if r['setup']==name]
        summary.append(dict(policy=name,**{k:interval([r[k] for r in group]) for k in measures}))
    summaries={r['policy']:r for r in summary}
    matrix=np.array([[np.mean([r['utility'] for r in rows if r['setup']==f'{pi[0]}-{pi[1]}' and r['opponent']==op]) for op in OPPONENTS] for pi in POLICIES])
    # Zero-sum relative-resource stress test; NOT the unrestricted LoL equilibrium.
    lp=linprog(np.r_[np.zeros(len(POLICIES)),-1],A_ub=np.c_[-matrix.T,np.ones(len(OPPONENTS))],b_ub=np.zeros(len(OPPONENTS)),
               A_eq=[np.r_[np.ones(len(POLICIES)),0]],b_eq=[1],bounds=[(0,None)]*len(POLICIES)+[(None,None)],method='highs')
    assert lp.success,lp.message
    # Nashpy independently checks the support of non-duplicated pure candidates via vertex enumeration.
    # Remove dominated rows to keep degeneracies from flooding the solver.
    keep=[i for i in range(len(POLICIES)) if not any(np.all(matrix[j]>=matrix[i]-1e-10) and np.any(matrix[j]>matrix[i]+1e-10) for j in range(len(POLICIES)) if j!=i)]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');eqs=list(nash.Game(matrix[keep],-matrix[keep]).vertex_enumeration())
    nash_check=[]
    for pa,pb in eqs:
        value=float(pa@matrix[keep]@pb)
        nash_check.append(dict(rows=[f'{POLICIES[i][0]}-{POLICIES[i][1]}' for i in keep],A=pa.tolist(),B=pb.tolist(),value=value,
                               exploitability=float(max(matrix[keep]@pb)-min(pa@matrix[keep]))))
    index={(r['seed'],r['setup'],r['opponent']):r for r in rows};paired=[]
    for seed in range(n):
        for op in OPPONENTS:
            a=index[seed,'0-0',op];b=index[seed,'3-2',op]
            paired.append(dict(seed=seed,opponent=op,**{k:b[k]-a[k] for k in measures}))
    write_csv(out/'paired_3_2_minus_baseline.csv',paired)
    # Weight sensitivity, selected from exactly the same transitions (no re-fitting).
    sensitivity=[]
    for wx in [0.,.5,1.,2.]:
        for wh in [0.,.5,1.]:
            means={s:np.mean([utility(r,wx=wx,wh=wh) for r in rows if r['setup']==s]) for s in summaries}
            sensitivity.append(dict(xp_weight=wx,hp_weight=wh,best=max(means,key=means.get),baseline=means['0-0'],setup_3_2=means['3-2']))
    write_csv(out/'weight_sensitivity.csv',sensitivity)
    # An independent seed set assesses selection without reusing its own rollout noise.
    winner=max(summaries,key=lambda s:summaries[s]['utility']['mean']);chosen=tuple(map(int,winner.split('-')))
    heldout=[]
    for seed in range(10000,10064):
        p=particle(seed)
        for pi in set([(0,0),(3,2),chosen]):
            for op in OPPONENTS:heldout.append(Wave(p,pi,op).run())
    write_csv(out/'heldout_rollouts.csv',heldout)
    # Free-time pressure off ablation is paired across the SAME physical particles.
    ablation=[]
    for seed in range(32):
        for pi in [(0,0),(3,2)]:
            for op in OPPONENTS:ablation.append(Wave(particle(seed),pi,op,pressure=False).run())
    write_csv(out/'no_pressure_ablation.csv',ablation)
    nominal={};validation=[]
    for name,pi in [('baseline',(0,0)),('setup_3_2',(3,2)),('selected',chosen)]:
        w=Wave(particle(0,True),pi,record=True);nominal[name]=w.run()
        write_csv(out/f'{name}_events.csv',w.events);write_csv(out/f'{name}_states_0_5s.csv',w.frames)
        write_csv(out/f'{name}_deaths.csv',w.deaths);write_csv(out/f'{name}_observations.csv',w.obs)
        nominal[name]['first_actions']=w.first_actions
        for observed in CFG['observation_checkpoints']:
            sim=min(w.obs,key=lambda x:abs(x['t']-observed['clip_t']))
            validation.append(dict(policy=name,t=observed['clip_t'],frame=observed['frame'],observed_A_cs=observed['A_cs'],
                                   simulated_A_cs=sim['A_cs'],observed_B_cs=observed['B_cs'],simulated_B_cs=sim['B_cs']))
    write_csv(out/'vod_checkpoint_validation.csv',validation)
    result=dict(status='conditional_simulation_executed_not_vod_validated',particles=n,training_rollouts=len(rows),
                heldout_rollouts=len(heldout),ablation_rollouts=len(ablation),seed_scheme='0..N-1 paired; heldout 10000..10063',
                posterior_calibrated=False,opponent_weights='equal design weights; not inferred opponent probabilities',
                metrics=summary,paired={k:interval([r[k] for r in paired]) for k in measures},
                fraction_setup_beats_baseline=float(np.mean([r['utility']>0 for r in paired])),
                payoff_matrix=matrix.tolist(),policies=[f'{a}-{b}' for a,b in POLICIES],opponents=OPPONENTS,
                selected_equal_weight=winner,restricted_minimax=dict(mix=lp.x[:-1].tolist(),value=float(lp.x[-1])),
                nashpy_checks=nash_check,weight_sensitivity=sensitivity,nominal=nominal,
                seconds_elapsed=time.perf_counter()-start,
                versions=dict(python=platform.python_version(),numpy=np.__version__,simpy=simpy.__version__,nashpy=nash.__version__),
                source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [BASE/'simulator.py',BASE/'initial_state.json',BASE/'run_experiment.py']})
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['training_rollouts','selected_equal_weight','fraction_setup_beats_baseline','seconds_elapsed','restricted_minimax']},indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--particles',type=int,default=128);args=parser.parse_args();main(args.particles)
