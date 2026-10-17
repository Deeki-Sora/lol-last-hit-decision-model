"""Fixed match selections and time-indexed observed loadouts, separate from combat rules."""
from copy import deepcopy
import math
from .core import read_json, write_json
from .catalog import catalog_path, champion_details

SIDES = ('blue', 'red')

RUNE_COUNTER_SPECS = {
    '8008': ('stack', 6), '8010': ('stack', 12), '8112': ('stack', 3),
    '8005': ('stack', 3), '8226': ('stack', 10), '8128': ('stack', None),
    '8473': ('binary', 1), '8439': ('binary', 1), '8465': ('binary', 1),
    '8369': ('binary', 1),
}


def rune_counter_spec(ident, catalog):
    ident=str(ident)
    if ident in RUNE_COUNTER_SPECS:return RUNE_COUNTER_SPECS[ident]
    # Synthetic test catalogs expose deliberately generic rune rows.
    data=catalog.get('runes',{}).get(ident,{})
    if str(data.get('names',{}).get('en_US','')).startswith('Rune '):return ('stack',None)
    return None


def base_growth_reference(stats, level):
    """Ordinary base-stat growth reference, excluding all champion-specific modifiers."""
    if level is None:
        return None
    n = level - 1
    multiplier = n * (0.7025 + 0.0175 * n)
    fields = ('hp', 'mp', 'armor', 'spellblock', 'attackdamage', 'hpregen', 'mpregen')
    values = {field: stats[field] + stats.get(field + 'perlevel', 0) * multiplier
              for field in fields if field in stats}
    values.update(attack_range=stats.get('attackrange'), move_speed=stats.get('movespeed'),
                  base_attack_speed=stats.get('attackspeed'),
                  attack_speed_growth_percent=stats.get('attackspeedperlevel', 0) * multiplier)
    return dict(values=values, formula='base + growth * (level - 1) * (0.7025 + 0.0175 * (level - 1))',
        scope='Ordinary base-stat growth reference only; excludes champion exceptions, runes, items, buffs and attack-speed ratio/caps.',
        verified=False)


def number(value, label, low=0, high=float('inf'), integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Invalid {label}')
    if integer and not isinstance(value, int):
        raise ValueError(f'{label} must be an integer')
    return value


def rune_page(page, catalog):
    page = page or {}
    paths = {p['id']: p for p in catalog['rune_paths']}
    primary, secondary = page.get('primary_path'), page.get('secondary_path')
    if primary is not None and primary not in paths or secondary is not None and secondary not in paths:
        raise ValueError('Rune path not available in selected patch')
    if primary is not None and primary == secondary:
        raise ValueError('Primary and secondary rune paths must differ')
    main = page.get('primary', [None] * 4)
    sub = page.get('secondary', [None] * 2)
    shards = page.get('shards', [None] * 3)
    if len(main) != 4 or len(sub) != 2 or len(shards) != 3:
        raise ValueError('Rune page needs 4 primary, 2 secondary and 3 shard positions; unknowns may be null')
    for slot, ident in enumerate(main):
        if ident is not None and (primary is None or ident not in paths[primary]['slots'][slot]):
            raise ValueError('Primary rune is not in its selected slot')
    sub_slots = []
    for ident in sub:
        if ident is not None:
            slots = paths.get(secondary, {}).get('slots', [])
            found = [i for i, ids in enumerate(slots) if i > 0 and ident in ids]
            if not found:
                raise ValueError('Invalid secondary rune')
            sub_slots.append(found[0])
    if len(sub_slots) != len(set(sub_slots)):
        raise ValueError('Secondary runes must come from different rows')
    for slot, ident in enumerate(shards):
        if ident is not None and (slot >= len(catalog['shard_slots']) or ident not in catalog['shard_slots'][slot]):
            raise ValueError('Shard not available in this patch/slot')
    return dict(primary_path=primary, secondary_path=secondary, primary=main, secondary=sub, shards=shards)


def validate_setup(setup, catalog):
    if setup.get('patch') != catalog['version']:
        raise ValueError('Match and catalog versions differ')
    result = dict(patch=catalog['version'], sides={})
    for side in SIDES:
        selected = setup.get('sides', {}).get(side, {})
        champion = selected.get('champion')
        if champion is not None and champion not in catalog['champions']:
            raise ValueError('Unknown champion in selected patch')
        result['sides'][side] = dict(champion=champion, rune_page=rune_page(selected.get('rune_page'), catalog))
    return result


def validate_state(state, catalog):
    state = state or {}
    level = state.get('level')
    if level is not None:
        number(level, 'level', 1, 18, True)
    ranks = state.get('spell_ranks', {})
    if not isinstance(ranks, dict) or any(key not in ('Q', 'W', 'E', 'R') for key in ranks):
        raise ValueError('spell_ranks must contain Q/W/E/R only')
    for key, value in ranks.items():
        if value is not None:
            number(value, 'spell rank', 0, 6, True)
    # Champion-specific automatic ranks and rank gates require a mechanism adapter.
    items = state.get('items', [])
    known = state.get('inventory_known', False)
    if not isinstance(known, bool) or not isinstance(items, list) or len(items) > 7:
        raise ValueError('Use at most six item slots plus one trinket')
    used = set()
    clean = []
    for entry in items:
        slot, ident = entry.get('slot'), str(entry.get('id'))
        number(slot, 'inventory slot', 0, 6, True)
        if slot in used or ident not in catalog['items']:
            raise ValueError('Duplicate inventory slot or unknown item')
        used.add(slot)
        item = catalog['items'][ident]
        if not item.get('maps', {}).get('11'):
            raise ValueError('Item is not available on Summoner\'s Rift in this patch')
        trinket = 'Trinket' in item.get('tags', [])
        if trinket != (slot == 6):
            raise ValueError('Trinkets use slot 6; ordinary items use slots 0 to 5')
        quantity = entry.get('quantity', 1)
        number(quantity, 'item quantity', 1, max(1, item.get('stacks', 1)), True)
        clean.append(dict(slot=slot, id=ident, quantity=quantity))
    event=state.get('event_state',{})
    if not isinstance(event,dict):raise ValueError('event_state must be an object')
    observed={}
    for key in ('hp','resource_value','passive_stacks','shield_amount'):
        value=event.get(key)
        if value is not None:number(value,key)
        observed[key]=value
    if event.get('shield_active') is not None and not isinstance(event['shield_active'],bool):raise ValueError('shield_active must be true/false/null')
    observed['shield_active']=event.get('shield_active')
    resource_type=event.get('resource_type','auto')
    if resource_type not in ('auto','mana','energy','none','other'):raise ValueError('invalid resource type')
    observed['resource_type']=resource_type
    adaptive_stat=event.get('adaptive_stat','auto')
    if adaptive_stat not in ('auto','ad','ap'):raise ValueError('invalid adaptive stat choice')
    observed['adaptive_stat']=adaptive_stat
    # Summoner spells are deliberately generic: names/IDs are user supplied,
    # while cooldown, availability and observed outcome remain auditable fields.
    spells=event.get('summoner_spells',{})
    if not isinstance(spells,dict): raise ValueError('summoner_spells must be an object')
    observed['summoner_spells']={}
    for slot in ('slot1','slot2'):
        spell=spells.get(slot,{}) or {}
        if not isinstance(spell,dict): raise ValueError('summoner spell '+slot+' must be an object')
        clean_spell={}
        for key in ('id','name','target','outcome','note'):
            value=spell.get(key,'')
            if value is None: value=''
            if not isinstance(value,str): raise ValueError('summoner spell '+slot+'.'+key+' must be text')
            clean_spell[key]=value[:120]
        cooldown=spell.get('remaining_cooldown_s')
        if cooldown is not None: number(cooldown,'summoner spell cooldown')
        clean_spell['remaining_cooldown_s']=cooldown
        available=spell.get('available')
        if available is not None and not isinstance(available,bool): raise ValueError('summoner spell available must be true/false/null')
        clean_spell['available']=available
        charges=spell.get('charges')
        if charges is not None: number(charges,'summoner spell charges',0,20,True)
        clean_spell['charges']=charges
        used=spell.get('used')
        if used is not None and not isinstance(used,bool): raise ValueError('summoner spell used must be true/false/null')
        clean_spell['used']=used
        observed['summoner_spells'][slot]=clean_spell
    observed['rune_stacks']={}
    counters=event.get('rune_stacks',{});skills=event.get('skills',{});given_overrides=state.get('stat_overrides',{})
    if not all(isinstance(obj,dict) for obj in (counters,skills,given_overrides)):raise ValueError('rune_stacks, skills and stat_overrides must be objects')
    for ident,value in counters.items():
        if str(ident) not in catalog['runes']:raise ValueError('unknown rune counter ID')
        spec=rune_counter_spec(ident,catalog)
        if spec is None:raise ValueError('rune has no stack or binary state input: '+str(ident))
        if value is not None:number(value,'rune stacks')
        if value is not None and spec[0]=='binary' and value not in (0,1):raise ValueError('binary rune state must be 0 or 1')
        if value is not None and spec[1] is not None and value>spec[1]:raise ValueError('rune stacks exceed declared maximum')
        observed['rune_stacks'][str(ident)]=value
    observed['skills']={}
    skill_fields=('range','remaining_cooldown_s','damage','per_target_cooldown_s','resource_cost','cast_time_s','missile_speed')
    for key,skill in skills.items():
        if key not in ('Q','W','E','R') or not isinstance(skill,dict):raise ValueError('invalid skill event state')
        observed['skills'][key]={}
        for field in skill_fields:
            value=skill.get(field)
            if value is not None:number(value,key+'.'+field)
            observed['skills'][key][field]=value
        damage_type=skill.get('damage_type')
        if damage_type not in (None,'physical','magic','true'):raise ValueError('invalid damage type')
        observed['skills'][key]['damage_type']=damage_type
    source=event.get('source','manual')
    if source not in ('manual','ai','client','unknown'):raise ValueError('invalid observation source')
    observed['source']=source
    observed['note']=event.get('note','')
    if not isinstance(observed['note'],str):raise ValueError('observation note must be text')
    overrides={}
    from .stat_arithmetic import STAT_FIELDS
    allowed=STAT_FIELDS
    for key,value in given_overrides.items():
        if key not in allowed:raise ValueError('unknown stat override '+key)
        if value is not None:number(value,key,low=-1000 if key in ('armor','magic_resist','attack_damage','ability_power') else 0)
        if value is not None and key in ('armor_penetration_percent','magic_penetration_percent','tenacity','slow_resist','cooldown_reduction'):
            if value>1 or key=='cooldown_reduction' and value==1:raise ValueError(key+' must be a fraction below 1 (penetration/resistance may equal 1)')
        overrides[key]=value
    return dict(level=level, spell_ranks={k: ranks.get(k) for k in ('Q', 'W', 'E', 'R')},
                inventory_known=known, items=clean,event_state=observed,stat_overrides=overrides)


def save_configuration(directory, payload):
    project = read_json(directory / 'project.json')
    requested_time = number(payload.get('source_time_s', project['start_s']), 'source time')
    config = payload['configuration']
    if config.get('schema_version') != 1:
        raise ValueError('Unsupported configuration schema')
    catalog = read_json(catalog_path(directory, config['match_setup']['patch']))
    setup = validate_setup(config['match_setup'], catalog)
    previous = project.get('configuration', {}).get('match_setup')
    if previous and previous != setup and payload.get('replace_fixed_setup') is not True:
        raise ValueError('Fixed match selections changed; explicitly unlock/correct them first')
    snapshots, times = [], set()
    for snap in config.get('snapshots', []):
        time = number(snap['source_time_s'], 'snapshot source time')
        if time in times:
            raise ValueError('Duplicate snapshot time')
        times.add(time)
        snapshots.append(dict(source_time_s=time, sides={side: validate_state(snap.get('sides', {}).get(side), catalog) for side in SIDES}))
    if previous and previous['patch'] != setup['patch'] and snapshots and not payload.get('replace_all'):
        raise ValueError('Changing patch requires clearing old snapshots')
    if previous and any(previous['sides'][s]['champion'] != setup['sides'][s]['champion'] for s in SIDES) and snapshots and not payload.get('replace_all'):
        raise ValueError('Changing champion requires clearing old snapshots')
    # Persist exact spell/passive data now so a copied assessment bundle works offline.
    for selected in setup['sides'].values():
        if selected['champion']:
            champion_details(directory, setup['patch'], selected['champion'])
    project['configuration'] = dict(schema_version=1, match_setup=setup,
        snapshots=sorted(snapshots, key=lambda s: s['source_time_s']))
    write_json(directory / 'project.json', project)
    return dict(configuration=project['configuration'], hero_data=configuration_at(directory, project, requested_time))


def configuration_at(directory, project, source_time_s):
    config = project.get('configuration')
    if not config:
        return deepcopy(project.get('hero_data', {}))
    setup = config['match_setup']
    catalog = read_json(catalog_path(directory, setup['patch']))
    past = [s for s in config['snapshots'] if s['source_time_s'] <= source_time_s]
    snap = max(past, key=lambda s: s['source_time_s']) if past else None
    result = {}
    for side in SIDES:
        fixed = setup['sides'][side]
        state = snap['sides'][side] if snap else dict(level=None, spell_ranks={}, items=[], inventory_known=False)
        champion = fixed['champion']
        details = champion_details(directory, setup['patch'], champion) if champion else None
        raw = details['locales']['en_US'] if details else {}
        page = fixed['rune_page']
        ids = [i for i in page['primary'] + page['secondary'] if i is not None]
        selected_items = [dict(**item, data=catalog['items'][item['id']]) for item in state['items']]
        # Keep data-file fields raw: tooltips can have unresolved variables, and modifiers are not universally additive.
        spell_refs = {}
        for key, spell in zip(('Q', 'W', 'E', 'R'), raw.get('spells', [])):
            rank = state['spell_ranks'].get(key)
            spell_refs[key] = dict(rank=rank, name=spell['name'], id=spell['id'],
                **{field + '_data': spell.get(field) for field in ('range', 'cooldown', 'cost', 'effect', 'tooltip', 'vars')})
            if rank and rank <= spell.get('maxrank', 0):
                spell_refs[key]['rank_reference'] = {field: spell.get(field, [])[rank-1] if len(spell.get(field, [])) >= rank else None
                                                      for field in ('range', 'cooldown', 'cost')}
        result[side] = dict(champion=champion, patch=setup['patch'], rune_page=deepcopy(page),
            runes=[catalog['runes'][str(i)] for i in ids], shards=[catalog['shards'][str(i)] for i in page['shards'] if i is not None],
            items=selected_items, base_stats=raw.get('stats', {}), passive=raw.get('passive', {}),
            spells=spell_refs, base_growth_reference=base_growth_reference(raw.get('stats', {}), state['level']),
            effective_state=deepcopy(state), verified_effective_state=False,
            selected_at_source_time_s=snap['source_time_s'] if snap else None, requested_at_source_time_s=source_time_s,
            sources=dict(catalog=catalog['sources'], champion=details['sources'] if details else {}),
            calculation_status='selection_and_static_references_only',
            missing_mechanisms=['Effective stats, windup, missile travel, champion/rune/item effects and current stacks need verified rule adapters.'])
    return result
