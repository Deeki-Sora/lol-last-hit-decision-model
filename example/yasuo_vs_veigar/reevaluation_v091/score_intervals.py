"""Frozen rubric sensitivity intervals, not statistical confidence intervals."""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / 'interval_v1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calculate(data, policy):
    weights = {'strategy': data['strategy_weights'], 'execution': data['execution_weights']}
    common = set(data['common_items'])
    result = {}
    for player, ratings in sorted(data['ratings'].items()):
        bounds = [0.0, 0.0]
        for layer, mixing in [('strategy', data['omega']), ('execution', 1-data['omega'])]:
            eligible = {k: w for k, w in weights[layer].items() if k in common}
            denominator = sum(eligible.values())
            for key, weight in eligible.items():
                value = ratings[key]
                if value is None:
                    raise ValueError('Common items cannot be unknown')
                delta = policy['grade_step'] if key in policy['vary_items'] else 0.0
                bounds[0] += 100*mixing*weight*max(0, value-delta)/denominator
                bounds[1] += 100*mixing*weight*min(1, value+delta)/denominator
        result[player] = dict(lower=round(bounds[0], 6), upper=round(bounds[1], 6),
                              display_lower=math.floor(bounds[0]+1e-9),
                              display_upper=math.ceil(bounds[1]-1e-9))
    return result


def main():
    lock = json.loads((BUNDLE/'lock.json').read_text(encoding='utf-8'))
    for name, expected in lock['sha256'].items():
        path = ROOT/'score_intervals.py' if name == 'score_intervals.py' else BUNDLE/name
        if digest(path) != expected:
            raise ValueError(f'Frozen input/code changed: {name}; use a new interval version')
    data = json.loads((BUNDLE/'inputs.json').read_text(encoding='utf-8'))
    policy = json.loads((BUNDLE/'policy.json').read_text(encoding='utf-8'))
    result = calculate(data, policy)
    recorded = json.loads((BUNDLE/'result.json').read_text(encoding='utf-8'))
    if result != recorded:
        raise ValueError('Recalculation differs from the frozen result')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
