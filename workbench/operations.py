"""Portable table import, official data lookup, and optional assessed matrix solving."""
from pathlib import Path
import csv
import io
import json
import math
import re
import ssl
import urllib.request
from .core import read_json, write_json, validate_annotations, export_tables


def import_csv(directory, filename, encoding='utf-8-sig'):
    directory = Path(directory)
    project = read_json(directory/'project.json')
    annotations = read_json(directory/'annotations.json')
    text = Path(filename).read_text(encoding=encoding)
    if '\ufffd' in text or '??' in text:
        raise ValueError('Damaged replacement characters detected; restore source text before import. Encoding conversion cannot recover lost text.')
    rows = list(csv.DictReader(io.StringIO(text)))
    seen = set()
    for row in rows:
        key = (row['frame_id'], row['unit_id'])
        if key in seen:
            raise ValueError('duplicate frame/unit row: '+str(key))
        seen.add(key)
        frame = annotations['frames'].setdefault(key[0], {'units': {}})
        unit = frame.setdefault('units', {}).setdefault(key[1], {})
        for field in ('action','target','phase','notes','coordinate_method'):
            if field in row:
                unit[field] = row[field]
        for field in ('hp','action_start_s','action_end_s'):
            if field in row:
                unit[field] = float(row[field]) if row[field].strip() else None
        if 'x_px' in row and 'y_px' in row:
            if bool(row['x_px'].strip()) != bool(row['y_px'].strip()):
                raise ValueError('both x_px and y_px are required together')
            unit['center'] = [float(row['x_px']),float(row['y_px'])] if row['x_px'].strip() else None
        if 'reviewed' in row:
            if row['reviewed'].lower() not in ('true','false','1','0',''):
                raise ValueError('reviewed must be true/false')
            unit['reviewed'] = row['reviewed'].lower() in ('true','1')
        if 'alive' in row:
            value=row['alive'].strip().lower()
            if value not in ('true','false','1','0',''):
                raise ValueError('alive must be true/false or blank')
            unit['alive']=None if not value else value in ('true','1')
    validate_annotations(project, annotations)
    write_json(directory/'annotations.json', annotations)
    return export_tables(directory)


def fetch_hero_data(version, blue, red, language='en_US'):
    """Data Dragon is a patch snapshot, not an effective-combat-stat calculator."""
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Use an exact Data Dragon version, e.g. 16.6.1')
    if not re.fullmatch(r'[a-z]{2}_[A-Z]{2}', language):
        raise ValueError('invalid language')
    result = {}
    context=ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    for side, champion in [('blue',blue),('red',red)]:
        if not re.fullmatch(r'[A-Za-z]+', champion):
            raise ValueError('use a Data Dragon champion ID')
        url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/{language}/champion/{champion}.json'
        with urllib.request.urlopen(url, timeout=30, context=context) as response:
            data = json.load(response)['data'][champion]
        result[side] = dict(champion=champion,patch=version,source_url=url,base_stats=data['stats'],
            passive=data['passive'],spells=data['spells'],runes=[],items=[],
            effective_state={},verified_effective_state=False,
            note='Verify level, attack speed/range, move speed, spell ranks/costs/cooldowns, runes, items and passive state at the recorded time.')
    return result


def solve_matrix(spec):
    """Maximin only for a user-supplied finite two-player zero-sum payoff matrix."""
    import numpy as np
    from scipy.optimize import linprog
    if spec.get('game_type') != 'two_player_zero_sum' or not spec.get('assessment_reference'):
        raise ValueError('Require game_type=two_player_zero_sum and assessment_reference from a completed assessment')
    matrix = np.asarray(spec['payoff_matrix'], dtype=float)
    if matrix.ndim != 2 or min(matrix.shape) < 1 or not np.isfinite(matrix).all():
        raise ValueError('payoff_matrix must be nonempty, rectangular and finite')
    m,n = matrix.shape
    # Maximize guaranteed row-player value v, then solve the dual column policy.
    row = linprog([0.0]*m+[-1.0],A_ub=np.column_stack([-matrix.T,np.ones(n)]),b_ub=np.zeros(n),
        A_eq=[[1.0]*m+[0.0]],b_eq=[1.0],bounds=[(0,None)]*m+[(None,None)],method='highs')
    col = linprog([0.0]*n+[1.0],A_ub=np.column_stack([matrix,-np.ones(m)]),b_ub=np.zeros(m),
        A_eq=[[1.0]*n+[0.0]],b_eq=[1.0],bounds=[(0,None)]*n+[(None,None)],method='highs')
    if not row.success or not col.success:
        raise ValueError('optimization failed')
    return dict(game_type=spec['game_type'],assessment_reference=spec['assessment_reference'],
        row_policy=row.x[:-1].tolist(),column_policy=col.x[:-1].tolist(),value=float(row.x[-1]),
        duality_gap=float(abs(row.x[-1]-col.x[-1])),
        scope='Only the supplied actions and assessed payoffs; not a complete LoL simulation or a player skill score.')
