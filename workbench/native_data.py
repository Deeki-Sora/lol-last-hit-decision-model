"""Patch-specific native character attributes; shared lookup for every champion."""
from .catalog import CD, download, catalog_path
from .core import read_json, write_json

SCHEMA_VERSION=2
STAT_MAP={'baseHPModifiable':('hp',1),'hpPerLevelModifiable':('hpperlevel',1),
    'baseDamageModifiable':('attackdamage',1),'damagePerLevelModifiable':('attackdamageperlevel',1),
    'baseArmorModifiable':('armor',1),'armorPerLevelModifiable':('armorperlevel',1),
    'baseMR':('spellblock',1),'baseMoveSpeedModifiable':('movespeed',1),'attackRangeModifiable':('attackrange',1),
    'baseStaticHPRegenModifiable':('hpregen',5),'hpRegenPerLevelModifiable':('hpregenperlevel',5),
    'attackSpeedModifiable':('attackspeed',1),'attackSpeedPerLevelModifiable':('attackspeedperlevel',1)}


def character_attributes(root,version,source):
    fields=set(STAT_MAP)|{'mCharacterName','attackSpeedRatioModifiable','mAdaptiveForceToAbilityPowerWeight'}
    base={field:root[key]['baseValue']*factor for key,(field,factor) in STAT_MAP.items()
          if isinstance(root.get(key),dict) and isinstance(root[key].get('baseValue'),(int,float))}
    return dict(schema_version=SCHEMA_VERSION,version=version,source=source,
        character={k:root[k] for k in sorted(fields) if k in root},base_stats=base,
        adaptive_default='ap' if root.get('mAdaptiveForceToAbilityPowerWeight',0)>0 else 'ad')


def native_data(directory, version, champion):
    catalog=read_json(catalog_path(directory,version))
    if champion not in catalog['champions']:raise ValueError('Unknown champion')
    if not version.startswith('16.'):raise ValueError('Native mechanism adapter currently requires a 2026 data patch')
    path=catalog_path(directory,version).parent/f'native_{champion}.json'
    if path.exists():
        cached=read_json(path)
        if cached.get('schema_version')==SCHEMA_VERSION:return cached
    patch='.'.join(version.split('.')[:2]);name=champion.lower()
    raw,source=download(f'{CD}/{patch}/game/data/characters/{name}/{name}.bin.json')
    roots=[v for v in raw.values() if isinstance(v,dict) and v.get('__type')=='CharacterRecord']
    root=next((r for r in roots if r.get('mCharacterName','').lower()==name),None)
    if root is None:raise ValueError('No matching character record')
    result=character_attributes(root,version,source)
    write_json(path,result)
    return result
