"""Count distinct eligible opportunities, not screenshot rows."""
import csv
import io
import json
import math

FIELDS=['opportunity_id','mechanism_id','kind','event_type','actor','target','source_time_s',
    'eligible','success','outcome_id','hit_unit_ids','window_start_s','window_end_s','context','source']


def template():
    stream=io.StringIO(newline='');csv.writer(stream).writerow(FIELDS)
    return stream.getvalue()


def boolean(value):
    value=value.strip().lower()
    if value in ('1','true'):return True
    if value in ('0','false'):return False
    if not value:return None
    raise ValueError('eligible/success must be true, false or blank')


def estimate(text):
    rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
    if not rows:return dict(models=[],observed_rates=[],coverage={'input_rows':0,'unique_opportunities':0})
    if '\ufffd' in text or '??' in text:raise ValueError('damaged observation text; restore original annotations')
    by_id={};groups={}
    for row in rows:
        if not row.get('opportunity_id') or not row.get('mechanism_id'):raise ValueError('opportunity_id and mechanism_id are required')
        key=(row['mechanism_id'],row['opportunity_id'])
        facts=tuple(row.get(k,'') for k in FIELDS if k!='source_time_s')
        if key in by_id:
            if by_id[key]!=facts:raise ValueError('conflicting repeated opportunity: '+str(key))
            continue
        by_id[key]=facts
        if row['kind'] not in ('binary','joint_hits'):raise ValueError('kind must be binary or joint_hits')
        if not row['context'] or not row['source']:raise ValueError('each opportunity needs context and evidence source')
        for key in ('source_time_s','window_start_s','window_end_s'):
            row[key]=float(row[key])
            if not math.isfinite(row[key]):raise ValueError('nonfinite observation time')
        if not row['window_start_s']<=row['source_time_s']<=row['window_end_s'] or row['window_end_s']<=row['window_start_s']:
            raise ValueError('event time must lie inside a positive declared observation window')
        row['eligible']=boolean(row['eligible']);row['success']=boolean(row['success'])
        if row['eligible'] is False and row['success'] is True:raise ValueError('success cannot be true for an explicitly ineligible opportunity')
        groups.setdefault(row['mechanism_id'],[]).append(row)
    models=[];rates=[]
    for mid,group in groups.items():
        first=group[0]
        if any((r['kind'],r['context'],r['window_start_s'],r['window_end_s'],r['actor'],r['event_type'])!=(first['kind'],first['context'],first['window_start_s'],first['window_end_s'],first['actor'],first['event_type']) for r in group):
            raise ValueError('use separate mechanism IDs for different actors, contexts, event types or observation windows')
        eligible=[r for r in group if r['eligible'] is True]
        known=[r for r in eligible if r['success'] is not None] if first['kind']=='binary' else [r for r in eligible if r['outcome_id']]
        successes=sum(r['success'] is True for r in known)
        activations=sum(r['success'] is True for r in group)
        duration=first['window_end_s']-first['window_start_s']
        rate=dict(mechanism_id=mid,event_type=first['event_type'],actor=first['actor'],unique_opportunities=len(group),
            eligibility_unknown=sum(r['eligible'] is None for r in group),eligible_opportunities=len(eligible),outcomes_known=len(known),
            outcomes_unknown=len(eligible)-len(known),window_seconds=duration,
            success_rate=successes/len(known) if known and first['kind']=='binary' else None,
            observed_confirmed_activations=activations if first['kind']=='binary' else None,
            observed_activations_per_minute=activations/duration*60 if first['kind']=='binary' else None,
            frequency_is_lower_bound=any(r['eligible'] is not False and r['success'] is None for r in group))
        rates.append(rate)
        if not known:continue
        model=dict(id=mid,kind=first['kind'],sampling='empirical',context_verified=False,context_note=first['context'],
            source=sorted({r['source'] for r in group}),event_type=first['event_type'])
        if first['kind']=='binary':model.update(eligible_trials=len(known),successes=successes)
        else:
            outcomes={}
            for r in known:
                hits=sorted(set(x.strip() for x in r['hit_unit_ids'].split(';') if x.strip()))
                if r['outcome_id'] in outcomes and outcomes[r['outcome_id']]['hits']!=hits:raise ValueError('outcome ID has conflicting hit sets')
                outcome=outcomes.setdefault(r['outcome_id'],dict(id=r['outcome_id'],hits=hits,count=0));outcome['count']+=1
            model.update(outcomes=list(outcomes.values()),distance_interval=[None,None],target_motion=None)
        models.append(model)
    return dict(models=models,observed_rates=rates,coverage=dict(input_rows=len(rows),unique_opportunities=len(by_id)),
        note='Observed conditional rates only. Verify transfer context and known deterministic mechanism rules before using in counterfactuals; unknown is not a miss.')
