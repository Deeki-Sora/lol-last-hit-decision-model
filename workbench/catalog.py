"""Version-pinned selection data. No executable code is downloaded from providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import ssl
import urllib.request
from .core import read_json, write_json

DD = 'https://ddragon.leagueoflegends.com'
CD = 'https://raw.communitydragon.org'


def download(url, allowed_hosts=None):
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    request = urllib.request.Request(url, headers={'User-Agent': 'LOL-Short-Window-Workbench/0.91'})
    with urllib.request.urlopen(request, timeout=25, context=context) as response:
        if response.url.split('/')[2] not in (allowed_hosts or {'ddragon.leagueoflegends.com', 'raw.communitydragon.org'}):
            raise ValueError('Unexpected data-provider redirect')
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('Data file exceeds size limit')
        return json.loads(raw), dict(url=url, sha256=hashlib.sha256(raw).hexdigest(),
            last_modified=response.headers.get('Last-Modified'), fetched_at=datetime.now(timezone.utc).isoformat())


def resolve_version(value, versions):
    """26.N is the public 2026 patch label; Data Dragon uses 16.N.build."""
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Enter a patch such as 26.6 or an exact Data Dragon version such as 16.6.1')
    if value.count('.') == 2:
        if value not in versions:
            raise ValueError('Version is not available from Data Dragon')
        return value
    major, minor = map(int, value.split('.'))
    prefix = f'{16 if major == 26 else major}.{minor}.'
    candidates = [v for v in versions if v.startswith(prefix) and re.fullmatch(r'\d+\.\d+\.\d+', v)]
    if not candidates:
        raise ValueError('No matching patch data; a newer patch will not be substituted')
    return max(candidates, key=lambda v: tuple(map(int, v.split('.'))))


def catalog_path(directory, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(version)):
        raise ValueError('Exact catalog version required')
    return Path(directory) / 'catalogs' / version / 'catalog.json'


def _ensure_shard_images(directory, catalog):
    """Backfill icon URLs for older cached catalogs without changing rune data."""
    if not catalog.get('shards') or all(item.get('image') for item in catalog['shards'].values()):return catalog
    if 'cd/default/perks' not in catalog.get('sources',{}):return catalog
    patch='.'.join(catalog['version'].split('.')[:2])
    try:raw,source=download(f'{CD}/{patch}/plugins/rcp-be-lol-game-data/global/default/v1/perks.json')
    except (OSError,ValueError):return catalog
    by_id={str(item['id']):item for item in raw}
    changed=False
    for ident,item in catalog['shards'].items():
        icon=by_id.get(str(ident),{}).get('iconPath')
        if icon and icon.startswith('/'):
            item['image']=f'{CD}/{patch}/plugins/rcp-be-lol-game-data/global/default{icon}';changed=True
    if changed:
        catalog['sources']['cd/default/perks'] = source
        write_json(catalog_path(directory,catalog['version']),catalog)
    return catalog


def load_catalog(directory, requested):
    # Exact versions are reusable offline; abbreviated patches use a pinned cached version list.
    if isinstance(requested, str) and re.fullmatch(r'\d+\.\d+\.\d+', requested):
        cached = catalog_path(directory, requested)
        if cached.exists():
            return _ensure_shard_images(directory,read_json(cached))
    versions_file = Path(directory) / 'catalogs' / 'versions.json'
    if versions_file.exists():
        versions = read_json(versions_file)['versions']
    else:
        versions, meta = download(DD + '/api/versions.json')
        versions_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(versions_file, dict(versions=versions, source=meta))
    try:
        version = resolve_version(requested, versions)
    except ValueError:
        versions, meta = download(DD + '/api/versions.json')
        write_json(versions_file, dict(versions=versions, source=meta))
        version = resolve_version(requested, versions)
    destination = catalog_path(directory, version)
    if destination.exists():
        return _ensure_shard_images(directory,read_json(destination))
    sources, warnings, data = {}, [], {}
    jobs = {f'{locale}/{kind}': f'{DD}/cdn/{version}/data/{locale}/{kind}.json'
            for locale in ('en_US', 'zh_CN') for kind in ('champion', 'item', 'runesReforged')}
    patch = '.'.join(version.split('.')[:2])
    # CDragon is used for version-specific shard slots and localized shard labels.
    jobs.update({f'cd/{locale}/{kind}': f'{CD}/{patch}/plugins/rcp-be-lol-game-data/global/{locale}/v1/{kind}.json'
                 for locale, kind in [('default', 'perks'), ('zh_cn', 'perks'), ('default', 'perkstyles')]})
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {key: pool.submit(download, url) for key, url in jobs.items()}
        for key, future in futures.items():
            try:
                data[key], sources[key] = future.result()
            except (OSError, ValueError) as error:
                if key.startswith('en_US/'):
                    raise ValueError(f'Required patch data unavailable: {key}: {error}') from error
                warnings.append(f'{key}: {error}')
    def localized(kind, ident, field='name'):
        return {lang: data.get(f'{lang}/{kind}', data[f'en_US/{kind}'])['data'][ident].get(field, '')
                for lang in ('en_US', 'zh_CN')}
    champions = {ident: dict(id=ident, key=c['key'], names=localized('champion', ident),
        titles=localized('champion', ident, 'title'), stats=c['stats']) for ident, c in data['en_US/champion']['data'].items()}
    items = {ident: dict(id=ident, names=localized('item', ident), descriptions=localized('item', ident, 'description'),
        stats=item.get('stats', {}), maps=item.get('maps', {}), tags=item.get('tags', []),
        stacks=item.get('stacks', 1), gold=item.get('gold', {}), inStore=item.get('inStore', True),
        requiredAlly=item.get('requiredAlly'), requiredChampion=item.get('requiredChampion'),
        image=f'{DD}/cdn/{version}/img/item/{item["image"]["full"]}') for ident, item in data['en_US/item']['data'].items()}
    paths, runes = [], {}
    for path in data['en_US/runesReforged']:
        zh = next((p for p in data.get('zh_CN/runesReforged', []) if p['id'] == path['id']), path)
        zh_runes = {r['id']: r for slot in zh['slots'] for r in slot['runes']}
        paths.append(dict(id=path['id'], names={'en_US': path['name'], 'zh_CN': zh['name']},
            slots=[[r['id'] for r in slot['runes']] for slot in path['slots']]))
        for slot in path['slots']:
            for rune in slot['runes']:
                zr = zh_runes.get(rune['id'], rune)
                runes[str(rune['id'])] = dict(id=rune['id'], names={'en_US': rune['name'], 'zh_CN': zr['name']},
                    descriptions={'en_US': rune['longDesc'], 'zh_CN': zr['longDesc']}, image=f'{DD}/cdn/img/{rune["icon"]}')
    shard_slots = []
    styles = data.get('cd/default/perkstyles', {}).get('styles', [])
    if styles:
        shard_slots = [s['perks'] for s in styles[0]['slots'] if s['type'] == 'kStatMod']
    shards = {}
    zh_perks = {p['id']: p for p in data.get('cd/zh_cn/perks', [])}
    for perk in data.get('cd/default/perks', []):
        if any(perk['id'] in slot for slot in shard_slots):
            zh = zh_perks.get(perk['id'], perk)
            icon=perk.get('iconPath')
            image=f'{CD}/{patch}/plugins/rcp-be-lol-game-data/global/default{icon}' if icon and icon.startswith('/') else None
            shards[str(perk['id'])] = dict(id=perk['id'], names={'en_US': perk['name'], 'zh_CN': zh['name']},
                descriptions={'en_US': perk['longDesc'], 'zh_CN': zh['longDesc']}, image=image)
    if not shard_slots or any(str(ident) not in shards for slot in shard_slots for ident in slot):
        shard_slots, shards = [], {}
        warnings.append('Patch-specific shard data unavailable; shards remain unknown')
    result = dict(schema_version=1, version=version, public_patch=f'26.{version.split(".")[1]}' if version.startswith('16.') else None,
        champions=champions, items=items, rune_paths=paths, runes=runes, shards=shards, shard_slots=shard_slots,
        sources=sources, warnings=warnings)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, result)
    return result


def champion_details(directory, version, champion):
    catalog = read_json(catalog_path(directory, version))
    if champion not in catalog['champions']:
        raise ValueError('Unknown champion ID for this patch')
    path = catalog_path(directory, version).parent / f'champion_{champion}.json'
    if path.exists():
        return read_json(path)
    result = dict(id=champion, version=version, locales={}, sources={})
    for lang in ('en_US', 'zh_CN'):
        try:
            data, source = download(f'{DD}/cdn/{version}/data/{lang}/champion/{champion}.json')
            result['locales'][lang] = data['data'][champion]
            result['sources'][lang] = source
        except (OSError, ValueError):
            if lang == 'en_US':
                raise
    write_json(path, result)
    return result
