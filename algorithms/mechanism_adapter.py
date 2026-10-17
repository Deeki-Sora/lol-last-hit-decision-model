"""Data-driven special-mechanic adapters.

The adapter language describes triggers, counters, sequences and arithmetic
effects.  It deliberately contains no champion names or branches.  A page
such as Riot Codex can supply a human-reviewed profile; it is not executed as
code and does not become a source of hidden champion logic.
"""
import ast
import math
from copy import deepcopy

ALLOWED_FIELDS={'level','rank','hp','max_hp','resource','max_resource','bonus_ad','ad','ap','target_hp','target_max_hp',
    'distance','ready_in_s','stacks','hits','count','elapsed_s','base_damage'}
ALLOWED_EFFECTS={'damage','heal','shield','resource','counter','cooldown','replan','stat_override'}


def _number(value,label,minimum=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(label+' must be finite')
    if minimum is not None and value<minimum:raise ValueError(label+' is below minimum')
    return float(value)


def validate_expression(expression):
    if not isinstance(expression,(int,float,str)) or isinstance(expression,bool):raise ValueError('formula must be a number or expression string')
    if isinstance(expression,(int,float)):return
    tree=ast.parse(expression,mode='eval')
    for node in ast.walk(tree):
        if isinstance(node,(ast.Expression,ast.Constant,ast.Name,ast.BinOp,ast.UnaryOp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.USub,ast.UAdd,ast.Mod,ast.Load)):continue
        raise ValueError('formula contains unsupported syntax: '+type(node).__name__)
        

def evaluate_expression(expression,variables):
    validate_expression(expression)
    if isinstance(expression,(int,float)):return float(expression)
    tree=ast.parse(expression,mode='eval')
    names={k:_number(v,k) for k,v in variables.items() if k in ALLOWED_FIELDS and v is not None}
    unknown={node.id for node in ast.walk(tree) if isinstance(node,ast.Name)}-set(names)
    if unknown:raise ValueError('formula variables unavailable: '+','.join(sorted(unknown)))
    value=eval(compile(tree,'<mechanism-formula>','eval'),{'__builtins__':{}},names)
    return _number(value,'formula result')


def validate_profile(profile):
    if not isinstance(profile,dict) or profile.get('schema_version')!=1:raise ValueError('mechanism profile schema_version must be 1')
    if not profile.get('id') or not profile.get('source') or not profile.get('patch'):raise ValueError('mechanism profile needs id, source and patch')
    if profile.get('verified') is not True and profile.get('allow_simulation') is True:raise ValueError('unverified profile cannot be enabled')
    states=profile.get('states',{})
    if not isinstance(states,dict):raise ValueError('states must be an object')
    for name,initial in states.items():
        if not isinstance(name,str) or not isinstance(initial,(int,float,bool,str)):raise ValueError('state values must be scalar')
    for sequence in profile.get('sequences',[]):
        if not sequence.get('id') or not isinstance(sequence.get('steps'),list) or not sequence['steps']:raise ValueError('sequence needs id and steps')
        for step in sequence['steps']:
            for key in ('cast_s','cooldown_s','cost','range'):
                if key in step:validate_expression(step[key])
            if step.get('reset_basic_attack') is not None and not isinstance(step['reset_basic_attack'],bool):raise ValueError('reset_basic_attack must be boolean')
    for trigger in profile.get('triggers',[]):
        if not trigger.get('id') or trigger.get('event') not in ('attack_hit','spell_hit','before_damage','minion_kill','timer','cast_start','cast_end'):
            raise ValueError('trigger requires id and supported event')
        if trigger.get('cooldown_s') is not None:validate_expression(trigger['cooldown_s'])
        for condition in trigger.get('conditions',[]):
            if condition.get('field') not in ALLOWED_FIELDS or condition.get('op') not in ('eq','ne','lt','lte','gt','gte','in'):
                raise ValueError('unsupported trigger condition')
            if condition.get('op')!='in' and isinstance(condition.get('value'),dict):raise ValueError('invalid condition value')
        for effect in trigger.get('effects',[]):
            if effect.get('kind') not in ALLOWED_EFFECTS:raise ValueError('unsupported adapter effect')
            for key in ('amount','duration_s','value','cooldown_s'):
                if key in effect:validate_expression(effect[key])
    return profile


def _condition(condition,variables):
    actual=variables.get(condition['field']);expected=condition.get('value');op=condition['op']
    if actual is None:return False
    if op=='eq':return actual==expected
    if op=='ne':return actual!=expected
    if op=='lt':return actual<expected
    if op=='lte':return actual<=expected
    if op=='gt':return actual>expected
    if op=='gte':return actual>=expected
    return actual in expected


def apply_event(profile,state,event,variables):
    """Apply all eligible generic effects and return an auditable transition."""
    validate_profile(profile);current=deepcopy(state);missing=[];applied=[]
    context=dict(variables);context.update({k:v for k,v in current.items() if k in ALLOWED_FIELDS})
    for trigger in profile.get('triggers',[]):
        if trigger['event']!=event.get('type') or any(not _condition(c,context) for c in trigger.get('conditions',[])):continue
        for effect in trigger.get('effects',[]):
            try:value=evaluate_expression(effect.get('value',effect.get('amount',0)),context)
            except ValueError as error:missing.append(dict(trigger=trigger['id'],reason=str(error)));continue
            kind=effect['kind'];target=effect.get('state')
            if kind=='counter':current[target]=current.get(target,0)+value
            elif kind=='cooldown':current[target]=value
            elif kind=='stat_override':current.setdefault('overrides',{})[target]=value
            elif kind=='resource':current[target]=current.get(target,0)+value
            elif kind=='replan':missing.append(dict(trigger=trigger['id'],reason='effect requires an external adapter'))
            else:applied.append(dict(trigger=trigger['id'],kind=kind,target=effect.get('target','self'),amount=value,duration_s=effect.get('duration_s')))
    return dict(state=current,applied=applied,missing=missing,source=profile['source'],verified=profile['verified'])


def explain_profile(profile):
    validate_profile(profile)
    return dict(id=profile['id'],patch=profile['patch'],source=profile['source'],verified=profile['verified'],
        sequences=len(profile.get('sequences',[])),triggers=len(profile.get('triggers',[])),
        unsupported=profile.get('unsupported',[]),allow_simulation=profile.get('allow_simulation',False))

