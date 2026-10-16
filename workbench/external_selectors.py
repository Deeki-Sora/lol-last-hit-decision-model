"""Import selection identities, never third-party combat values or champion choices."""
from pathlib import Path
import re
import urllib.parse
from .catalog import download, catalog_path
from .core import read_json, write_json
from .loadouts import rune_page

ARAMONLY = 'https://www.aramonly.com/lol-runes-builder/'
PAGE_DATA = 'https://www.aramonly.com/page-data/lol-runes-builder/page-data.json'


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


def aramonly_preview(directory, link, version):
    if not isinstance(link, str) or len(link) > 8192:
        raise ValueError('Invalid share link')
    url = urllib.parse.urlsplit(link)
    if url.scheme != 'https' or url.netloc != 'www.aramonly.com' or url.path.rstrip('/') != '/lol-runes-builder':
        raise ValueError('Use an HTTPS ARAMonly runes-builder share link')
    query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
    if any(len(v) != 1 for k, v in query.items() if k in ('runes', 'items')):
        raise ValueError('Duplicate selection query parameters')
    catalog = read_json(catalog_path(directory, version))
    # The sharing format encodes positions, so decode against that site's own current schema.
    # The compact schema is cached with the import evidence for offline reproduction.
    path = Path(directory) / 'catalogs' / 'aramonly_schema.json'
    if path.exists():
        schema = read_json(path)
    else:
        raw, source = download(PAGE_DATA, allowed_hosts={'www.aramonly.com'})
        data = raw['result']['data']
        schema = dict(patch=data['patchVersionJson']['patchVersion'], source=source,
            trees=[dict(name=t['tree'], rows=[[r['name'] for r in row['runes']] for row in t['outlook']])
                   for t in data['allRunesJson']['nodes'] if t['tree'] != 'Empty'])
        if not re.fullmatch(r'26\.\d+', schema['patch']):
            raise ValueError('This adapter requires an explicitly identified 2026 patch schema')
        write_json(path, schema)
    trees = sorted((t for t in schema['trees'] if t['name'] != 'Passive'), key=lambda t: t['name'])
    shards = next(t for t in schema['trees'] if t['name'] == 'Passive')
    raw_code = query.get('runes', [''])[0]
    page = dict(primary_path=None, secondary_path=None, primary=[None]*4, secondary=[None]*2, shards=[None]*3)
    missing, decoded = [], {}
    def pick(text, options):
        if text in ('x', 'v', 'vv', ''):
            return None
        if not text.isdigit() or int(text) >= len(options):
            raise ValueError('Rune position is outside the supported website schema')
        return options[int(text)]
    def mapped(name, collection):
        if name is None:
            return None
        matches = [r['id'] for r in collection.values() if normalized(r['names']['en_US']) == normalized(name)]
        if len(matches) != 1:
            missing.append(name)
            return None
        return matches[0]
    if raw_code:
        parts = raw_code.split('-')
        if len(parts) == 1 and len(parts[0]) == 3:parts = ['xxxxx','vvvvv',parts[0]]
        elif len(parts) == 1 and 'v' in parts[0]:parts = ['xxxxx',parts[0]]
        elif len(parts) == 2 and len(parts[1]) == 3:parts = [parts[0],'vvvvv',parts[1]]
        if len(parts) > 3 or len(parts[0]) != 5 or len(parts) > 1 and len(parts[1]) != 5 or len(parts) > 2 and len(parts[2]) != 3:
            raise ValueError('Unsupported ARAMonly rune code layout')
        main, sub, passive = (parts + ['', ''])[:3]
        tree = pick(main[0], trees)
        if tree:
            path_match = next((p for p in catalog['rune_paths'] if normalized(p['names']['en_US']) == normalized(tree['name'])), None)
            page['primary_path'] = path_match['id'] if path_match else None
            decoded['primary'] = [pick(c, tree['rows'][i]) for i,c in enumerate(main[1:])]
            page['primary'] = [mapped(n, catalog['runes']) for n in decoded['primary']]
        if sub:
            tree = pick(sub[0], trees)
            if tree:
                path_match = next((p for p in catalog['rune_paths'] if normalized(p['names']['en_US']) == normalized(tree['name'])), None)
                page['secondary_path'] = path_match['id'] if path_match else None
                names = []
                for code in [sub[1:3], sub[3:5]]:
                    if code == 'vv':names.append(None);continue
                    if not re.fullmatch(r'[1-3][0-9]', code):raise ValueError('Invalid secondary rune position')
                    names.append(pick(code[1], tree['rows'][int(code[0])]))
                decoded['secondary'] = names
                page['secondary'] = [mapped(n, catalog['runes']) for n in names]
        if passive:
            decoded['shards'] = [pick(c, shards['rows'][i]) for i,c in enumerate(passive)]
            page['shards'] = [mapped(n, catalog['shards']) for n in decoded['shards']]
        # A mismatch is shown, not silently remapped by the target patch's positional order.
        if not missing:rune_page(page, catalog)
    raw_items = query.get('items', [''])[0]
    ids = raw_items.split(',') if raw_items else []
    if len(ids) > 6 or any(not re.fullmatch(r'\d+', ident) for ident in ids):
        raise ValueError('Use at most six numeric item IDs')
    items, invalid_items = [], []
    for slot, ident in enumerate(ids):
        item = catalog['items'].get(ident)
        if not item or not item.get('maps', {}).get('11') or 'Trinket' in item.get('tags', []):
            invalid_items.append(ident)
        else:items.append(dict(slot=slot,id=ident,quantity=1,data=item))
    return dict(provider='ARAMonly', source_url=link, provider_patch=schema['patch'], target_patch=version,
        source=schema['source'], champion_ignored=True, decoded_names=decoded,
        rune_page=page if raw_code else None, unresolved_runes=missing, items=items, invalid_items=invalid_items,
        items_parameter_present='items' in query, inventory_complete=False,
        note='Optional selection source only. Champion selection is preserved. Item quantities, trinket and completeness require confirmation. Patch values come from the local pinned catalog.')
