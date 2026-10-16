"""Auditable conditional event models; no probabilities from player identity."""
import hashlib
import json
import math
import random


def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def validate(spec):
    data=spec.get('stochastic')
    if data is None:return
    if not isinstance(data.get('samples'),int) or not 1<=data['samples']<=64:raise ValueError('stochastic.samples must be 1..64')
    if not isinstance(data.get('seed'),int):raise ValueError('stochastic.seed must be an integer')
    if len(spec['policies']['blue'])*len(spec['policies']['red'])>16:raise ValueError('probabilistic tasks are limited to 16 policy pairs')
    models=data.get('models',[]);ids={m['id'] for m in models}
    if len(ids)!=len(models):raise ValueError('probability model IDs must be unique')
    for model in models:
        if model.get('context_verified') is not True or not model.get('context_note') or not model.get('source'):
            raise ValueError('probability models require a verified applicability context, source and note')
        if model['sampling'] not in ('empirical','posterior','fixed'):raise ValueError('sampling must be empirical, posterior or fixed')
        if model['kind']=='binary':
            if model['sampling']=='fixed':
                if not finite(model['probability']) or not 0<=model['probability']<=1:raise ValueError('invalid fixed probability')
            else:
                n,k=model['eligible_trials'],model['successes']
                if not isinstance(n,int) or not isinstance(k,int) or not 0<=k<=n or n<1:raise ValueError('binary model requires 0 <= successes <= eligible_trials and at least one trial')
                if model['sampling']=='posterior' and any(not finite(model[x]) or model[x]<=0 for x in ('prior_alpha','prior_beta')):
                    raise ValueError('posterior sampling needs explicit positive Beta prior parameters')
        elif model['kind']=='joint_hits':
            bounds=model.get('distance_interval')
            if not isinstance(bounds,list) or len(bounds)!=2 or any(not finite(x) for x in bounds) or not 0<=bounds[0]<=bounds[1]:
                raise ValueError('joint hit models require a verified ground-distance applicability interval')
            if model.get('target_motion') not in ('any','moving','stationary'):raise ValueError('declare target_motion applicability')
            outcomes=model['outcomes']
            if not outcomes or len({o['id'] for o in outcomes})!=len(outcomes):raise ValueError('joint outcomes require unique IDs')
            for o in outcomes:
                if len(set(o['hits']))!=len(o['hits']) or any(t not in spec['units'] for t in o['hits']):raise ValueError('invalid joint hit target IDs')
                if model['sampling']=='fixed':
                    if not finite(o['probability']) or o['probability']<0:raise ValueError('invalid outcome probability')
                elif not isinstance(o['count'],int) or o['count']<0:raise ValueError('outcome counts must be nonnegative integers')
            total=sum(o.get('probability',0) if model['sampling']=='fixed' else o['count'] for o in outcomes)
            if model['sampling']=='fixed' and not math.isclose(total,1):raise ValueError('joint outcome probabilities must sum to one')
            if total<=0:raise ValueError('joint outcomes require observed trials')
            if model['sampling']=='posterior' and (not finite(model['prior_per_outcome']) or model['prior_per_outcome']<=0):
                raise ValueError('posterior categorical model needs an explicit positive Dirichlet prior')
        else:raise ValueError('unknown probability model kind')
    effects=data.get('effects',[])
    if len({e['id'] for e in effects})!=len(effects):raise ValueError('effect IDs must be unique')
    for e in effects:
        if e['actor'] not in spec['units'] or e.get('verified') is not True or not e.get('source'):raise ValueError('effects require a known actor and verified mechanism source')
        if e['trigger'] not in ('attack_hit','spell_hit','before_damage','minion_kill'):raise ValueError('unsupported effect trigger')
        if not finite(e['cooldown_s']) or e['cooldown_s']<0:raise ValueError('effect cooldown invalid')
        if not finite(e['ready_in_s']) or e['ready_in_s']<0:raise ValueError('declare initial effect cooldown remaining')
        if e.get('probability_model') is not None and e['probability_model'] not in ids:raise ValueError('unknown effect probability model')
        if e.get('probability_model') and next(m for m in models if m['id']==e['probability_model'])['kind']!='binary':raise ValueError('proc models must be binary')
        counter=e['counter']
        if not isinstance(counter['threshold'],int) or counter['threshold']<1 or not finite(counter['window_s']) or counter['window_s']<0:
            raise ValueError('effect counter requires integer threshold >=1 and nonnegative window')
        if not isinstance(counter.get('unique_casts'),bool):raise ValueError('declare unique_casts')
        for hit in counter['initial_hits']:
            if not finite(hit['age_s']) or hit['age_s']<0 or not hit['instance']:raise ValueError('invalid initial counter hit')
        states=e.get('initial_state_scenarios',[])
        if states:
            if any(not finite(s['probability']) or s['probability']<0 for s in states) or not math.isclose(sum(s['probability'] for s in states),1):raise ValueError('initial hidden-state probabilities must sum to one')
            for s in states:
                if not finite(s['ready_in_s']) or s['ready_in_s']<0:raise ValueError('invalid hidden-state cooldown')
                for hit in s['initial_hits']:
                    if not finite(hit['age_s']) or hit['age_s']<0 or not hit['instance']:raise ValueError('invalid hidden-state hit')
        if e['effect']['kind'] not in ('damage','shield','heal','mana','bank_resource','replan'):raise ValueError('unsupported proc effect')
        if e['effect']['target'] not in ('self','event_target'):raise ValueError('effect target must be self or event_target')
        if e['effect']['kind'] in ('shield','heal','mana','bank_resource') and (not finite(e['effect']['amount']) or e['effect']['amount']<0):raise ValueError('effect amount invalid')
        if e['effect']['kind']=='shield' and (not finite(e['effect']['duration_s']) or e['effect']['duration_s']<0):raise ValueError('invalid shield duration')
        if e['effect']['kind']=='bank_resource' and not isinstance(e['effect'].get('invalidates_labels'),list):raise ValueError('resource stacks must declare which combat profiles become stale')
        if e['effect']['kind']=='damage':
            from .short_horizon import packet
            packet(e['effect']['damage'])
        if e['effect']['kind']=='shield' and e['effect'].get('shield_type','all') not in ('all','physical','magic'):
            raise ValueError('invalid proc shield type')
    shared=data.get('initial_joint_states',[])
    if shared:
        if any(not finite(s['probability']) or s['probability']<0 for s in shared) or not math.isclose(sum(s['probability'] for s in shared),1):raise ValueError('initial joint-state probabilities must sum to one')
        for state in shared:
            if any(key not in {e['id'] for e in effects} for key in state['effects']):raise ValueError('unknown effect in joint initial state')
            for s in state['effects'].values():
                if not finite(s['ready_in_s']) or s['ready_in_s']<0:raise ValueError('invalid joint initial cooldown')
                for hit in s['initial_hits']:
                    if not finite(hit['age_s']) or hit['age_s']<0 or not hit['instance']:raise ValueError('invalid joint initial counter')


class Runtime:
    def __init__(self,spec,scenario):
        self.spec=spec;self.data=spec.get('stochastic') or {};self.scenario=scenario
        self.models={m['id']:m for m in self.data.get('models',[])}
        self.counts={};self.parameters={};self.opportunities={};self.effect_states={}
        self.joint_initial={}
        if self.data.get('initial_joint_states'):
            value=self.rng('joint_initial_state').random();total=0
            for state in self.data['initial_joint_states']:
                total+=state['probability']
                if value<total:self.joint_initial=state['effects'];break

    def rng(self,*key):
        seed=json.dumps([self.data.get('seed',0),self.scenario,*key],sort_keys=True,separators=(',',':'))
        return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:16],'big'))

    def distribution(self,model_id):
        if model_id in self.parameters:return self.parameters[model_id]
        m=self.models[model_id];rng=self.rng('parameters',model_id)
        if m['kind']=='binary':
            if m['sampling']=='fixed':p=m['probability']
            elif m['sampling']=='empirical':p=m['successes']/m['eligible_trials']
            else:p=rng.betavariate(m['successes']+m['prior_alpha'],m['eligible_trials']-m['successes']+m['prior_beta'])
            result=[1-p,p]
        else:
            if m['sampling']=='fixed':weights=[o['probability'] for o in m['outcomes']]
            elif m['sampling']=='empirical':weights=[o['count'] for o in m['outcomes']]
            else:weights=[rng.gammavariate(o['count']+m['prior_per_outcome'],1) for o in m['outcomes']]
            total=sum(weights);result=[w/total for w in weights]
        self.parameters[model_id]=result
        return result

    def draw(self,model_id,actor,target):
        m=self.models[model_id];key=(model_id,actor,target)
        i=self.opportunities.get(key,0);self.opportunities[key]=i+1
        # Common random numbers compare policies at matching conditional
        # opportunities. This is not an inferred human-behaviour probability.
        value=self.rng('opportunity',model_id,actor,target,i).random();weights=self.distribution(model_id)
        chosen=len(weights)-1;total=0
        for n,w in enumerate(weights):
            total+=w
            if value<total:chosen=n;break
        count=self.counts.setdefault(model_id,dict(eligible=0,outcomes={}))
        count['eligible']+=1;label=str(chosen) if m['kind']=='binary' else m['outcomes'][chosen]['id']
        count['outcomes'][label]=count['outcomes'].get(label,0)+1
        return chosen

    def hits(self,model_id,actor,target):
        chosen=self.draw(model_id,actor,target)
        return self.models[model_id]['outcomes'][chosen]['hits']

    def applicable(self,world,model_id,actor,target):
        model=self.models[model_id]
        if 'distance_interval' in model:
            d=math.dist(world.units[actor]['position'],world.units[target]['position'])
            if not model['distance_interval'][0]<=d<=model['distance_interval'][1]:return False
        motion=model.get('target_motion','any')
        moving=world.units[target]['motion'] is not None
        return motion=='any' or (motion=='moving')==moving

    def notify(self,world,trigger,p):
        for e in self.data.get('effects',[]):
            actor=e['actor'];target=p['target'];attacker=p['actor']
            if trigger!=e['trigger'] or (target if trigger=='before_damage' else attacker)!=actor:continue
            u=world.units[actor];v=world.units[target]
            if e.get('labels') and p.get('label') not in e['labels']:continue
            if e.get('target_kinds') and v['kind'] not in e['target_kinds']:continue
            if e['id'] not in self.effect_states:
                initial=dict(ready_in_s=e['ready_in_s'],initial_hits=e['counter']['initial_hits'])
                if e.get('initial_state_scenarios'):
                    draw=self.rng('hidden_initial_state',e['id']).random();total=0
                    for scenario in e['initial_state_scenarios']:
                        total+=scenario['probability']
                        if draw<total:initial=scenario;break
                if e['id'] in self.joint_initial:initial=self.joint_initial[e['id']]
                self.effect_states[e['id']]=dict(ready=initial['ready_in_s'],hits=[(-h['age_s'],h['instance']) for h in initial['initial_hits']],qualified=0,activations=0)
            state=self.effect_states[e['id']]
            if state['ready']>world.t:continue
            c=e['counter'];state['hits']=[x for x in state['hits'] if world.t-x[0]<=c['window_s']+1e-9]
            instance=p.get('instance',str(world.serial))
            if c['unique_casts'] and any(x[1]==instance for x in state['hits']):continue
            state['hits'].append((world.t,instance))
            world.record('effect_counter_input',actor=actor,effect=e['id'],counter=len(state['hits']))
            if len(state['hits'])<c['threshold']:continue
            state['hits']=[]
            model=e.get('probability_model')
            if model and not self.applicable(world,model,actor,target):
                world.stop('probability_model_outside_verified_context:'+model);return
            state['qualified']+=1
            success=model is None or self.draw(model,actor,target)==1
            world.record('effect_trigger_trial',actor=actor,effect=e['id'],success=success,model=model)
            if not success:continue
            state['activations']+=1
            state['ready']=world.t+e['cooldown_s'];effect=e['effect'];receiver=actor if effect['target']=='self' else target
            dest=world.units[receiver];kind=effect['kind']
            if kind=='replan':
                world.stop('effect_requires_adapter:'+e['id']);return
            elif kind=='shield':dest['shields'].append(dict(type=effect.get('shield_type','all'),amount=effect['amount'],remaining_s=world.t+effect['duration_s']))
            elif kind=='heal':dest['hp']=min(dest['max_hp'],dest['hp']+effect['amount'])
            elif kind=='mana':
                if dest['mana'] is None:raise ValueError('mana proc on a unit without mana')
                dest['mana']=min(dest['max_mana'],dest['mana']+effect['amount'])
            elif kind=='bank_resource':
                name=effect['resource'];dest['resources'][name]=dest['resources'].get(name,0)+effect['amount']
                dest['stale_labels'].update(effect['invalidates_labels'])
            elif kind=='damage':
                world.impact(dict(actor=actor,target=receiver,effect='damage',label=e['id'],damage=effect['damage'],proc_generated=True))
            world.record('effect_applied',actor=actor,target=receiver,effect=e['id'],effect_kind=kind)

    def summary(self,end):
        return dict(observed_models=self.models,scenario_parameters=self.parameters,simulated_conditional_trials=self.counts,
            effect_counters={k:dict(ready_in_s=max(0,v['ready']-end),qualified_hits=len(v['hits']),
                qualified_opportunities=v['qualified'],activations=v['activations'],
                conditional_activation_rate=v['activations']/v['qualified'] if v['qualified'] else None,
                activations_per_second=v['activations']/end if end>0 else None) for k,v in self.effect_states.items()})
