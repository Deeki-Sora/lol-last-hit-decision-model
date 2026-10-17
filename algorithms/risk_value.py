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


def two_layer_score(strategy,execution,omega=.6,confidence=1.):
    """Framework's strategy-first score; inputs are normalized 0..1 components."""
    if not .6<=omega<=1:raise ValueError("strategy weight omega must be between .6 and 1")
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

