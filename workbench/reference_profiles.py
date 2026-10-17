"""Import human-reviewable reference text without executing a web page."""
import html
import re


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
    patch=selected_patch or (re.search(r'Patch\s+(\d+\.\d+)',joined,re.I) or [None,None])[1]
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
    return dict(schema_version=1,source=source_url,patch=patch,verified=False,
        base_stats=stats,ability_reference=abilities,
        notes=['Parsed reference text only; confirm the exact selected patch and effective values.',
            'Ability geometry, hitboxes, sequence state, costs and temporary effects require a mechanism profile review.'])

