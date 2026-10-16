"""Recompute a transparent manual rubric; this is not a combat simulator."""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parent
STRATEGY = dict(window=.25, resource_plan=.20, cooldown=.15,
                cost_conversion=.15, passive=.10, rune=.05, adaptation=.10)
EXECUTION = dict(regret=.35, position=.25, resource_execution=.25, pressure=.15)

# None means unscored, not zero. Numbers are reviewer annotations, not telemetry.
RATINGS = {
    'A_Yasuo': dict(window=1, resource_plan=.75, cooldown=None,
                    cost_conversion=.50, passive=.75, rune=None, adaptation=.75,
                    regret=None, position=.75, resource_execution=.75, pressure=.75),
    'A_Veigar': dict(window=.50, resource_plan=.75, cooldown=None,
                     cost_conversion=.50, passive=.75, rune=None, adaptation=.75,
                     regret=None, position=.50, resource_execution=.75, pressure=None),
    'B_Yasuo': dict(window=1, resource_plan=1, cooldown=None,
                    cost_conversion=.75, passive=None, rune=None, adaptation=.75,
                    regret=None, position=.75, resource_execution=.75, pressure=1),
    'B_Veigar': dict(window=.75, resource_plan=.75, cooldown=None,
                     cost_conversion=.75, passive=None, rune=None, adaptation=.75,
                     regret=None, position=.75, resource_execution=.50, pressure=None),
}


def layer(ratings, weights):
    coverage = sum(w for k, w in weights.items() if ratings[k] is not None)
    subtotal = sum(w * ratings[k] for k, w in weights.items() if ratings[k] is not None)
    return dict(coverage=coverage, subtotal=subtotal, observed_score=100 * subtotal / coverage)


def evaluate(ratings, omega=.65):
    k, o = layer(ratings, STRATEGY), layer(ratings, EXECUTION)
    lower = 100 * (omega * k['subtotal'] + (1-omega) * o['subtotal'])
    coverage = omega * k['coverage'] + (1-omega) * o['coverage']
    return dict(strategy=k['observed_score'], execution=o['observed_score'],
                observed_total=omega*k['observed_score']+(1-omega)*o['observed_score'],
                strategy_coverage=k['coverage'], execution_coverage=o['coverage'],
                weighted_coverage=coverage, missing_completion_lower=lower,
                missing_completion_upper=lower+100*(1-coverage))


if __name__ == '__main__':
    assert abs(sum(STRATEGY.values()) - 1) < 1e-9
    assert abs(sum(EXECUTION.values()) - 1) < 1e-9
    assert all(v is None or v in (0, .25, .5, .75, 1)
               for r in RATINGS.values() for v in r.values())
    results = {name: evaluate(values) for name, values in RATINGS.items()}
    common = {k for k in (*STRATEGY, *EXECUTION)
              if all(r[k] is not None for r in RATINGS.values())}
    common_results = {name: evaluate({k: v if k in common else None for k, v in r.items()})
                      for name, r in RATINGS.items()}
    with (ROOT / 'level1_3_scores.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['player', *next(iter(results.values()))])
        writer.writeheader()
        writer.writerows(dict(player=name, **row) for name, row in results.items())
    (ROOT / 'level1_3_scoring_inputs.json').write_text(json.dumps(dict(
        strategy_weights=STRATEGY, execution_weights=EXECUTION, omega=.65,
        ratings=RATINGS, results=results, common_items=sorted(common),
        common_results=common_results), indent=2), encoding='utf-8')
    with (ROOT / 'level1_3_common_scores.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['player', *next(iter(common_results.values()))])
        writer.writeheader()
        writer.writerows(dict(player=name, **row) for name, row in common_results.items())
    for name, row in results.items():
        print(name, {k: round(v, 3) for k, v in row.items()})
    print('Common items:', sorted(common))
    for name, row in common_results.items():
        print(name, {k: round(v, 3) for k, v in row.items()})
    print('Strategy weight sensitivity, 0.60 to 0.70:')
    for name, ratings in RATINGS.items():
        print(name, [round(evaluate(ratings, w)['observed_total'], 2) for w in (.60, .65, .70)])
