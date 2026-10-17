"""Version-aware minion references with explicit generic fallbacks.

CommunityDragon does not expose a stable public minion schema across patches.
The loader therefore records attempted sources and returns a conservative
profile when fields are absent; it never presents the fallback as patch data.
"""
from pathlib import Path
from .core import read_json,write_json
from .catalog import catalog_path,download

GENERIC_MINION_SOURCE='https://riotcodex.net/rift/minions'
GENERIC_MINION_PROFILES={
    # Patch 26.20 Codex base rows.  These are explicitly a fallback for other
    # patches, never silently asserted to be the selected patch's values.
    "melee":dict(hp=465,move_speed=350,radius=48,hp_regen_s=0,armor=0,magic_resist=0,
        attack_speed=1.25,period_s=.8,windup_s=.3,range=110,missile_speed=0,damage=11,gold_reward=20,xp_reward=62),
    "caster":dict(hp=284,move_speed=350,radius=32,hp_regen_s=0,armor=0,magic_resist=0,
        attack_speed=0.667,period_s=1.5,windup_s=.3,range=550,missile_speed=650,damage=21,gold_reward=14,xp_reward=31),
    "siege":dict(hp=835,move_speed=350,radius=48,hp_regen_s=0,armor=0,magic_resist=0,
        attack_speed=1.,period_s=1.,windup_s=.3,range=300,missile_speed=650,damage=37.5,gold_reward=50,xp_reward=75),
    "super":dict(hp=1600,move_speed=350,radius=48,hp_regen_s=0,armor=100,magic_resist=-30,
        attack_speed=.85,period_s=1/.85,windup_s=.3,range=170,missile_speed=0,damage=185,gold_reward=50,xp_reward=75),
    "minion":dict(hp=None,move_speed=325,radius=40,hp_regen_s=0,armor=0,magic_resist=0,
        attack_speed=None,period_s=None,windup_s=None,range=None,missile_speed=None,damage=None,gold_reward=None,xp_reward=None),
}


def generic_profile(kind):
    if kind not in GENERIC_MINION_PROFILES:raise ValueError("unknown minion kind")
    return dict(GENERIC_MINION_PROFILES[kind],kind=kind,source_kind="generic_default",verified=False,
        profile_version='26.20',source=GENERIC_MINION_SOURCE,
        behavior=dict(acquisition_range=500,help_range=1000,recheck='between_attack_windups',
            target_priority=['champion_attacking_ally_champion','minion_attacking_ally_champion',
                'minion_attacking_ally_minion','turret_attacking_ally_minion','closest_enemy_minion','closest_enemy_champion'],
            same_priority_does_not_steal=True,first_wave_ghosted=True),
        note="Generic fallback from a patch-scoped public reference; replace or verify for the selected patch before simulation.")


def _cache_path(directory,version):return catalog_path(directory,version).parent/f"minion_profiles_{version}.json"


def load_profiles(directory,version,fetch=False):
    """Load a user/provider cache, optionally trying known CDragon candidate paths."""
    path=_cache_path(directory,version)
    if path.exists():return read_json(path)
    profiles={kind:generic_profile(kind) for kind in GENERIC_MINION_PROFILES}
    sources=[];warnings=[]
    if fetch:
        patch='.'.join(version.split('.')[:2])
        for kind in ('melee','caster','siege','super'):
            names=(f"{kind}minion",f"minion{kind}",f"sruap_minion{kind}")
            found=None
            for name in names:
                url=f"https://raw.communitydragon.org/{patch}/game/data/characters/{name}/{name}.bin.json"
                try:
                    raw,source=download(url);found=(raw,source);break
                except Exception as error:warnings.append(f"{kind}:{type(error).__name__}")
            if found:
                # Keep raw data for manual extraction; schema is not assumed.
                profiles[kind].update(source_kind="provider_raw_unmapped",verified=False,raw=found[0],source=found[1])
                sources.append(found[1])
    result=dict(schema_version=1,version=version,profiles=profiles,sources=sources,warnings=warnings)
    write_json(path,result);return result

