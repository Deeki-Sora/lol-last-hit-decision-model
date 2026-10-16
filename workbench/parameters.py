"""Common arithmetic with explicit event inputs/overrides; no champion-specific algorithms."""
import math
from .core import read_json
from .catalog import catalog_path, champion_details
from .native_data import native_data
from .stat_arithmetic import STAT_FIELDS, subtotal


def effective_parameters(directory,reference,source_time_s,fetch_native=False):
    state=reference.get('effective_state',{});lookup_notes=[]
    champion=reference.get('champion');version=reference.get('patch');native={}
    if champion and version:
        path=catalog_path(directory,version).parent/f'native_{champion}.json'
        try:
            if fetch_native:native=native_data(directory,version,champion)
            elif path.exists():native=read_json(path)
        except (OSError,ValueError,KeyError) as error:lookup_notes.append('native_stat_lookup:'+str(error))
    age=None if reference.get('selected_at_source_time_s') is None else source_time_s-reference['selected_at_source_time_s']
    fresh=age is not None and math.isclose(age,0,abs_tol=1e-6)
    # Inventory and level persist as last-known configuration; transient observations do not.
    overrides=state.get('stat_overrides',{}) if fresh else {}
    base_stats=reference.get('base_stats',{});merged_base=dict(base_stats,**native.get('base_stats',{}))
    differences={key:dict(data_dragon=base_stats.get(key),native=value) for key,value in native.get('base_stats',{}).items()
                 if key in base_stats and not math.isclose(base_stats[key],value,rel_tol=1e-6,abs_tol=1e-6)}
    if differences:lookup_notes.append('Native character fields take precedence where the pinned data sources disagree; inspect base_stat_differences.')
    arithmetic_reference=dict(reference,effective_state=state if fresh else dict(state,event_state={}))
    if merged_base:
        from .loadouts import base_growth_reference
        arithmetic_reference['base_growth_reference']=base_growth_reference(merged_base,state.get('level'))
    auto,trace,notes=subtotal(arithmetic_reference,native,overrides);notes.extend(lookup_notes)
    if not native:notes.append('Native character cross-check unavailable; download it or verify the effective attributes manually.')
    if (state.get('level') or 0)>1 and merged_base.get('attackdamageperlevel')==0 and 'attackdamageperlevel' not in native.get('base_stats',{}):
        auto['attack_damage']=None;notes.append('zero_attack_damage_growth_requires_native_cross_check_or_effective_stat_override')
    stats={key:dict(value=overrides[key],source='user_override',automatic_value=auto[key]) if overrides.get(key) is not None
           else dict(value=auto[key],source='automatic_static',automatic_value=auto[key]) for key in STAT_FIELDS}
    attack_speed=stats['attack_speed']['value'];attack_period=1/attack_speed if attack_speed is not None and attack_speed>0 else None
    event=state.get('event_state',{})
    resource_label='unknown'
    if champion and version:resource_label=champion_details(directory,version,champion)['locales']['en_US'].get('partype','unknown')
    inferred={'mana':'mana','energy':'energy','none':'none','no resource':'none'}.get(resource_label.lower(),'other')
    resource_type=event.get('resource_type','auto')
    if resource_type=='auto':resource_type=inferred
    if resource_type=='none':
        for field in ('max_resource','resource_regen'):stats[field]=dict(value=None,source='not_applicable',automatic_value=auto[field])
    skills={}
    for key,skill in reference.get('spells',{}).items():
        raw=skill.get('rank_reference',{});given=event.get('skills',{}).get(key,{}) if fresh else {}
        def choose(field,default=None):return dict(value=given[field],source='event_input') if given.get(field) is not None else dict(value=default,source='static_reference' if default is not None else 'unknown')
        reduction=stats['cooldown_reduction']['value'];cooldown=raw.get('cooldown')
        cd=cooldown*(1-reduction) if cooldown is not None and reduction is not None else None
        skills[key]=dict(rank=skill.get('rank'),range=choose('range',raw.get('range')),resource_cost=choose('resource_cost',raw.get('cost')),
            base_cooldown_s=cooldown,standard_haste_cooldown_reference_s=cd,
            remaining_cooldown_s=choose('remaining_cooldown_s'),damage=choose('damage'),damage_type=given.get('damage_type'),
            per_target_cooldown_s=choose('per_target_cooldown_s'),cast_time_s=choose('cast_time_s'),missile_speed=choose('missile_speed'),
            event_inputs_are_current=fresh)
    notes.extend(['Conditional rune/passive/item effects use event inputs and effective-stat overrides; a counter does not imply an automatic stat bonus.',
        'Automatic references include ordinary growth, item stat blocks and recognized version-pinned stat shards; unique effects and champion exceptions require effective-stat overrides.',
        'Regeneration is per second; rates and penetration percentages use fractions (0.15 = 15%); bonus attack speed uses percentage points (10 = 10%).',
        'The ordinary attack-speed cap follows the patch baseline; override total attack speed for champion or buff exceptions.'])
    if age is not None and not fresh:notes.append('Only the last-known level/inventory/rune page persist; event observations and effective-stat overrides require reconfirmation at this time.')
    if not state.get('inventory_known'):notes.append('inventory_completeness_unknown')
    return dict(schema_version=1,champion=champion,patch=version,source_time_s=source_time_s,
        stats=stats,attack_period_s=attack_period,skills=skills,verified_effective_stats=False,
        hp=event.get('hp') if fresh else None,resource_value=event.get('resource_value') if fresh and resource_type!='none' else None,
        resource_type=resource_type,resource_label=resource_label,
        passive_stacks=event.get('passive_stacks') if fresh else None,shield_active=event.get('shield_active') if fresh else None,
        shield_amount=event.get('shield_amount') if fresh else None,rune_stacks=event.get('rune_stacks',{}) if fresh else {},
        observation_source=event.get('source'),observation_note=event.get('note',''),observation_age_s=age,event_inputs_are_current=fresh,
        static_trace=trace,native_stat_source=native.get('source'),base_stat_differences=differences,
        base_stat_reference=arithmetic_reference.get('base_growth_reference'),limitations=notes,decision_score=None)


def evaluate_project(directory,project,source_time_s,fetch_native=False):
    from .loadouts import configuration_at
    references=configuration_at(directory,project,source_time_s)
    return dict(schema_version=1,source_time_s=source_time_s,
        sides={side:effective_parameters(directory,references.get(side,{}),source_time_s,fetch_native) for side in ('blue','red')},decision_score=None)


def direct_range_reference(parameters,actor,skill,distance_game_units):
    """Compare a declared distance to a declared skill range. No overall safety inference."""
    if actor not in ('blue','red') or skill not in ('Q','W','E','R'):raise ValueError('invalid actor or skill')
    if isinstance(distance_game_units,bool) or not isinstance(distance_game_units,(int,float)) or not math.isfinite(distance_game_units) or distance_game_units<0:raise ValueError('invalid distance')
    source=parameters['sides'][actor];target=parameters['sides']['red' if actor=='blue' else 'blue'];profile=source['skills'].get(skill,{})
    radius=profile.get('range',{}).get('value');damage=profile.get('damage',{}).get('value');kind=profile.get('damage_type')
    resistance=target['stats']['armor' if kind=='physical' else 'magic_resist']['value'] if kind in ('physical','magic') else None
    effective_resistance=resistance
    if resistance is not None and resistance>=0:
        prefix='armor' if kind=='physical' else 'magic'
        percent=source['stats'][prefix+'_penetration_percent']['value'];flat=source['stats'][prefix+'_penetration_flat']['value']
        effective_resistance=None if percent is None or flat is None else max(0,resistance*(1-percent)-flat)
    if damage is None:post=None
    elif kind=='true':post=damage
    elif effective_resistance is not None:post=damage*(100/(100+effective_resistance) if effective_resistance>=0 else 2-100/(100-effective_resistance))
    else:post=None
    fresh=source['event_inputs_are_current'];cost=profile.get('resource_cost',{}).get('value');resource=source['resource_value']
    affordable=True if cost==0 else None if not fresh or resource is None or cost is None else resource>=cost
    return dict(actor=actor,skill=skill,distance_reference_game_units=distance_game_units,
        skill_learned=None if profile.get('rank') is None else profile['rank']>0,
        range_reference_game_units=radius,range_margin=None if radius is None else radius-distance_game_units,
        direct_range_reference=None if radius is None else distance_game_units<=radius,
        remaining_cooldown_s=profile.get('remaining_cooldown_s',{}).get('value') if fresh else None,
        same_target_remaining_cooldown_s=profile.get('per_target_cooldown_s',{}).get('value') if fresh else None,
        damage_before_mitigation=damage if fresh else None,
        damage_after_resistance_reference=post if fresh else None,resistance_before_penetration=resistance,
        resistance_after_penetration_reference=effective_resistance,resource_affordable=affordable,
        source_inputs_are_current=fresh,overall_safety=None,decision_score=None,
        limitations=['A range comparison does not resolve hitboxes, intervening units, indirect mobility, shields, passives or other damage modifiers.'])
