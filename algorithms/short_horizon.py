"""Conditional lane-event rollouts. No champion data or implicit game-server AI.

Supported rules are explicit and patch-scoped. Unmodelled transitions terminate
the validity interval instead of inventing an outcome. Uses only the stdlib.
"""
from copy import deepcopy
import heapq
import math

SIDES=('blue','red')
MINIONS={'melee','caster','siege','super','minion'}


def number(value, label, minimum=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(label+' requires a finite number')
    if minimum is not None and value<minimum:raise ValueError(label+' is below its minimum')
    return value


def validate(spec):
    if spec.get('schema_version')!=1:raise ValueError('game task schema_version must be 1')
    number(spec['entry_time_s'],'entry_time_s',0)
    if not 0<number(spec['horizon_s'],'horizon_s')<=30:raise ValueError('horizon must be >0 and <=30 seconds')
    rules=spec['rules']
    if not rules.get('verified') or not rules.get('patch') or not rules.get('sources'):
        raise ValueError('verified patch-specific rules and sources are required')
    if rules.get('unit_scope_verified') is not True or not rules.get('unit_scope_note'):
        raise ValueError('verify the relevant unit scope, including minions that could influence the window')
    if rules.get('geometry')!='verified_game_ground_coordinates':
        raise ValueError('range legality requires verified game-ground coordinates; health-bar pixels alone are insufficient')
    if rules.get('unsupported_mechanics'):
        raise ValueError('unsupported mechanics must be resolved or excluded from this window: '+str(rules['unsupported_mechanics']))
    if rules.get('unmodelled_effects')!='replan':raise ValueError('unmodelled_effects must be replan')
    if rules.get('level_up')!='replan':raise ValueError('level_up must be replan; supply a new state/skill profile after leveling')
    if rules.get('retarget')!='replan':raise ValueError('unknown minion retargeting must replan')
    if rules.get('hero_aggro')!='replan':raise ValueError('unimplemented champion-to-minion aggro must replan')
    if not isinstance(rules.get('aggro_triggers'),list):raise ValueError('declare complete patch-scoped aggro_triggers, including an explicitly verified empty list when inapplicable')
    for trigger in rules['aggro_triggers']:
        if trigger['action'] not in ('attack','cast') or trigger['target_kind'] not in ('hero','minion'):
            raise ValueError('unsupported aggro trigger')
        number(trigger['radius'],'aggro radius',0)
    if rules.get('pathing')!='verified_clear_straight_segments':raise ValueError('movement paths must be verified clear straight segments')
    if rules.get('xp_mode')!='solo_lane':raise ValueError('only solo-lane XP accounting is supported; shared/quest exceptions need a separate profile')
    number(rules['xp_range'],'xp_range',0)
    number(rules['solo_xp_multiplier'],'solo_xp_multiplier',0)
    if not isinstance(rules.get('last_hitter_xp_outside_range'),bool):raise ValueError('declare last_hitter_xp_outside_range')
    step=number(rules['projectile_step_s'],'projectile_step_s')
    if not .005<=step<=.05:raise ValueError('projectile integration step must be 0.005 to 0.05 seconds')
    units=spec['units']
    from .probabilistic_mechanics import validate as validate_probabilities
    validate_probabilities(spec)
    if not isinstance(units,dict) or not 2<=len(units)<=60:raise ValueError('require 2 to 60 units')
    for side in SIDES:
        if sum(u['kind']=='hero' and u['side']==side for u in units.values())!=1:
            raise ValueError('exactly one hero per side is supported')
    for uid,u in units.items():
        if u['side'] not in SIDES or u['kind'] not in MINIONS|{'hero'}:raise ValueError('unsupported unit side/kind')
        if len(u['position'])!=2:raise ValueError('position requires [x,y]')
        for x in u['position']:number(x,'position')
        for key in ('hp','max_hp','radius','move_speed','hp_regen_s','armor','magic_resist'):
            number(u[key],uid+'.'+key,0 if key not in ('armor','magic_resist') else None)
        if not 0<u['hp']<=u['max_hp']:raise ValueError('initial units must be alive, with 0 < hp <= max_hp')
        for key in ('mana','max_mana','mana_regen_s'):
            if u.get(key) is not None:number(u[key],uid+'.'+key,0)
        if u['mana'] is not None and (u['max_mana'] is None or u['mana_regen_s'] is None or u['mana']>u['max_mana']):
            raise ValueError('invalid mana state')
        if u.get('resource_model') not in ('mana','none') or (u['resource_model']=='mana')!=(u['mana'] is not None):
            raise ValueError('resource_model must explicitly distinguish mana from no-resource; other resource systems need an adapter')
        if u.get('phase') not in ('idle','windup','in_flight','recovery','casting'):raise ValueError('declare each unit attack/cast phase')
        movement=u.get('movement',{})
        if movement.get('verified') is not True:raise ValueError('verify current movement before predicting')
        if movement.get('destination') is not None:
            if len(movement['destination'])!=2:raise ValueError('movement destination requires a ground point')
            for x in movement['destination']:number(x,'initial movement destination')
        if u.get('effects_inactive_verified') is not True and u.get('effects_adapter_verified') is not True:
            raise ValueError(uid+': passive/rune/item/CC effects must be verified inactive, or provide an earlier valid_until_s boundary')
        if u.get('effects_adapter_verified') is True:
            effect_ids={e['id'] for e in (spec.get('stochastic') or {}).get('effects',[]) if e['actor']==uid}
            if not effect_ids or set(u.get('covered_effect_ids',[]))!=effect_ids:
                raise ValueError(uid+': list all covered_effect_ids and provide matching verified effect adapters')
        if not isinstance(u.get('effects_scope_note'),str) or not u['effects_scope_note'].strip():
            raise ValueError(uid+': explain why passive/rune/item/CC effects cannot change this bounded window')
        aa=u['attack']
        for key in ('attack_speed','period_s','windup_s','range','missile_speed','ready_in_s'):number(aa[key],uid+'.attack.'+key,0)
        if aa['period_s']<=0 or aa['windup_s']>aa['period_s']:raise ValueError('attack period/windup invalid')
        if aa['attack_speed']<=0 or not math.isclose(aa['period_s']*aa['attack_speed'],1,rel_tol=1e-6):raise ValueError('period_s must equal 1/effective attack_speed')
        if aa['range_mode']!='edge_to_edge':raise ValueError('basic attacks require edge_to_edge range semantics')
        packet(aa['damage'])
        for name,skill in u.get('skills',{}).items():
            if name=='attack':raise ValueError('attack is reserved for basic attacks')
            if skill['delivery'] not in ('targeted','self','skillshot_probability'):raise ValueError(name+': unsupported delivery')
            if skill['delivery']=='skillshot_probability':
                if skill['effect']!='damage':raise ValueError('this joint-hit adapter supports damaging skillshots only')
                model=next((m for m in (spec.get('stochastic') or {}).get('models',[]) if m['id']==skill.get('outcome_model')),None)
                if model is None or model['kind']!='joint_hits':raise ValueError('skillshots require a joint hit/miss outcome model')
                if skill.get('collateral_scope_verified') is not True:raise ValueError('verify all possibly affected minions/heroes, not only the main target')
                number(skill['impact_delay_s'],'skillshot impact_delay_s',0)
                maximum=skill.get('max_hits')
                if not isinstance(maximum,int) or maximum<1 or any(len(o['hits'])>maximum for o in model['outcomes']):raise ValueError('joint outcomes exceed declared maximum penetration/targets')
                if any(units[t]['side']==u['side'] for o in model['outcomes'] for t in o['hits']):raise ValueError('damaging skillshot outcomes cannot include allies')
            if skill['range_mode'] not in ('center_to_center','edge_to_edge'):raise ValueError('invalid skill range_mode')
            if skill['commit']!='start':raise ValueError('only explicitly start-committed single-cast skills are supported')
            if skill.get('interruptible_by_move') is not False:raise ValueError('cast cancellation/refunds require another adapter; declare interruptible_by_move=false only when verified')
            if skill['effect'] not in ('damage','heal','shield'):raise ValueError('unsupported skill effect')
            if skill.get('charges',1)!=1:raise ValueError('charge skills require another adapter')
            for key in ('rank','cast_s','cooldown_s','cost','range','missile_speed','ready_in_s'):
                number(skill[key],name+'.'+key,0)
            if skill['effect']=='damage':packet(skill['damage'])
            else:number(skill['amount'],name+'.amount',0)
            if skill['effect']=='shield':number(skill['duration_s'],name+'.duration_s',0)
        if u['kind']=='hero':
            for key in ('xp','next_level_xp','level','gold_multiplier','xp_multiplier'):number(u[key],uid+'.'+key,0)
            if u['next_level_xp']<=u['xp']:raise ValueError('next_level_xp must exceed current cumulative xp')
        else:
            for key in ('gold_reward','xp_reward'):number(u[key],uid+'.'+key,0)
            target=u.get('locked_target')
            if target is not None and (target not in units or units[target]['side']==u['side']):raise ValueError('invalid locked target')
            if target is not None and units[target]['movement']['destination'] is not None:
                raise ValueError('moving locked targets require a verified pursuit adapter; select a stationary-target window')
            if target is None and number(u.get('idle_verified_until_s'),'idle_verified_until_s',0)<min(spec['horizon_s'],rules.get('valid_until_s',spec['horizon_s'])):
                raise ValueError('idle minion state is not verified through the requested boundary')
        for shield in u.get('shields',[]):
            number(shield['amount'],'shield amount',0);number(shield['remaining_s'],'shield expiry',0)
            if shield['type'] not in ('all','physical','magic'):raise ValueError('invalid shield type')
    if rules.get('valid_until_s') is not None:
        if not 0<number(rules['valid_until_s'],'valid_until_s')<=spec['horizon_s']:raise ValueError('valid_until_s is relative to entry and must lie inside the horizon')
        if not rules.get('boundary_reason'):raise ValueError('valid_until_s requires a boundary_reason')
    pending=spec.get('in_progress_actions',[])
    if len({p['actor'] for p in pending})!=len(pending):raise ValueError('one in-progress windup/cast per unit')
    for uid,u in units.items():
        if (u['phase'] in ('windup','casting'))!=(uid in {p['actor'] for p in pending}):raise ValueError('in-progress windup/cast must match the declared unit phase')
    for p in pending:
        if p['actor'] not in units or p['target'] not in units or p['kind'] not in ('attack','cast'):raise ValueError('invalid in-progress action')
        number(p['release_in_s'],'release_in_s',0);number(p['started_ago_s'],'started_ago_s',0)
        if p['kind']=='cast' and p['skill'] not in units[p['actor']]['skills']:raise ValueError('unknown in-progress skill')
    for side in SIDES:
        policies=spec['policies'][side]
        if not isinstance(policies,list) or not policies or len(policies)>8:raise ValueError('require 1 to 8 policies per side')
        if len({p['id'] for p in policies})!=len(policies):raise ValueError('policy IDs must be unique per side')
        for policy in policies:
            for cmd in policy['commands']:
                if cmd['kind'] not in ('attack','cast','move','wait'):raise ValueError('unsupported command')
                if not 0<=number(cmd['at_s'],'command time')<=spec['horizon_s']:raise ValueError('command outside horizon')
                if 'if' in cmd:
                    gate=cmd['if']
                    if set(gate)-{'target','hp_at_most','alive'}:raise ValueError('unsupported policy condition')
                    if gate.get('target') not in units:raise ValueError('unknown conditional target')
                    if 'hp_at_most' in gate:number(gate['hp_at_most'],'conditional hp',0)
                if cmd['kind'] in ('attack','cast') and cmd.get('target') not in units:raise ValueError('unknown action target')
                if cmd['kind']=='move':
                    if len(cmd['to'])!=2:raise ValueError('move requires a ground point')
                    for x in cmd['to']:number(x,'move destination')
    return spec


def packet(value):
    if value['type'] not in ('physical','magic','true'):raise ValueError('invalid damage type')
    for field in ('base','target_current_hp_ratio','target_max_hp_ratio'):number(value[field],'damage.'+field,0)
    if 'mitigation_multiplier' in value:number(value['mitigation_multiplier'],'mitigation_multiplier',0)
    for kind,override in value.get('by_target_kind',{}).items():
        if kind not in MINIONS|{'hero'}:raise ValueError('unknown per-target-kind damage override')
        packet(override)


def mitigation(resistance):
    return 100/(100+resistance) if resistance>=0 else 2-100/(100-resistance)


class Rollout:
    def __init__(self,spec,blue,red,end,scenario=0):
        self.spec=spec;self.units=deepcopy(spec['units']);self.rules=spec['rules'];self.t=0.;self.end=end
        self.queue=[];self.serial=0;self.log=[];self.boundary=None;self.count=0
        self.initial=deepcopy(self.units)
        from .probabilistic_mechanics import Runtime
        self.mechanics=Runtime(spec,scenario)
        for uid,u in self.units.items():
            u.update(gold_gain=0.,xp_gain=0.,hp_damage=0.,hp_healed=0.,mana_spent=0.,busy_until=0.,token=0,motion=None)
            u['resources']=deepcopy(u.get('resources',{}));u['stale_labels']=set()
            u['motion']={'to':list(u['movement']['destination'])} if u['movement']['destination'] is not None else None
            u['attack_ready']=u['attack']['ready_in_s']
            u['skill_ready']={k:v['ready_in_s'] for k,v in u.get('skills',{}).items()}
            u['shields']=deepcopy(u.get('shields',[]))
            if u['kind']!='hero' and u.get('locked_target') and u['phase'] not in ('windup','casting'):
                self.add(u['attack_ready'],3,'auto',{'actor':uid})
        for p in spec.get('in_progress_actions',[]):
            u=self.units[p['actor']];profile=u['attack'] if p['kind']=='attack' else u['skills'][p['skill']]
            u['token']+=1;u['casting']=p['kind']=='cast';u['busy_until']=p['release_in_s'];u['motion']=None
            self.add(p['release_in_s'],2,'launch',dict(actor=p['actor'],target=p['target'],profile=deepcopy(profile),
                token=u['token'],label='attack' if p['kind']=='attack' else p['skill'],effect='damage' if p['kind']=='attack' else profile['effect'],
                start=-p['started_ago_s'],auto=u['kind']!='hero'))
        for side,policy in [('blue',blue),('red',red)]:
            actor=next(uid for uid,u in self.units.items() if u['kind']=='hero' and u['side']==side)
            for cmd in policy['commands']:self.add(cmd['at_s'],3,'command',dict(cmd,actor=actor))
        for event in spec.get('committed_attacks',[]):
            if event['source'] not in self.units or event['target'] not in self.units:raise ValueError('unknown committed attack unit')
            packet(event['damage']);number(event['remaining_s'],'committed remaining_s',0)
            if event.get('already_launched') is not True:raise ValueError('only already-launched committed packets may bypass windup')
            if self.units[event['source']]['side']==self.units[event['target']]['side']:raise ValueError('committed damage must target enemies')
            self.add(event['remaining_s'],1,'impact',dict(event,actor=event['source'],effect='damage',label='committed'))

    def add(self,t,priority,kind,data):
        self.serial+=1
        heapq.heappush(self.queue,(t,priority,self.serial,kind,data))

    def record(self,kind,**fields):self.log.append(dict(t_s=self.t,source_time_s=self.spec['entry_time_s']+self.t,kind=kind,**fields))

    def stop(self,reason):
        if self.boundary is None:self.boundary=dict(t_s=self.t,reason=reason)
        self.record('replan_required',reason=reason)

    def advance(self,t):
        dt=t-self.t
        for u in self.units.values():
            if u['hp']<=0:continue
            u['hp']=min(u['max_hp'],u['hp']+u['hp_regen_s']*dt)
            if u['mana'] is not None:u['mana']=min(u['max_mana'],u['mana']+u['mana_regen_s']*dt)
            if u['motion']:
                motion=u['motion'];length=math.dist(u['position'],motion['to'])
                distance=min(length,u['move_speed']*dt)
                if length>0:u['position']=[x+(y-x)*distance/length for x,y in zip(u['position'],motion['to'])]
                if distance>=length:u['motion']=None
            u['shields']=[s for s in u['shields'] if s['remaining_s']>t and s['amount']>0]
            if u['busy_until']<=t and not u.get('casting'):u['phase']='idle' if u['attack_ready']<=t else 'recovery'
        self.t=t

    def in_range(self,actor,target,profile):
        a,b=self.units[actor],self.units[target]
        distance=math.dist(a['position'],b['position'])
        if profile['range_mode']=='edge_to_edge':distance=max(0,distance-a['radius']-b['radius'])
        return distance<=profile['range']+1e-9

    def command(self,cmd,auto=False):
        actor=cmd['actor'];u=self.units[actor]
        if u['hp']<=0:return
        gate=cmd.get('if')
        if gate:
            target=self.units[gate['target']]
            if ('alive' in gate and (target['hp']>0)!=gate['alive']) or ('hp_at_most' in gate and target['hp']>gate['hp_at_most']):
                return self.record('condition_not_met',actor=actor)
        kind=cmd['kind']
        if kind=='wait':return self.record('wait',actor=actor)
        if kind=='move':
            if any(v['hp']>0 and v['kind'] in MINIONS and v.get('locked_target')==actor for v in self.units.values()):
                return self.stop('moving_locked_target_requires_pursuit_adapter')
            if u['busy_until']>self.t and u.get('casting'):
                return self.record('illegal_action',actor=actor,reason='noninterruptible cast')
            if u['busy_until']>self.t:
                u['token']+=1;u['busy_until']=self.t
                u['phase']='idle' if u['attack_ready']<=self.t else 'recovery'
                self.record('attack_windup_cancelled',actor=actor)
            u['motion']={'to':cmd['to']}
            return self.record('move',actor=actor,to=cmd['to'])
        target=cmd['target'];v=self.units[target]
        if v['hp']<=0:
            if auto:self.stop('locked_target_died:'+actor)
            else:self.record('illegal_action',actor=actor,reason='target dead')
            return
        if u['busy_until']>self.t+1e-9:return self.record('illegal_action',actor=actor,reason='windup/cast busy')
        if kind=='attack':
            profile=u['attack'];ready=u['attack_ready'];label='attack';effect='damage'
            if v['side']==u['side']:return self.record('illegal_action',actor=actor,reason='allied attack target')
        else:
            label=cmd['skill']
            if label not in u.get('skills',{}):return self.record('illegal_action',actor=actor,reason='skill not learned')
            profile=u['skills'][label];ready=u['skill_ready'][label];effect=profile['effect']
            if profile['rank']<1:return self.record('illegal_action',actor=actor,reason='skill not learned')
            if profile['delivery']=='self' and actor!=target:return self.record('illegal_action',actor=actor,reason='self-only skill')
            if (effect=='damage')==(v['side']==u['side']):return self.record('illegal_action',actor=actor,reason='skill target side')
            if u['mana'] is None and profile['cost']>0:return self.record('illegal_action',actor=actor,reason='unsupported non-mana resource cost')
            if u['mana'] is not None and u['mana']<profile['cost']:return self.record('illegal_action',actor=actor,reason='insufficient mana')
        if label in u['stale_labels']:return self.stop('resource_stack_requires_updated_combat_profile:'+actor+':'+label)
        if ready>self.t+1e-9:return self.record('illegal_action',actor=actor,reason='cooldown')
        if not self.in_range(actor,target,profile):
            if auto:self.stop('locked_target_out_of_range:'+actor)
            else:self.record('illegal_action',actor=actor,reason='range')
            return
        if u['kind']=='hero' and effect=='damage':
            for trigger in self.rules['aggro_triggers']:
                group='hero' if v['kind']=='hero' else 'minion'
                if trigger['action']==kind and trigger['target_kind']==group and any(
                    m['kind'] in MINIONS and m['hp']>0 and m['side']!=u['side'] and
                    math.dist(m['position'],u['position'])<=trigger['radius'] for m in self.units.values()):
                    return self.stop('aggro_transition_requires_updated_minion_targets')
        u['motion']=None;u['token']+=1;u['casting']=kind=='cast'
        u['phase']='casting' if kind=='cast' else 'windup'
        windup=profile['windup_s'] if kind=='attack' else profile['cast_s']
        u['busy_until']=self.t+windup
        if kind=='cast':
            if u['mana'] is not None:u['mana']-=profile['cost'];u['mana_spent']+=profile['cost']
            u['skill_ready'][label]=self.t+profile['cooldown_s']
        payload=dict(actor=actor,target=target,profile=deepcopy(profile),token=u['token'],label=label,effect=effect,start=self.t,auto=auto)
        self.add(self.t+windup,2,'launch',payload)
        self.record('attack_start' if kind=='attack' else 'cast_start',actor=actor,target=target,label=label)

    def launch(self,p):
        u=self.units[p['actor']];v=self.units[p['target']]
        if u['hp']<=0 or u['token']!=p['token']:return
        u['casting']=False
        u['phase']='recovery' if p['label']=='attack' else 'idle'
        if v['hp']<=0 and p['profile'].get('delivery')!='skillshot_probability':
            if p['auto']:self.stop('locked_target_died_during_windup:'+p['actor'])
            return
        if p['label']=='attack':
            if not self.in_range(p['actor'],p['target'],p['profile']):
                if p['auto']:self.stop('locked_target_left_attack_range:'+p['actor'])
                else:self.record('attack_cancelled_range',actor=p['actor'],target=p['target'])
                return
            u['attack_ready']=max(self.t,p['start']+p['profile']['period_s'])
            if p['auto']:self.add(u['attack_ready'],3,'auto',{'actor':p['actor']})
        self.record('launch',actor=p['actor'],target=p['target'],label=p['label'])
        effect=deepcopy(p['profile']);effect.update(actor=p['actor'],target=p['target'],effect=p['effect'],label=p['label'])
        effect['instance']=p['actor']+':'+str(p['token'])
        if p['profile'].get('delivery')=='skillshot_probability':
            model=p['profile']['outcome_model']
            if not self.mechanics.applicable(self,model,p['actor'],p['target']):return self.stop('probability_model_outside_verified_context:'+model)
            targets=self.mechanics.hits(model,p['actor'],p['target'])
            self.record('joint_skillshot_outcome',actor=p['actor'],targets=targets,model=model)
            for target in targets:self.add(self.t+p['profile']['impact_delay_s'],1,'impact',dict(effect,target=target))
            return
        if p['profile']['missile_speed']>0:
            effect.update(projectile_position=list(u['position']),last_t=self.t)
            self.add(self.t+self.rules['projectile_step_s'],1,'projectile',effect)
        else:self.impact(effect)

    def projectile(self,p):
        target=self.units[p['target']]
        if target['hp']<=0:return
        distance=math.dist(p['projectile_position'],target['position'])
        travel=p['missile_speed']*(self.t-p['last_t'])
        if travel+target['radius']>=distance:return self.impact(p)
        p['projectile_position']=[x+(y-x)*travel/distance for x,y in zip(p['projectile_position'],target['position'])]
        p['last_t']=self.t
        self.add(self.t+self.rules['projectile_step_s'],1,'projectile',p)

    def impact(self,p):
        a,b=self.units[p['actor']],self.units[p['target']]
        if b['hp']<=0:return
        if p['effect']=='heal':
            healed=min(b['max_hp']-b['hp'],p['amount']);b['hp']+=healed;b['hp_healed']+=healed
            return self.record('heal',actor=p['actor'],target=p['target'],amount=healed)
        if p['effect']=='shield':
            b['shields'].append(dict(type='all',amount=p['amount'],remaining_s=self.t+p['duration_s']))
            return self.record('shield',actor=p['actor'],target=p['target'],amount=p['amount'])
        if not p.get('proc_generated'):
            self.mechanics.notify(self,'before_damage',p)
            if self.boundary:return
        d=p['damage'].get('by_target_kind',{}).get(b['kind'],p['damage'])
        raw=d['base']+d['target_current_hp_ratio']*b['hp']+d['target_max_hp_ratio']*b['max_hp']
        multiplier=d.get('mitigation_multiplier')
        if multiplier is None:multiplier=mitigation(b['armor']) if d['type']=='physical' else mitigation(b['magic_resist']) if d['type']=='magic' else 1
        amount=raw*multiplier
        for shield in b['shields']:
            if shield['type'] in ('all',d['type']) and shield['remaining_s']>self.t:
                absorbed=min(amount,shield['amount']);shield['amount']-=absorbed;amount-=absorbed
        actual=min(b['hp'],amount);b['hp']-=actual;b['hp_damage']+=actual
        self.record('damage',actor=p['actor'],target=p['target'],hp_damage=actual,damage_type=d['type'])
        if b['hp']<=0:self.death(p['target'],p['actor'])
        if not p.get('proc_generated') and not self.boundary:
            self.mechanics.notify(self,'attack_hit' if p.get('label')=='attack' else 'spell_hit',p)
            if b['hp']<=0 and b['kind'] in MINIONS:self.mechanics.notify(self,'minion_kill',p)

    def death(self,target,killer):
        u=self.units[target];u['motion']=None;u['token']+=1
        u['phase']='dead'
        self.record('death',actor=target,killer=killer)
        if u['kind']=='hero':return self.stop('hero_death_rewards_and_respawn_need_adapter')
        a=self.units[killer]
        if a['kind']=='hero' and a['side']!=u['side']:a['gold_gain']+=u['gold_reward']*a['gold_multiplier']
        eligible=[(uid,h) for uid,h in self.units.items() if h['kind']=='hero' and h['side']!=u['side'] and
            ((h['hp']>0 and math.dist(h['position'],u['position'])<=self.rules['xp_range']) or (uid==killer and self.rules['last_hitter_xp_outside_range']))]
        for uid,h in eligible:
            value=u['xp_reward']*self.rules['solo_xp_multiplier']*h['xp_multiplier'];h['xp']+=value;h['xp_gain']+=value
            self.record('xp',actor=uid,target=target,amount=value)
            if h['xp']>=h['next_level_xp']:self.stop('level_up_requires_new_stats_and_skill_choice:'+uid)
        if any(v['hp']>0 and v['kind'] in MINIONS and v.get('locked_target')==target for v in self.units.values()):
            self.stop('locked_target_death_requires_immediate_retarget')

    def run(self):
        while self.queue and self.queue[0][0]<=self.end+1e-9:
            t,_,_,kind,data=heapq.heappop(self.queue);self.advance(min(t,self.end));self.count+=1
            if self.count>100000:raise ValueError('event budget exceeded')
            if kind=='command':self.command(data)
            elif kind=='auto':
                u=self.units[data['actor']]
                if u['hp']>0:self.command(dict(data,kind='attack',target=u['locked_target']),auto=True)
            elif kind=='launch':self.launch(data)
            elif kind=='impact':self.impact(data)
            elif kind=='projectile':self.projectile(data)
            if self.boundary:break
        if not self.boundary:self.advance(self.end)
        metrics={}
        for uid,u in self.units.items():
            if u['kind']!='hero':continue
            initial=self.initial[uid]
            metrics[u['side']]=dict(gold_gain=u['gold_gain'],xp_gain=u['xp_gain'],hp_damage=u['hp_damage'],
                hp_deficit_change=(u['max_hp']-u['hp'])-(initial['max_hp']-initial['hp']),hp_end=u['hp'],
                mana_spent=u['mana_spent'],mana_end=u['mana'],
                cooldown_remaining_s=sum(max(0,t-self.t) for t in u['skill_ready'].values()),
                shield_remaining=sum(s['amount'] for s in u['shields']),
                xp_to_next_level=max(0,u['next_level_xp']-u['xp']),
                pending_enemy_gold=sum(v['gold_reward']*u['gold_multiplier'] for v in self.units.values() if v['kind'] in MINIONS and v['side']!=u['side'] and v['hp']>0),
                pending_enemy_xp=sum(v['xp_reward']*self.rules['solo_xp_multiplier']*u['xp_multiplier'] for v in self.units.values() if v['kind'] in MINIONS and v['side']!=u['side'] and v['hp']>0))
        for uid,u in self.units.items():
            if u['kind']=='hero':metrics[u['side']].update({'resource:'+key:value for key,value in u['resources'].items()})
            u['stale_labels']=sorted(u['stale_labels'])
        return dict(end_s=self.t,boundary=self.boundary,metrics=metrics,mechanics=self.mechanics.summary(self.t),legal=not any(e['kind']=='illegal_action' for e in self.log),events=self.log,
            terminal_units=self.units,pending_events=[dict(at_s=t,kind=k,source=d.get('actor'),target=d.get('target')) for t,_,_,k,d in self.queue if t>self.t])


def compare(spec):
    validate(spec)
    end=min(spec['horizon_s'],spec['rules'].get('valid_until_s',spec['horizon_s']))
    combinations=[(a,b) for a in spec['policies']['blue'] for b in spec['policies']['red']]
    samples=(spec.get('stochastic') or {}).get('samples',1)
    trials=[Rollout(spec,a,b,end,scenario).run() for a,b in combinations for scenario in range(samples)]
    common=min([end]+[r['end_s'] for r in trials])
    # All branches are recomputed with the SAME endpoint, even if only one
    # branch leveled or exposed an unsupported state transition first.
    rows=[]
    for a,b in combinations:
        scenarios=[Rollout(spec,a,b,common,i).run() for i in range(samples)]
        row=dict(blue_policy=a['id'],red_policy=b['id'],**deepcopy(scenarios[0]))
        if samples>1:
            row['scenario_results']=scenarios;row['legal']=all(s['legal'] for s in scenarios)
            row['metric_scenario_ranges']={}
            for side in SIDES:
                row['metric_scenario_ranges'][side]={}
                keys=set().union(*(s['metrics'][side] for s in scenarios))
                for key in sorted(keys):
                    values=[s['metrics'][side].get(key,0) for s in scenarios]
                    if any(v is None for v in values):continue
                    row['metrics'][side][key]=sum(values)/samples
                    ordered=sorted(values)
                    row['metric_scenario_ranges'][side][key]=dict(min=ordered[0],max=ordered[-1],
                        p05=ordered[int(.05*(samples-1))],p95=ordered[int(.95*(samples-1))])
        rows.append(row)
    return dict(schema_version=1,status='conditional_finite_window_comparison',entry_time_s=spec['entry_time_s'],
        requested_horizon_s=spec['horizon_s'],effective_horizon_s=common,
        valid_through_source_time_s=spec['entry_time_s']+common,
        replan_reasons=[r['boundary'] for r in trials if r['boundary']],
        declared_boundary=spec['rules'].get('boundary_reason'),
        branches=rows,samples=samples,terminal_state_requires_refresh=bool(any(r['boundary'] for r in trials)),probability_note='Empirical frequencies or declared posterior scenarios, not calibrated win probabilities or player skill confidence.',patch=spec['rules']['patch'],sources=spec['rules']['sources'],
        assumptions=spec['rules'].get('assumptions',[]),
        limitations=['No built-in champion/rune/item data or full minion AI.',
            'Only verified inactive effects or declared generic effect adapters; targeted casts or scoped joint-hit probability models, and clear straight paths.',
            'Level-up, triggering minion aggro, unknown retargets or declared boundaries require a fresh state.',
            'Unsettled minions and pending attacks are terminal state, not lost or already earned rewards.',
            'Projectile arrival is numerically integrated within the declared time step; not server tick reconstruction.',
            'No player skill score or win/loss classification is inferred.'])
