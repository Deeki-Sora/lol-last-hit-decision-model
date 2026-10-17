"""Small, auditable belief-state utilities for partially observed lane windows.

The module intentionally knows nothing about League units.  A caller supplies
states, observation likelihoods and (optionally) a transition kernel.  This is
the particle/filter layer used by the finite-window evaluator; it is not a
learned opponent model.
"""
from copy import deepcopy
import math


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be finite")
    return float(value)


def normalize(states):
    """Normalize ``[{state, probability}, ...]`` and merge no states implicitly."""
    if not isinstance(states, list) or not states:
        raise ValueError("belief requires a non-empty state list")
    clean=[]
    total=0.0
    for item in states:
        if not isinstance(item, dict) or "state" not in item:
            raise ValueError("each belief item requires state and probability")
        p=_finite(item.get("probability"), "belief probability")
        if p<0: raise ValueError("belief probability cannot be negative")
        clean.append(dict(state=deepcopy(item["state"]), probability=p));total+=p
    if total<=0: raise ValueError("belief probabilities must have positive mass")
    return [dict(state=x["state"], probability=x["probability"]/total) for x in clean]


def entropy(states):
    return -sum(x["probability"]*math.log(x["probability"], 2)
                for x in normalize(states) if x["probability"]>0)


def bayesian_update(states, likelihoods, observation=None):
    """Apply P(o|s); unknown likelihood is an error rather than zero."""
    prior=normalize(states);weighted=[]
    for index,item in enumerate(prior):
        if callable(likelihoods): p=likelihoods(item["state"], observation)
        elif isinstance(likelihoods, dict): p=likelihoods.get(index, likelihoods.get(str(index)))
        else: raise ValueError("likelihoods must be callable or indexed mapping")
        p=_finite(p, "observation likelihood")
        if p<0: raise ValueError("observation likelihood cannot be negative")
        weighted.append(dict(state=item["state"], probability=item["probability"]*p))
    return normalize(weighted)


def predict(states, transition):
    """Push each belief state through a branching transition kernel."""
    if not callable(transition): raise ValueError("transition must be callable")
    output=[]
    for item in normalize(states):
        branches=transition(deepcopy(item["state"]))
        if not isinstance(branches, list) or not branches: raise ValueError("transition must return branches")
        for branch in branches:
            if not isinstance(branch, dict) or "state" not in branch: raise ValueError("invalid transition branch")
            p=_finite(branch.get("probability"), "transition probability")
            if p<0: raise ValueError("transition probability cannot be negative")
            output.append(dict(state=branch["state"], probability=item["probability"]*p))
    return normalize(output)


def expected(states, value):
    if not callable(value): raise ValueError("value must be callable")
    return sum(item["probability"]*_finite(value(item["state"]), "state value") for item in normalize(states))


def update_with_evidence(states, observation, likelihood, transition=None):
    posterior=bayesian_update(states, likelihood, observation)
    return predict(posterior, transition) if transition is not None else posterior


def roll_forward(states, updates):
    """Apply a reproducible sequence of indexed likelihood updates."""
    current=normalize(states);trace=[dict(step=0,entropy=entropy(current),states=current)]
    for step,update in enumerate(updates,1):
        if not isinstance(update,dict):raise ValueError("belief update must be an object")
        current=bayesian_update(current,update.get("likelihoods"),update.get("observation"))
        trace.append(dict(step=step,observation=update.get("observation"),entropy=entropy(current),states=current))
    return trace

