"""Generic last-hit-window scheduling, independent of champion identities.

Each target supplies feasible impact intervals and a resource cost.  The
scheduler only handles shared actor time and target claim conflicts; damage,
aggro and champion-specific effects remain inputs to the caller.
"""
from copy import deepcopy
import math


def _number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value<minimum:
        raise ValueError(label+" must be a finite number >= "+str(minimum))
    return float(value)


def feasible_claims(targets, actor_ready_s=0.0, actor_period_s=0.0, horizon_s=30.0):
    """Convert target windows to individual feasible claims.

    Target format: ``id``, ``impact_window=[lo,hi]``, optional ``commit_s``,
    ``duration_s``, ``probability``, ``gold``, ``xp`` and ``cost``.
    """
    actor_ready_s=_number(actor_ready_s,"actor_ready_s");actor_period_s=_number(actor_period_s,"actor_period_s")
    horizon_s=_number(horizon_s,"horizon_s")
    claims=[]
    for target in targets:
        if not isinstance(target,dict) or not target.get("id"): raise ValueError("target id is required")
        window=target.get("impact_window")
        if not isinstance(window,list) or len(window)!=2: raise ValueError("impact_window requires [lo,hi]")
        lo=_number(window[0],"impact_window lower");hi=_number(window[1],"impact_window upper")
        if hi<lo or lo>horizon_s: continue
        duration=_number(target.get("duration_s",target.get("commit_s",0)),"claim duration")
        earliest=max(lo,actor_ready_s)
        latest=min(hi,horizon_s)
        if earliest>latest: continue
        claims.append(dict(id=str(target["id"]),commit_s=earliest,duration_s=duration,
            impact_s=earliest,impact_window=[lo,hi],probability=float(target.get("probability",1)),
            gold=float(target.get("gold",0)),xp=float(target.get("xp",0)),cost=deepcopy(target.get("cost",{})),
            source=deepcopy(target)))
    return claims


def enumerate_schedules(claims, horizon_s=30.0, max_schedules=256):
    """Enumerate non-overlapping schedules; each target can be claimed once."""
    horizon_s=_number(horizon_s,"horizon_s");claims=sorted(claims,key=lambda x:(x["commit_s"],x["id"]))
    result=[]
    def visit(index, selected, ready):
        if len(result)>=max_schedules:return
        if selected: result.append(deepcopy(selected))
        for i in range(index,len(claims)):
            claim=claims[i]
            if claim["commit_s"]+1e-9<ready: continue
            visit(i+1,selected+[claim],claim["commit_s"]+claim["duration_s"])
    visit(0,[],0.)
    result.append([])
    return result[:max_schedules]


def evaluate_schedule(schedule, horizon_s=30.0):
    horizon_s=_number(horizon_s,"horizon_s")
    schedule=sorted((deepcopy(x) for x in schedule),key=lambda x:x["commit_s"])
    cursor=0.;free=[];gold=xp=success=0.;cost={};conflicts=[]
    for claim in schedule:
        if claim["commit_s"]<cursor-1e-9: conflicts.append(claim["id"]);continue
        if claim["commit_s"]>cursor:free.append([cursor,claim["commit_s"]])
        cursor=max(cursor,claim["commit_s"]+claim["duration_s"])
        probability=max(0,min(1,claim["probability"]));gold+=probability*claim["gold"];xp+=probability*claim["xp"];success+=probability
        for key,value in claim["cost"].items():cost[key]=cost.get(key,0)+probability*float(value)
    if cursor<horizon_s:free.append([cursor,horizon_s])
    return dict(claims=[x["id"] for x in schedule],expected_gold=gold,expected_xp=xp,
        expected_success=success,expected_cost=cost,free_windows=free,conflicts=conflicts,
        occupied_time=sum(x["duration_s"] for x in schedule),horizon_s=horizon_s)


def best_schedule(targets, actor_ready_s=0., actor_period_s=0., horizon_s=30., max_schedules=256):
    claims=feasible_claims(targets,actor_ready_s,actor_period_s,horizon_s)
    schedules=enumerate_schedules(claims,horizon_s,max_schedules)
    evaluated=[evaluate_schedule(s,horizon_s) for s in schedules]
    return max(evaluated,key=lambda x:(x["expected_gold"],x["expected_xp"],-sum(x["expected_cost"].values()))) if evaluated else evaluate_schedule([],horizon_s)

