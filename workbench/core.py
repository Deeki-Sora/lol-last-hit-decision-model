from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import itertools
import json
import math
import re
import shutil
import subprocess
import zipfile
from algorithms.pixel_distance import Observation, distance, displacement, position

ROOT = Path(__file__).resolve().parents[1]
VIDEO_SUFFIXES = {'.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v'}
EVENT_FIELDS = ['frame_id','source_time_s','image','unit_id','side','kind','wave','alive','enemy_hero_id','in_distance_scope',
    'x_px','y_px','local_x_px','local_y_px','coordinate_method','reviewed','action','target','phase','hp',
    'action_start_s','action_end_s','row_type','enemy_hero_distance_px','target_distance_px',
    'enemy_hero_distance_game_units_estimate','target_distance_game_units_estimate','movement_dt_s','movement_px','notes']
DISTANCE_FIELDS = ['frame_id','source_time_s','first','first_side','first_kind','second','second_side','second_kind',
    'distance_px','distance_game_units_estimate','status','both_reviewed']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def seconds(value):
    parts = str(value).strip().split(':')
    if len(parts) > 3:
        raise ValueError('use seconds, MM:SS or HH:MM:SS')
    result = sum(float(p)*60**i for i,p in enumerate(reversed(parts)))
    if not math.isfinite(result) or result < 0:
        raise ValueError('time must be finite and nonnegative')
    return result


def calibration(value):
    if not value:
        return None
    pixels, units = map(float, str(value).split('='))
    if not all(math.isfinite(x) and x > 0 for x in (pixels,units)):
        raise ValueError('calibration must be positive: pixels=game_units')
    return {'pixels':pixels,'game_units':units,'units_per_pixel':units/pixels,
            'status':'user_supplied_isotropic_estimate'}


def probe(path):
    if not shutil.which('ffprobe'):
        raise RuntimeError('ffprobe is required; install FFmpeg and refresh PATH')
    data = json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(path)]))
    video = next((s for s in data['streams'] if s['codec_type']=='video'),None)
    if video is None:
        raise ValueError('no video stream')
    return dict(duration=float(data['format']['duration']),width=video['width'],height=video['height'])


def sample(video, output, start, end, step, first_wave_template=False):
    video, output = Path(video).resolve(), Path(output).resolve()
    if not .1 <= step <= .5:
        raise ValueError('sampling interval must be between 0.1 and 0.5 seconds')
    if not 0 <= start < end:
        raise ValueError('require 0 <= start < end')
    info = probe(video)
    if end > info['duration']+.05:
        raise ValueError('end exceeds video duration')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('ffmpeg is required')
    output.mkdir(parents=True,exist_ok=False)
    frames = output/'frames';frames.mkdir()
    log = output/'sampling_ffmpeg.log'
    # Select actual source frames rather than synthesizing intermediate frames.
    select = f"trim=duration={end-start:.9f},select='isnan(prev_selected_t)+gte(t-prev_selected_t,{step-1e-6:.9f})',showinfo"
    command = ['ffmpeg','-hide_banner','-ss',str(start),'-t',str(end-start),'-i',str(video),
               '-vf',select,'-fps_mode','vfr','-q:v','2',str(frames/'frame_%06d.jpg')]
    with log.open('w',encoding='utf-8') as handle:
        subprocess.run(command,stdout=subprocess.DEVNULL,stderr=handle,check=True)
    pts = []
    for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
        m = re.search(r'\bn:\s*(\d+).*?\bpts_time:([-+\d.eE]+)',line)
        if m:
            pts.append(float(m.group(2)))
    files = sorted(frames.glob('frame_*.jpg'))
    if not files or len(files)!=len(pts):
        raise RuntimeError('sample images and logged frame timestamps differ; inspect sampling_ffmpeg.log')
    sampled = [dict(id=f'f{i:06d}',source_time_s=round(start+t,6),
                    image=p.relative_to(output).as_posix()) for i,(t,p) in enumerate(zip(pts,files),1)]
    project = dict(schema_version=1,source_name=video.name,source_sha256=sha256(video),
        media=info,start_s=start,end_s=end,step_s=step,frames=sampled,calibration=None,
        units=default_units() if first_wave_template else [u for u in default_units() if u['kind']=='hero'],hero_data={'blue':{},'red':{}},strategy_text='',
        timestamp_note='Decoded frame PTS after input seeking; source time = requested start + relative PTS.')
    write_json(output/'project.json',project)
    write_json(output/'annotations.json',{'schema_version':1,'frames':{}})
    return project


def default_units():
    units=[]
    for side in ('blue','red'):
        units.append(dict(id=side+'_hero',side=side,kind='hero',wave=None))
        for kind in ('melee','caster'):
            for index in range(1,4):
                units.append(dict(id=f'{side}_{kind}_w1_{index}',side=side,kind=kind,wave=1))
    return units


def suggest_bars(image_path):
    """Color-run proposals, never confirmed identities/full-bar centers."""
    try:
        from PIL import Image
    except ImportError:
        return []
    with Image.open(image_path) as original:
        factor=original.width/960
        image=original.convert('RGB').resize((960,round(original.height/factor)))
    pixels=image.load();found=[]
    for y in range(int(image.height*.08),int(image.height*.78),2):
        start=None;old=None
        for x in range(65,895):
            r,g,b=pixels[x,y]
            color='red' if r>110 and r>g*1.35 and r>b*1.2 else (
                'blue' if b>95 and g>65 and b>r*1.35 else None)
            if color!=old:
                if old and start is not None and 12<=x-start<=115:
                    box=[round(start*factor,2),round(y*factor,2),round((x-start)*factor,2),round(3*factor,2)]
                    if not any(abs(box[0]-p['box'][0])<8*factor and abs(box[1]-p['box'][1])<8*factor for p in found):
                        found.append(dict(side_guess=old,box=box,status='colored_fill_proposal_only'))
                start=x if color else None;old=color
    return found[:50]


def validate_annotations(project, annotations):
    if annotations.get('schema_version')!=1 or not isinstance(annotations.get('frames'),dict):
        raise ValueError('annotations require schema_version=1 and a frames object')
    frames={f['id'] for f in project['frames']}
    if len(frames)!=len(project['frames']):raise ValueError('frame ids must be unique')
    times=[f['source_time_s'] for f in project['frames']]
    if any(not isinstance(t,(int,float)) or not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('frame times must be finite and strictly increasing')
    if not isinstance(project.get('hero_data',{}),dict) or any(not isinstance(project.get('hero_data',{}).get(side,{}),dict) for side in ('blue','red')):
        raise ValueError('hero_data must contain blue/red objects')
    scale=project.get('calibration')
    if scale:
        expected=calibration(f"{scale['pixels']}={scale['game_units']}")['units_per_pixel']
        if not math.isclose(scale['units_per_pixel'],expected):raise ValueError('inconsistent calibration factor')
    ids={u['id'] for u in project['units']}
    if not ids or not project['frames'] or len(ids)!=len(project['units']):
        raise ValueError('unit ids must be unique')
    for u in project['units']:
        if u.get('side') not in ('blue','red') or not isinstance(u.get('kind'),str):
            raise ValueError('each unit requires side blue/red and kind')
        if u.get('first_seen_s') is not None and (not isinstance(u['first_seen_s'],(int,float)) or not math.isfinite(u['first_seen_s'])):
            raise ValueError('first_seen_s must be finite')
    for side in ('blue','red'):
        if sum(u['kind']=='hero' and u['side']==side for u in project['units'])!=1:
            raise ValueError('this lane workspace requires exactly one hero per side')
    for fid, frame in annotations['frames'].items():
        if fid not in frames or not isinstance(frame,dict):
            raise ValueError('unknown frame id')
        if 'distance_minions' in frame:
            selected=frame['distance_minions']
            if not isinstance(selected,list) or len(set(selected))!=len(selected) or any(uid not in ids for uid in selected):
                raise ValueError('distance_minions must contain unique roster IDs')
            if any(u['id'] in selected and u['kind'] not in {'melee','caster','siege','super','minion'} for u in project['units']):
                raise ValueError('distance_minions may contain only minion IDs')
        coords=list(frame.get('units',{}).items())
        if any(uid not in ids for uid,_ in coords):
            raise ValueError('unknown unit id; add it to the roster first')
        points=[frame.get('origin')]
        for _,unit in coords:
            if not isinstance(unit,dict):
                raise ValueError('unit annotations must be objects')
            points.append(unit.get('center'))
            if unit.get('target') and unit['target'] not in ids:
                raise ValueError('unknown target id')
            if 'alive' in unit and unit['alive'] is not None and not isinstance(unit['alive'],bool):
                raise ValueError('alive must be true, false or null (unknown)')
            if 'reviewed' in unit and not isinstance(unit['reviewed'],bool):
                raise ValueError('reviewed must be boolean')
            for key in ('hp','action_start_s','action_end_s'):
                value=unit.get(key)
                if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
                    raise ValueError(key+' must be finite or null')
            for key in ('action','target','phase','notes','coordinate_method'):
                if key in unit and not isinstance(unit[key],str):raise ValueError(key+' must be text')
            if unit.get('action_start_s') is not None and unit.get('action_end_s') is not None and unit['action_end_s']<unit['action_start_s']:
                raise ValueError('action end cannot precede start')
        for p in points:
            if p is not None and (not isinstance(p,list) or len(p)!=2 or any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in p)):
                raise ValueError('coordinates must be finite [x,y] or null')
    return annotations


def write_csv(path, rows, fields):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def export_tables(directory):
    directory=Path(directory)
    p=read_json(directory/'project.json');a=validate_annotations(p,read_json(directory/'annotations.json'))
    tables=directory/'tables';tables.mkdir(exist_ok=True)
    events=[];pairs=[];deaths=[];last_alive={};previous={};dead=set();persistent_selection=None;factor=(p.get('calibration') or {}).get('units_per_pixel')
    minion_kinds={'melee','caster','siege','super','minion'}
    roster={u['id']:u for u in p['units']}
    def allowed_pair(first,second):
        if first not in roster or second not in roster:return False
        x,y=roster[first],roster[second]
        return x['side']!=y['side'] and ((x['kind']=='hero' and y['kind'] in minion_kinds|{'hero'}) or (y['kind']=='hero' and x['kind'] in minion_kinds))
    for f in p['frames']:
        annotation=a['frames'].get(f['id'],{})
        labelled=annotation.get('units',{})
        for uid,data in labelled.items():
            if (data.get('alive') is False or data.get('action')=='death') and uid not in dead:
                deaths.append(dict(unit_id=uid,side=roster[uid]['side'],kind=roster[uid]['kind'],frame_id=f['id'],
                    last_confirmed_alive_s=last_alive.get(uid),confirmed_dead_by_s=f['source_time_s']))
                dead.add(uid)
            elif data.get('alive') is True and uid not in dead:last_alive[uid]=f['source_time_s']
        active=[u for u in p['units'] if u['id'] not in dead and
            (u.get('first_seen_s') is None or f['source_time_s']>=u['first_seen_s'])]
        if 'distance_minions' in annotation:persistent_selection=annotation['distance_minions']
        selected=persistent_selection
        if selected is None:
            selected=[u['id'] for u in active if u['kind'] in minion_kinds]
            if any(sum(u['id'] in selected and u['side']==side for u in active)>6 for side in ('blue','red')):
                raise ValueError(f"{f['id']}: overlapping/cannon wave; explicitly select distance_minions (any number; no six-minion limit)")
        scope={u['id'] for u in active if u['kind']=='hero' or u['id'] in selected}
        obs=Observation(f['source_time_s'],{uid:data.get('center') for uid,data in labelled.items() if uid not in dead},annotation.get('origin'),annotation.get('scale_id','unscaled_pixels'))
        for u in active:
            uid=u['id'];data=labelled.get(uid,{})
            center=data.get('center');local=position(obs,uid)
            movement=displacement(previous[uid],obs,uid) if uid in previous and previous[uid].scale_id==obs.scale_id else None
            if center is not None:previous[uid]=obs
            enemy=next((h['id'] for h in p['units'] if h['kind']=='hero' and h['side']!=u['side']),None)
            enemy_distance=distance(obs,uid,enemy) if uid in scope and enemy in scope and allowed_pair(uid,enemy) else None
            target_distance=distance(obs,uid,data.get('target')) if uid in scope and data.get('target') in scope and allowed_pair(uid,data.get('target')) else None
            row=dict(frame_id=f['id'],source_time_s=f['source_time_s'],image=f['image'],
                unit_id=uid,side=u['side'],kind=u['kind'],wave=u.get('wave'),
                alive=data.get('alive'),enemy_hero_id=enemy,in_distance_scope=uid in scope,
                x_px=center[0] if center else None,y_px=center[1] if center else None,
                local_x_px=local[0] if local else None,local_y_px=local[1] if local else None,
                coordinate_method=data.get('coordinate_method','unknown'),reviewed=data.get('reviewed',False),
                action=data.get('action',''),target=data.get('target',''),phase=data.get('phase',''),
                hp=data.get('hp'),action_start_s=data.get('action_start_s'),action_end_s=data.get('action_end_s'),
                row_type='action_annotation' if data.get('action') else 'sample',
                enemy_hero_distance_px=enemy_distance,target_distance_px=target_distance,
                enemy_hero_distance_game_units_estimate=enemy_distance*factor if enemy_distance is not None and factor else None,
                target_distance_game_units_estimate=target_distance*factor if target_distance is not None and factor else None,
                movement_dt_s=movement['dt'] if movement else None,movement_px=movement['distance_px'] if movement else None,
                notes=data.get('notes',''))
            events.append(row)
        for first,second in itertools.combinations(active,2):
            if first['id'] not in scope or second['id'] not in scope:continue
            if first['side']==second['side']:continue
            if first['kind']!='hero' and second['kind']=='hero':first,second=second,first
            if first['kind']!='hero' or second['kind'] not in minion_kinds|{'hero'}:continue
            d=distance(obs,first['id'],second['id'])
            pairs.append(dict(frame_id=f['id'],source_time_s=f['source_time_s'],first=first['id'],first_side=first['side'],first_kind=first['kind'],second=second['id'],second_side=second['side'],second_kind=second['kind'],
                distance_px=d,distance_game_units_estimate=d*factor if d is not None and factor else None,
                status='measured_from_recorded_centers' if d is not None else 'unknown',
                both_reviewed=all(labelled.get(k,{}).get('reviewed',False) for k in [first['id'],second['id']])))
    write_csv(tables/'events.csv',events,EVENT_FIELDS)
    write_csv(tables/'distances.csv',pairs,DISTANCE_FIELDS)
    write_csv(tables/'deaths.csv',deaths,['unit_id','side','kind','frame_id','last_confirmed_alive_s','confirmed_dead_by_s'])
    actions=[];seen=set();last_start={}
    for row in events:
        start=row['action_start_s'];uid=row['unit_id']
        if start is None or not row['action']:continue
        key=(uid,start)
        if key in seen:continue
        seen.add(key)
        actions.append(dict(unit_id=uid,side=row['side'],action=row['action'],target=row['target'],
            action_start_s=start,action_end_s=row['action_end_s'],
            previous_action_start_gap_s=start-last_start[uid] if uid in last_start else None,
            observed_frame_id=row['frame_id'],sample_time_s=row['source_time_s']))
        last_start[uid]=start
    actions.sort(key=lambda r:(r['unit_id'],r['action_start_s']))
    last_start={}
    for row in actions:
        uid=row['unit_id'];start=row['action_start_s']
        row['previous_action_start_gap_s']=start-last_start[uid] if uid in last_start else None
        last_start[uid]=start
    write_csv(tables/'actions.csv',actions,list(actions[0]) if actions else ['unit_id','side','action','target','action_start_s','action_end_s','previous_action_start_gap_s','observed_frame_id','sample_time_s'])
    summary=dict(sample_count=len(p['frames']),unit_rows=len(events),
        rows_with_centers=sum(x['x_px'] is not None for x in events),
        rows_with_actions=sum(bool(x['action']) for x in events),unique_timed_actions=len(actions),
        reviewed_rows=sum(bool(x['reviewed']) for x in events),
        known_distance_rows=sum(x['distance_px'] is not None for x in pairs),
        unknown_distance_rows=sum(x['distance_px'] is None for x in pairs),
        csv_encoding='UTF-8 with BOM',blank_meaning='unknown or not applicable, never zero')
    write_json(tables/'coverage.json',summary)
    return summary


def export_assessment(directory, bundle=True):
    directory=Path(directory);summary=export_tables(directory)
    p=read_json(directory/'project.json');dest=directory/'assessment';dest.mkdir(exist_ok=True)
    documents=read_json(ROOT/'framework_documents.json')
    for name in documents.values():shutil.copy2(ROOT/name,dest/name)
    from .loadouts import configuration_at
    hero_data = configuration_at(directory, p, p['start_s'])
    write_json(dest/'hero_data.json',hero_data)
    if p.get('configuration'):
        write_json(dest/'configuration.json', p['configuration'])
        write_json(dest/'hero_states.json', [dict(source_time_s=s['source_time_s'],
            sides=configuration_at(directory,p,s['source_time_s'])) for s in p['configuration']['snapshots']])
        from .parameters import evaluate_project
        write_json(dest/'event_parameters.json',[evaluate_project(directory,p,s['source_time_s']) for s in p['configuration']['snapshots']])
    (dest/'strategy_reference.md').write_text(p.get('strategy_text',''),encoding='utf-8')
    (dest/'evaluation_request.md').write_text((ROOT/'docs/evaluation_request_template.md').read_text(encoding='utf-8'),encoding='utf-8')
    guide=ROOT/'docs/short_horizon.md'
    if guide.is_file():shutil.copy2(guide,dest/'planning_guide.md')
    adapter=ROOT/'templates/mechanic_adapters.json'
    if adapter.is_file():
        (directory/'templates').mkdir(exist_ok=True)
        shutil.copy2(adapter,directory/'templates'/adapter.name)
    ready=all(hero_data.get(side,{}).get('verified_effective_state') is True and hero_data.get(side,{}).get('effective_state') for side in ('blue','red'))
    write_json(dest/'manifest.json',dict(schema_version=1,hero_parameters_declared_verified=bool(ready),source_name=p['source_name'],source_sha256=p['source_sha256'],
        start_s=p['start_s'],end_s=p['end_s'],step_s=p['step_s'],calibration=p.get('calibration'),coverage=summary,
        files={f.relative_to(directory).as_posix():sha256(f) for folder in ['frames','tables','game_analysis','mechanics','templates','catalogs'] for f in (directory/folder).rglob('*') if f.is_file()},
        framework_sha256={name:sha256(dest/name) for name in documents.values()}))
    if bundle:
        archive=directory/'assessment_bundle.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as output:
            for name in ['project.json','annotations.json','frames','tables','assessment','game_analysis','mechanics','templates','catalogs']:
                path=directory/name
                for f in ([path] if path.is_file() else sorted(path.rglob('*'))):
                    if f.is_file():output.write(f,f.relative_to(directory).as_posix())
    return summary
