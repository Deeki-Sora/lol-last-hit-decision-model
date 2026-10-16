"""Shared stat arithmetic from versioned data; no per-champion combat rule table."""
import html
import re

ATTACK_SPEED_CAP_SOURCE='https://www.leagueoflegends.com/en-us/news/game-updates/patch-2025-s1-3-notes/'


def ordinary_attack_speed_cap(version):
    if not version:return None
    parts=version.split('.')
    if len(parts)<2 or not all(p.isdigit() for p in parts[:2]):return None
    major,minor=map(int,parts[:2])
    if major>16:return None  # Future seasons need a confirmed ruleset.
    return 2.5 if major<15 or major==15 and minor<3 else 3.

STAT_FIELDS=('max_hp','health_regen','max_resource','resource_regen','attack_damage','ability_power','armor','magic_resist',
    'attack_speed','ability_haste','move_speed','crit_chance','lifesteal','omnivamp','armor_penetration_flat','magic_penetration_flat',
    'attack_range','armor_penetration_percent','magic_penetration_percent','tenacity','slow_resist','cooldown_reduction',
    'attack_speed_ratio','bonus_attack_speed_percent')

ITEM_MAP={'FlatHPPoolMod':'max_hp','FlatMPPoolMod':'max_resource','FlatPhysicalDamageMod':'attack_damage','FlatMagicDamageMod':'ability_power',
    'FlatArmorMod':'armor','FlatSpellBlockMod':'magic_resist','FlatMovementSpeedMod':'move_speed','FlatAbilityHasteMod':'ability_haste',
    'FlatHPRegenMod':'health_regen','FlatMPRegenMod':'resource_regen','FlatCritChanceMod':'crit_chance','PercentLifeStealMod':'lifesteal'}
TEXT_MAP={'health':'max_hp','mana':'max_resource','attack damage':'attack_damage','ability power':'ability_power','armor':'armor',
    'magic resist':'magic_resist','magic resistance':'magic_resist','move speed':'move_speed','movement speed':'move_speed',
    'ability haste':'ability_haste','critical strike chance':'crit_chance','life steal':'lifesteal','lifesteal':'lifesteal',
    'omnivamp':'omnivamp','lethality':'armor_penetration_flat','magic penetration':'magic_penetration_flat','tenacity':'tenacity',
    'attack speed':'bonus_attack_speed_percent','armor penetration':'armor_penetration_percent',
    'base health regen':'base_health_regen_percent','base mana regen':'base_resource_regen_percent'}


def item_components(item):
    """Structured stats take precedence; only the explicit <stats> block supplies missing fields."""
    out={};unknown=[]
    for key,value in item.get('stats',{}).items():
        field=ITEM_MAP.get(key)
        if field:out[field]=value
        elif key=='PercentAttackSpeedMod':out['bonus_attack_speed_percent']=value*100
        elif key=='PercentMovementSpeedMod':out['move_speed_percent']=value
        else:unknown.append(key)
    description=item.get('descriptions',{}).get('en_US','')
    block=re.search(r'<stats>(.*?)</stats>',description,re.S|re.I)
    if block:
        for row in re.split(r'<br\s*/?>',block.group(1),flags=re.I):
            text=html.unescape(re.sub(r'<[^>]+>',' ',row));text=' '.join(text.split())
            match=re.fullmatch(r'([\d,.]+)\s*(%)?\s+(.+)',text)
            if not match:
                if text:unknown.append('stat_block:'+text)
                continue
            value=float(match[1].replace(',',''));percent=bool(match[2]);label=match[3].strip().lower();field=TEXT_MAP.get(label)
            if percent and label in ('move speed','movement speed'):field='move_speed_percent'
            elif percent and label=='magic penetration':field='magic_penetration_percent'
            elif not percent and label=='armor penetration':field='armor_penetration_flat'
            if field is None:unknown.append('stat_block:'+text);continue
            if percent and field!='bonus_attack_speed_percent':value/=100
            if field not in out:out[field]=value
    return out,unknown


def subtotal(reference,native,overrides):
    base=(reference.get('base_growth_reference') or {}).get('values',{});level=reference.get('effective_state',{}).get('level')
    auto={key:None for key in STAT_FIELDS};trace=[];notes=[]
    if level is None or not base:return auto,trace,['champion_or_level_unknown']
    for key in STAT_FIELDS:auto[key]=0.
    mapping={'max_hp':'hp','max_resource':'mp','attack_damage':'attackdamage','armor':'armor','magic_resist':'spellblock','move_speed':'move_speed','attack_range':'attack_range'}
    for key,source in mapping.items():auto[key]=base.get(source)
    auto['health_regen']=None if base.get('hpregen') is None else base['hpregen']/5
    auto['resource_regen']=None if base.get('mpregen') is None else base['mpregen']/5
    auto['bonus_attack_speed_percent']=base.get('attack_speed_growth_percent',0)
    auto['attack_speed_ratio']=native.get('character',{}).get('attackSpeedRatioModifiable',{}).get('baseValue')
    bonus_ad=0.;item_ap=0.;percent_move=0.;health_regen_percent=0.;resource_regen_percent=0.
    def add(field,value):
        if auto.get(field) is not None:
            if field in ('armor_penetration_percent','magic_penetration_percent','tenacity','slow_resist'):auto[field]=1-(1-auto[field])*(1-value)
            else:auto[field]+=value
    for entry in reference.get('items',[]):
        components,unknown=item_components(entry['data']);quantity=entry['quantity']
        for field,value in components.items():
            if field=='move_speed_percent':percent_move+=value*quantity
            elif field=='base_health_regen_percent':health_regen_percent+=value*quantity
            elif field=='base_resource_regen_percent':resource_regen_percent+=value*quantity
            else:
                for _ in range(quantity):add(field,value)
            if field=='attack_damage':bonus_ad+=value*quantity
            if field=='ability_power':item_ap+=value*quantity
        trace.append(dict(kind='item',id=entry['id'],quantity=quantity,components=components))
        notes.extend('unparsed_item_stat:'+entry['id']+':'+name for name in unknown)
    event=reference.get('effective_state',{}).get('event_state',{});adaptive=event.get('adaptive_stat','auto')
    if adaptive=='auto':
        if bonus_ad>0 and item_ap>0:
            adaptive=None;notes.append('mixed_ad_ap_equipment_select_adaptive_stat')
        elif bonus_ad>0:adaptive='ad'
        elif item_ap>0:adaptive='ap'
        else:adaptive=native.get('adaptive_default')
    for shard in reference.get('shards',[]):
        text=html.unescape(re.sub(r'<[^>]+>',' ',shard.get('descriptions',{}).get('en_US','')))
        numbers=[float(n) for n in re.findall(r'\d+(?:\.\d+)?',text)];ident=shard['id'];effects={}
        if ident==5005 and numbers:effects['bonus_attack_speed_percent']=numbers[0]
        elif ident==5007 and numbers:effects['ability_haste']=numbers[0]
        elif ident==5011 and len(numbers)==1:effects['max_hp']=numbers[0]
        elif ident==5001 and len(numbers)>=2:effects['max_hp']=numbers[0]+(numbers[1]-numbers[0])*(level-1)/17
        elif ident==5010 and numbers and '%' in text:percent_move+=numbers[0]/100;effects['move_speed_percent']=numbers[0]/100
        elif ident==5013 and numbers and '%' in text:effects.update(tenacity=numbers[0]/100,slow_resist=numbers[0]/100)
        elif ident==5008 and numbers:
            if adaptive=='ad':effects['attack_damage']=numbers[0]*.6
            elif adaptive=='ap':effects['ability_power']=numbers[0]
            else:
                notes.append('adaptive_stat_choice_unknown');auto['attack_damage']=auto['ability_power']=None
        else:
            notes.append('shard_data_unresolved:'+str(ident))
            affected={5005:['bonus_attack_speed_percent'],5007:['ability_haste'],5001:['max_hp'],5011:['max_hp'],
                5010:['move_speed'],5013:['tenacity','slow_resist'],5008:['attack_damage','ability_power']}
            for field in affected.get(ident,[]):auto[field]=None
        for field,value in effects.items():
            if field!='move_speed_percent':add(field,value)
        trace.append(dict(kind='stat_shard',id=ident,effects=effects,adaptive_stat=adaptive))
    if auto['health_regen'] is not None:auto['health_regen']+=(base.get('hpregen',0)/5)*health_regen_percent
    if auto['resource_regen'] is not None:auto['resource_regen']+=(base.get('mpregen',0)/5)*resource_regen_percent
    if auto['move_speed'] is not None:
        speed=auto['move_speed']*(1+percent_move)
        auto['move_speed']=speed*.5+230 if speed>490 else speed*.8+83 if speed>415 else speed*.5+110 if speed<220 else speed
    ratio=overrides.get('attack_speed_ratio') if overrides.get('attack_speed_ratio') is not None else auto['attack_speed_ratio']
    bonus=overrides.get('bonus_attack_speed_percent') if overrides.get('bonus_attack_speed_percent') is not None else auto['bonus_attack_speed_percent']
    base_as=base.get('base_attack_speed')
    auto['attack_speed']=base_as if bonus==0 else base_as+ratio*bonus/100 if base_as is not None and ratio is not None and bonus is not None else None
    cap=ordinary_attack_speed_cap(reference.get('patch'))
    if cap is not None and auto['attack_speed'] is not None:auto['attack_speed']=min(auto['attack_speed'],cap)
    trace.append(dict(kind='ordinary_attack_speed_cap',value=cap,source=ATTACK_SPEED_CAP_SOURCE))
    haste=overrides.get('ability_haste') if overrides.get('ability_haste') is not None else auto['ability_haste']
    auto['cooldown_reduction']=haste/(100+haste) if haste is not None else None
    return auto,trace,notes
