"""Import human-reviewable reference text without executing a web page."""
import html
import re
import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CODEX_HOST='riotcodex.net'


def public_patch(version):
    match=re.match(r'^(\d+)\.(\d+)',str(version or ''))
    if not match:return None
    major,minor=map(int,match.groups())
    return f'26.{minor}' if major==16 else f'{major}.{minor}'


def fetch_text(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!=CODEX_HOST:raise ValueError('Codex fetch only permits https://riotcodex.net')
    context=ssl.create_default_context()
    try:
        import certifi;context.load_verify_locations(certifi.where())
    except ImportError:pass
    request=urllib.request.Request(url,headers={'User-Agent':'LOL-Short-Window-Workbench/0.91'})
    with urllib.request.urlopen(request,timeout=20,context=context) as response:
        raw=response.read(12*1024*1024+1)
        if len(raw)>12*1024*1024:raise ValueError('Codex page exceeds size limit')
        return raw.decode('utf-8','replace'),dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),
            fetched_at=datetime.now(timezone.utc).isoformat(),last_modified=response.headers.get('Last-Modified'))


def codex_text_to_reference(text, source_url, selected_patch=None):
    """Extract common stats and preserve ability prose for adapter review.

    Riot Codex pages are unofficial and may change layout.  Parsed values are
    therefore references with ``verified=False``; the mechanism adapter still
    requires explicit review before simulation.
    """
    if not isinstance(text,str) or not text.strip():raise ValueError('Codex text is empty')
    plain=html.unescape(re.sub(r'<[^>]+>','\n',text)).replace('\r','')
    lines=[' '.join(x.split()) for x in plain.split('\n') if x.strip()]
    joined='\n'.join(lines)
    provider_patch=(re.search(r'Patch\s+(\d+\.\d+)',joined,re.I) or [None,None])[1]
    patch=selected_patch or provider_patch
    stats={};labels={'Health':'hp','Health regen':'hpregen','Armor':'armor','Magic resist':'spellblock',
        'Attack damage':'attackdamage','Attack speed':'attackspeed','Attack range':'attackrange','Move speed':'movespeed'}
    for label,field in labels.items():
        for i,line in enumerate(lines):
            if line.lower()!=label.lower():continue
            if i+1>=len(lines):continue
            match=re.match(r'^-?\d+(?:\.\d+)?$',lines[i+1]);
            if not match:continue
            value=float(match.group());stats[field]=value
            if i+2<len(lines):
                growth=re.match(r'^\+\s*(-?\d+(?:\.\d+)?)\s*/\s*lvl',lines[i+2],re.I)
                if growth:stats[field+'perlevel']=float(growth.group(1))
            break
    abilities={};current=None;buffer=[]
    for line in lines:
        heading=re.match(r'^([PQRWES])\s*$',line)
        if heading:
            if current:abilities[current]=' '.join(buffer)
            current=heading.group(1);buffer=[];continue
        if current:buffer.append(line)
    if current:abilities[current]=' '.join(buffer)
    if not stats and not abilities:raise ValueError('no recognizable Codex fields')
    return dict(schema_version=1,source=source_url,patch=patch,provider_patch=provider_patch,
        selected_patch=selected_patch,patch_match=not selected_patch or not provider_patch or provider_patch==public_patch(selected_patch),verified=False,
        base_stats=stats,ability_reference=abilities,
        notes=['Parsed reference text only; confirm the exact selected patch and effective values.',
            'Ability geometry, hitboxes, sequence state, costs and temporary effects require a mechanism profile review.'])


def fetch_riot_codex(directory, version, champion):
    """Fetch/cache a champion page; callers never need to search the site."""
    directory=Path(directory);safe=re.sub(r'[^A-Za-z0-9_-]','_',str(champion));folder=directory/'references';folder.mkdir(exist_ok=True)
    cache=folder/f'codex_{version}_{safe}.json'
    if cache.exists():return json.loads(cache.read_text(encoding='utf-8'))
    candidates=[str(champion),str(champion).lower(),re.sub(r'[^A-Za-z0-9]','',str(champion))]
    last=None
    for slug in dict.fromkeys(candidates):
        url=f'https://{CODEX_HOST}/champions/{slug}'
        try:
            text,source=fetch_text(url);profile=codex_text_to_reference(text,url,version)
            profile['fetch']=source;profile['cache_path']=cache.relative_to(directory).as_posix();profile['notes'].append('Automatic page lookup; review patch_match before using the reference.')
            cache.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');return profile
        except (OSError,ValueError,urllib.error.HTTPError) as error:last=error
    raise ValueError(f'Riot Codex page not available for {champion}: {last}')

