"""Risk-aware short-window decision and two-layer evaluation formulas."""
import math


DEFAULT_METRIC_WEIGHTS={
    "gold_gain":1.0,"xp_gain":0.02,"hp_damage":-0.5,"hp_deficit_change":-0.5,
    "mana_spent":-0.15,"cooldown_remaining_s":-0.1,"pending_enemy_gold":-0.25,
    "pending_enemy_xp":-0.01}


def _finite(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(label+" must be finite")
    return float(value)


def weighted_utility(metrics,weights=None,scales=None):
    weights=weights or DEFAULT_METRIC_WEIGHTS;scales=scales or {}
    result=0.;terms={}
    for key,weight in weights.items():
        if key not in metrics or metrics[key] is None:continue
        scale=_finite(scales.get(key,1.),"metric scale")
        if scale<=0:raise ValueError("metric scales must be positive")
        term=_finite(metrics[key],key)*_finite(weight,key+" weight")/scale
        terms[key]=term;result+=term
    return dict(value=result,terms=terms,missing=sorted(set(weights)-set(terms)))


def lower_cvar(values,probabilities=None,alpha=.2):
    """Expected value in the worst lower-alpha tail of utility values."""
    if not 0<alpha<=1:raise ValueError("alpha must be in (0,1]")
    vals=[_finite(x,"utility") for x in values]
    if not vals:return None
    if probabilities is None:probabilities=[1/len(vals)]*len(vals)
    if len(probabilities)!=len(vals):raise ValueError("probabilities length mismatch")
    total=sum(_finite(p,"probability") for p in probabilities)
    if total<=0:raise ValueError("probabilities must have positive mass")
    pairs=sorted(zip(vals,[p/total for p in probabilities]))
    remain=alpha;out=0.
    for value,p in pairs:
        take=min(remain,p);out+=value*take;remain-=take
        if remain<=1e-12:break
    return out/alpha


def value_of_information(action_values, observation_action_values, observation_probabilities=None):
    """VOI = expected posterior best action minus current best action."""
    if not action_values or not observation_action_values:return 0.
    prior=max(_finite(v,"action value") for v in action_values.values())
    rows=list(observation_action_values)
    if observation_probabilities is None:observation_probabilities=[1/len(rows)]*len(rows)
    if len(rows)!=len(observation_probabilities):raise ValueError("observation probability mismatch")
    total=sum(_finite(p,"observation probability") for p in observation_probabilities)
    if total<=0:raise ValueError("observation probabilities must have positive mass")
    posterior=sum((p/total)*max(_finite(v,"posterior action value") for v in row.values())
                  for p,row in zip(observation_probabilities,rows))
    return max(0.,posterior-prior)


def decision_value(outcomes,weights=None,scales=None,alpha=.2,lambda_risk=.25,voi=0.,nu_voi=.1,execute_cost=0.,kappa=.05):
    """Evaluate a finite action distribution before seeing its outcome."""
    if not outcomes:raise ValueError("at least one outcome is required")
    probabilities=[_finite(x.get("probability",1.),"outcome probability") for x in outcomes]
    total=sum(probabilities)
    if total<=0:raise ValueError("outcome probabilities must have positive mass")
    utilities=[weighted_utility(x.get("metrics",{}),weights,scales)["value"] for x in outcomes]
    expected=sum(p/total*u for p,u in zip(probabilities,utilities));tail=lower_cvar(utilities,probabilities,alpha)
    risk=max(0.,expected-tail);value=expected-lambda_risk*risk+nu_voi*voi-kappa*_finite(execute_cost,"execute_cost")
    return dict(expected_utility=expected,lower_cvar=tail,risk_penalty=risk,voi=voi,
        execution_cost=execute_cost,decision_value=value,utilities=utilities)



def _bounded(value, low=-1., high=1.):
    return max(low, min(high, float(value)))


def _projected_stock_cost(start, end, maximum, horizon_s=0., regen_per_s=0., recovery=0.):
    """Normalized stock expenditure after natural and observed recovery.

    Positive values mean depletion relative to the window start; negative values
    mean the stock ended above its start after recovery.  HP, mana, energy and
    other meters use the same side-specific normalization, so unlike raw values
    they remain comparable across champions and resource systems.
    """
    if any(value is None for value in (start, end, maximum)):
        return None
    start, end, maximum = (_finite(value, 'stock') for value in (start, end, maximum))
    if maximum <= 0:
        raise ValueError('stock maximum must be positive')
    horizon_s = _finite(horizon_s, 'horizon_s')
    regen_per_s = _finite(regen_per_s, 'regen_per_s')
    recovery = _finite(recovery, 'recovery')
    projected = min(maximum, end + max(0., horizon_s) * max(0., regen_per_s) + max(0., recovery))
    return _bounded((start - projected) / maximum)


def _relative_side_cost(a, b, field, horizon_s):
    a_cost = _projected_stock_cost(horizon_s=horizon_s, **a.get(field, {})) if isinstance(a.get(field), dict) else None
    b_cost = _projected_stock_cost(horizon_s=horizon_s, **b.get(field, {})) if isinstance(b.get(field), dict) else None
    return (b_cost - a_cost) if a_cost is not None and b_cost is not None else None


def relative_state_utility(side_a, side_b, horizon_s, references=None, weights=None):
    """Compare two sides' receipts and recoverable state costs.

    The result is centered at zero: equal gold/XP and equal projected states
    yield zero advantage rather than a high absolute score.  ``side_a`` and
    ``side_b`` may contain ``gold_gain``, ``xp_gain``, ``hp``, ``resource``,
    ``cooldowns``, ``summoner_spells`` and ``consumables``.  Stock objects use
    ``start``, ``end``, ``maximum`` and optional ``regen_per_s``/``recovery``.
    Missing fields remain missing and are excluded from the denominator.
    """
    horizon_s = _finite(horizon_s, 'horizon_s')
    references = references or {'gold': 100., 'xp': 100., 'cooldown': 1., 'charges': 1.}
    weights = weights or {'gold': 1., 'xp': 1., 'hp_cost': 1., 'resource_cost': 1.,
                          'cooldown_cost': .5, 'summoner_cost': .75, 'consumable_cost': .5}
    terms = {}
    def receipt(key, ref):
        av, bv = side_a.get(key), side_b.get(key)
        if av is None or bv is None or ref <= 0:return
        terms[key] = _bounded((float(av)-float(bv))/float(ref)) * weights['gold' if key=='gold_gain' else 'xp']
    receipt('gold_gain', references['gold']);receipt('xp_gain', references['xp'])
    for field, key in [('hp', 'hp_cost'), ('resource', 'resource_cost')]:
        value = _relative_side_cost(side_a, side_b, field, horizon_s)
        if value is not None:terms[key] = value * weights[key]
    # Cooldowns: compare unavailable fractions at the common endpoint.
    ac, bc = side_a.get('cooldowns'), side_b.get('cooldowns')
    if isinstance(ac, dict) and isinstance(bc, dict):
        vals=[]
        for ident in set(ac) | set(bc):
            x,y=ac.get(ident),bc.get(ident)
            if isinstance(x,dict) and isinstance(y,dict) and x.get('maximum_s',0)>0 and y.get('maximum_s',0)>0:
                vals.append(_bounded(float(y.get('remaining_s',0))/float(y['maximum_s'])-
                                     float(x.get('remaining_s',0))/float(x['maximum_s'])))
        if vals:terms['cooldown_cost']=sum(vals)/len(vals)*weights['cooldown_cost']
    # A used summoner spell/consumable is a cost only when its state changed.
    for field,key in [('summoner_spells','summoner_cost'),('consumables','consumable_cost')]:
        av,bv=side_a.get(field),side_b.get(field)
        if isinstance(av,dict) and isinstance(bv,dict):
            vals=[]
            for ident in set(av)|set(bv):
                x,y=av.get(ident),bv.get(ident)
                if isinstance(x,dict) and isinstance(y,dict) and x.get('available') is not None and y.get('available') is not None:
                    vals.append(float(bool(x['available']))-float(bool(y['available'])))
                elif isinstance(x,(int,float)) and isinstance(y,(int,float)):
                    vals.append(_bounded(float(x)-float(y)))
            if vals:terms[key]=sum(vals)/len(vals)*weights[key]
    receipt_keys={'gold_gain','xp_gain'}
    receipt_total=sum(terms.get(k,0.) for k in receipt_keys)
    receipt_denom=sum(abs(weights.get('gold' if k=='gold_gain' else 'xp',0.)) for k in receipt_keys if k in terms) or 1.
    cost_total=sum(v for k,v in terms.items() if k not in receipt_keys)
    cost_denom=sum(abs(weights.get(k,0.)) for k in terms if k not in receipt_keys) or 1.
    receipt_advantage=_bounded(receipt_total/receipt_denom)
    cost_advantage=_bounded(cost_total/cost_denom)
    # Receipts are the primary signal; state cost is a bounded secondary adjustment.
    combined=_bounded(receipt_advantage + .5*cost_advantage)
    return {'advantage_a':combined, 'receipt_advantage':receipt_advantage,
            'cost_advantage':cost_advantage, 'terms':terms, 'missing':
            [k for k in ('gold_gain','xp_gain','hp_cost','resource_cost','cooldown_cost','summoner_cost','consumable_cost') if k not in terms],
            'centered_score':50.+50.*combined}

def two_layer_score(strategy,execution,omega=.5,confidence=1.):
    """Published two-layer score with a frozen 50:50 strategy/execution mix."""
    if not math.isclose(float(omega), .5, abs_tol=1e-12):raise ValueError("published layer weight is fixed at omega=0.50")
    if not 0<=confidence<=1:raise ValueError("confidence must be in [0,1]")
    strategy_weights={"window":.25,"resource_plan":.20,"cooldown_discipline":.15,"cost_conversion":.15,"passive":.10,"rune":.05,"adaptation":.10}
    execution_weights={"distance":.35,"phase":.20,"resource":.20,"movement":.15,"timing":.10}
    def layer(data,weights):
        used={};missing=[]
        for key,weight in weights.items():
            value=data.get(key) if isinstance(data,dict) else None
            if value is None:missing.append(key);continue
            used[key]=max(0.,min(1.,_finite(value,key)))*weight
        denominator=sum(weights[k] for k in used)
        return (sum(used.values())/denominator if denominator else None),missing
    k,kmissing=layer(strategy,strategy_weights);o,omissing=layer(execution,execution_weights)
    if k is None or o is None:return dict(score=None,strategy_score=k,execution_score=o,missing=kmissing+omissing,confidence=confidence)
    score=100*(omega*k+(1-omega)*o)*confidence
    return dict(score=score,strategy_score=k,execution_score=o,omega=omega,confidence=confidence,
        missing=kmissing+omissing,interval=[max(0.,score-15*(1-confidence)),min(100.,score+15*(1-confidence))])


def evaluate_policy_branches(branches,side,weights=None,scales=None,alpha=.2,lambda_risk=.25):
    """Attach pre-decision Q values to compare branches and report regret."""
    rows=[]
    for branch in branches:
        metrics=branch.get("metrics",{}).get(side,{})
        q=decision_value([dict(probability=1.,metrics=metrics)],weights,scales,alpha,lambda_risk)
        rows.append(dict(policy=branch[side+'_policy'],**q))
    best=max(rows,key=lambda x:x["decision_value"]) if rows else None
    for row in rows:row["regret"]=(best["decision_value"]-row["decision_value"]) if best else None
    return dict(side=side,branches=rows,best_policy=best["policy"] if best else None)

