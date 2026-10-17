"""Optional finite-window planning; imports solvers only when explicitly chosen."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import math
from .core import read_json,write_json


def availability():
    return dict(compare={'installed':True,'install':None},
        zero_sum={'installed':importlib.util.find_spec('scipy') is not None,
            'url':'https://pypi.org/project/scipy/','documentation':'https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html',
            'install':'python -m pip install -r requirements-game.txt'},
        general_sum={'installed':importlib.util.find_spec('nashpy') is not None,
            'url':'https://pypi.org/project/nashpy/','documentation':'https://nashpy.readthedocs.io/en/stable/',
            'install':'python -m pip install -r requirements-game.txt'},
        auto_download=False,note='Dependencies are optional; selecting a link does not install or run a package.')


def draft(project,annotations,frame_id,directory=None):
    frame=next((f for f in project['frames'] if f['id']==frame_id),None)
    if frame is None:raise ValueError('unknown frame')
    observations=annotations.get('frames',{}).get(frame_id,{})
    configuration=project.get('configuration')
    if configuration:
        past=[s for s in configuration['snapshots'] if s['source_time_s']<=frame['source_time_s']]
        configuration=dict(match_setup=configuration['match_setup'],
            selected_snapshot=max(past,key=lambda s:s['source_time_s']) if past else None)
    dead=set()
    for f in project['frames']:
        if f['source_time_s']>frame['source_time_s']:break
        for uid,u in annotations.get('frames',{}).get(f['id'],{}).get('units',{}).items():
            if u.get('alive') is False or u.get('action')=='death':dead.add(uid)
    units={}
    for u in project['units']:
        if u['id'] in dead or (u.get('first_seen_s') is not None and u['first_seen_s']>frame['source_time_s']):continue
        fields=['hp','max_hp','radius','move_speed','hp_regen_s','armor','magic_resist','mana','max_mana','mana_regen_s','resource_model','phase']
        unit={k:None for k in fields}
        unit.update(side=u['side'],kind=u['kind'],position=[None,None],effects_inactive_verified=False,
            effects_scope_note='',movement=dict(verified=False,destination=None),skills={},shields=[],attack=dict(attack_speed=None,period_s=None,windup_s=None,
                range=None,range_mode='edge_to_edge',missile_speed=None,ready_in_s=None,
                damage=dict(type='physical',base=None,target_current_hp_ratio=None,target_max_hp_ratio=None)))
        if u['kind']=='hero':unit.update(level=None,xp=None,next_level_xp=None,gold_multiplier=None,xp_multiplier=None)
        else:unit.update(gold_reward=None,xp_reward=None,locked_target=None,idle_verified_until_s=None)
        units[u['id']]=unit
    if directory is not None:
        from .loadouts import configuration_at
        hero_references=configuration_at(directory,project,frame['source_time_s'])
        from .parameters import evaluate_project
        event_parameters=evaluate_project(directory,project,frame['source_time_s']) if project.get('configuration') else None
        from .minion_data import load_profiles
        patch=hero_references.get('blue',{}).get('patch')
        minion_profiles=load_profiles(directory,patch,fetch=False) if patch else None
    else:hero_references={};minion_profiles=None
    if directory is None:event_parameters=None
    if event_parameters:
        for uid,unit in units.items():
            if unit['kind']!='hero':continue
            values=event_parameters['sides'][unit['side']];stats=values['stats']
            for field,param in [('max_hp','max_hp'),('move_speed','move_speed'),('armor','armor'),('magic_resist','magic_resist'),('hp_regen_s','health_regen')]:unit[field]=stats[param]['value']
            unit['hp']=values['hp'];unit['attack']['attack_speed']=stats['attack_speed']['value']
            unit['attack']['period_s']=values['attack_period_s'];unit['attack']['range']=stats['attack_range']['value']
            unit['attack']['damage']['base']=stats['attack_damage']['value']
            if values['resource_type'] in ('mana','energy'):
                unit['resource_model']='finite';unit['mana']=values['resource_value'];unit['max_mana']=stats['max_resource']['value'];unit['mana_regen_s']=stats['resource_regen']['value']
            # Non-mana meters can have their own effects; do not silently erase them as 'no resource'.
            elif values['resource_type']=='none':unit.update(resource_model='none',mana=0.,max_mana=0.,mana_regen_s=0.)
    if minion_profiles:
        for unit in units.values():
            profile=minion_profiles.get('profiles',{}).get(unit['kind'])
            if not profile:continue
            for field in ('max_hp','move_speed','radius','hp_regen_s','armor','magic_resist'):unit[field]=profile.get(field)
            unit['hp']=profile.get('hp')
            unit['attack'].update(attack_speed=profile.get('attack_speed'),period_s=profile.get('period_s'),
                windup_s=profile.get('windup_s'),range=profile.get('range'),missile_speed=profile.get('missile_speed'),
                damage=dict(type='physical',base=profile.get('damage'),target_current_hp_ratio=0,target_max_hp_ratio=0))
            unit.update(gold_reward=profile.get('gold_reward'),xp_reward=profile.get('xp_reward'),
                minion_profile_source=profile.get('source_kind'),minion_profile_verified=profile.get('verified',False))
    return dict(schema_version=1,enabled=False,frame_id=frame_id,entry_time_s=frame['source_time_s'],horizon_s=3.,
        backend='compare',rules=dict(verified=False,patch=configuration['match_setup']['patch'] if configuration else None,sources=[],geometry='unverified_pixels',
            unit_scope_verified=False,unit_scope_note='',level_up='replan',retarget='replan',hero_aggro='replan',aggro_triggers=[],unmodelled_effects='replan',
            pathing='unverified',xp_mode='solo_lane',xp_range=None,solo_xp_multiplier=None,
            last_hitter_xp_outside_range=None,projectile_step_s=.02,unsupported_mechanics=[],assumptions=[]),
        units=units,in_progress_actions=[],committed_attacks=[],
        policies={side:[dict(id='wait',commands=[dict(at_s=0,kind='wait')])] for side in ('blue','red')},
        utility=None,evaluation=dict(two_layer=False,omega=.6,risk_alpha=.2,risk_lambda=.25,weights={},scales={},strategy={},execution={},confidence={}),
        belief=dict(states=[],updates=[]),mechanism_profiles=[],schedule_targets=[],schedule_actor_ready_s=0.,schedule_actor_period_s=0.,schedule_max_schedules=256,
        stochastic=dict(samples=16,seed=0,models=[],effects=[]),observations=dict(frame_id=frame_id,image=frame['image'],health_bar_pixels=observations,
            match_configuration=configuration,
            selected_hero_references=hero_references,
            event_parameters=event_parameters,
            minion_profiles=minion_profiles,
            minion_behavior_reference={kind:profile.get('behavior') for kind,profile in (minion_profiles or {}).get('profiles',{}).items() if profile.get('behavior')},
            note='Observation references only. Ground positions, effective rules and parameters must be verified; pixels are not copied as game positions.'))


def scalars(task,result):
    config=task.get('utility')
    if not config or not config.get('reference') or not config.get('terminal_scope_note'):
        raise ValueError('solver requires declared utility reference, per-side weights/scales and terminal_scope_note')
    if not math.isclose(config.get('valid_for_entry_time_s',-1),task['entry_time_s']) or not math.isclose(config.get('valid_for_horizon_s',-1),result['effective_horizon_s']):
        raise ValueError('utility must bind valid_for_entry_time_s and valid_for_horizon_s to this effective window; run compare first after any boundary change')
    if result['effective_horizon_s']<=0:raise ValueError('no positive common validity window; replan first')
    if result['terminal_state_requires_refresh']:
        raise ValueError('boundary state needs refreshed mechanics/stats; use compare evidence and start a new verified task before matrix solving')
    if any(not r['legal'] for r in result['branches']):raise ValueError('illegal candidate commands must be corrected before solving a payoff matrix')
    matrices={side:[] for side in ('blue','red')}
    columns=len(task['policies']['red'])
    for side in ('blue','red'):
        weights=config[side]['weights'];scales=config[side]['scales']
        if not weights:raise ValueError('utility weights must be explicit')
        values=[]
        for branch in result['branches']:
            metric=branch['metrics'][side];value=0.
            for key,weight in weights.items():
                scale=scales[key]
                if not isinstance(weight,(int,float)) or not math.isfinite(weight) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0:
                    raise ValueError('utility weights must be finite and scales positive')
                if key not in metric or metric[key] is None:raise ValueError('unknown/unavailable utility metric: '+key)
                if key.startswith('pending_'):raise ValueError('pending resources cannot be treated as already earned; use terminal value assumptions')
                value+=weight*metric[key]/scale
            terminal=branch.get('terminal_value',{}).get(side,0.)
            values.append(value+terminal)
        matrices[side]=[values[i:i+columns] for i in range(0,len(values),columns)]
    return matrices


def run_task(task):
    if task.get('enabled') is not True:
        return dict(status='disabled',note='Optional planning is off; ordinary tables and evaluation remain available.')
    from algorithms.short_horizon import compare
    backend=task.get('backend','compare')
    if backend not in ('compare','zero_sum','general_sum'):raise ValueError('unknown backend')
    if not availability()[backend]['installed']:
        raise ValueError('Optional solver not installed. '+availability()[backend]['install'])
    result=compare(task)
    from algorithms.risk_value import evaluate_policy_branches, two_layer_score
    evaluation=task.get('evaluation') or {}
    result['decision_analysis']={side:evaluate_policy_branches(result['branches'],side,
        (evaluation.get('weights') or {}).get(side),
        (evaluation.get('scales') or {}).get(side),evaluation.get('risk_alpha',.2),evaluation.get('risk_lambda',.25))
        for side in ('blue','red')}
    result['player_scores']={side:two_layer_score((evaluation.get('strategy') or {}).get(side,{}),
        (evaluation.get('execution') or {}).get(side,{}),evaluation.get('omega',.6),
        (evaluation.get('confidence') or {}).get(side,1.)) if evaluation.get('two_layer') else None for side in ('blue','red')}
    if task.get('mechanism_profiles'):
        from algorithms.mechanism_adapter import explain_profile,validate_profile
        for profile in task['mechanism_profiles']:validate_profile(profile)
        result['mechanism_profiles']=[explain_profile(profile) for profile in task['mechanism_profiles']]
    if task.get('belief') and task['belief'].get('states'):
        from algorithms.belief_state import roll_forward
        result['belief_trace']=roll_forward(task['belief']['states'],task['belief'].get('updates',[]))
    if task.get('schedule_targets'):
        from algorithms.joint_scheduler import best_schedule
        schedule=task['schedule_targets']
        result['joint_schedule_reference']=best_schedule(schedule,task.get('schedule_actor_ready_s',0),
            task.get('schedule_actor_period_s',0),result['effective_horizon_s'],task.get('schedule_max_schedules',256))
    # Boundary valuation is a declared external assumption, never inferred
    # from lost CS or unfinished minions. Preserve it alongside raw accounts.
    terminal=task.get('terminal_values',{})
    for branch in result['branches']:
        key=json.dumps([branch['blue_policy'],branch['red_policy']],separators=(',',':'))
        entry=terminal.get(key)
        if entry:
            if not entry.get('reason'):raise ValueError('terminal valuation requires a reason')
            for side in ('blue','red'):
                value=entry[side]
                if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('terminal value must be finite')
            branch['terminal_value']={side:entry[side] for side in ('blue','red')}
            branch['terminal_value_reason']=entry['reason']
    result['backend']=backend
    result['terminal_valuation_status']='externally_declared' if terminal else 'unpriced_local_state_only'
    if backend=='compare':return result
    matrices=scalars(task,result);result['utility_matrices']=matrices;result['utility_config']=task['utility']
    if backend=='zero_sum':
        if task.get('relative_resource_proxy') is not True:raise ValueError('zero_sum requires relative_resource_proxy=true; a lane is not inherently zero-sum')
        from .operations import solve_matrix
        difference=[[a-b for a,b in zip(ar,br)] for ar,br in zip(matrices['blue'],matrices['red'])]
        result['solver']=solve_matrix(dict(game_type='two_player_zero_sum',assessment_reference=task['utility']['reference'],payoff_matrix=difference))
    else:
        import nashpy
        import numpy as np
        if len(result['branches'])>16:raise ValueError('general-sum support enumeration is limited to 16 cells; reduce the policy set')
        equilibria=[]
        for a,b in nashpy.Game(np.asarray(matrices['blue']),np.asarray(matrices['red'])).support_enumeration():
            equilibria.append(dict(blue_policy=a.tolist(),red_policy=b.tolist()))
        result['solver']=dict(method='support_enumeration',equilibria=equilibria,
            note='Conditional finite game only; degenerate games may need another solver. No unique recommendation is implied.')
    result['solver_scope']='Finite window and declared terminal assumptions; not victory, defeat, full-match optimality or a player skill score.'
    return result


def save_run(directory,task):
    directory=Path(directory)
    if task.get('enabled') is not True:return run_task(task)
    if (directory/'project.json').is_file():
        project=read_json(directory/'project.json')
        frame=next((f for f in project['frames'] if f['id']==task.get('frame_id')),None)
        if frame is None or not math.isclose(frame['source_time_s'],task['entry_time_s']):raise ValueError('planning frame_id/entry_time_s must match this workspace observation')
        roster={u['id']:u for u in project['units']}
        if any(uid not in roster or (roster[uid]['side'],roster[uid]['kind'])!=(u['side'],u['kind']) for uid,u in task['units'].items()):
            raise ValueError('task unit identity/side/kind must match the workspace roster')
    result=run_task(task)
    if result['status']=='disabled':return result
    directory=directory/'game_analysis'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'task.json',task)
    result['task_sha256']=hashlib.sha256((directory/'task.json').read_bytes()).hexdigest()
    root=Path(__file__).resolve().parents[1]
    result['engine_sha256']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['algorithms/short_horizon.py','algorithms/probabilistic_mechanics.py','workbench/game_tools.py']}
    write_json(directory/'result.json',result)
    return dict(result=result,folder=directory.name)
