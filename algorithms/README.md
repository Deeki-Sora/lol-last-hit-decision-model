# Model utilities

`event_queue.py` implements finite-horizon event ordering and caller-supplied state transitions, corresponding to model Sections 6–7 and 50. Supply the initial state, legal events, patch-dependent tie priorities and transition function. The module contains no champion configuration or game-mechanic defaults. It returns processed and pending events at a common endpoint.

`pixel_distance.py` measures explicit health-bar-center observations, corresponding to Section 27. It computes same-frame pixel distances and movement relative to a tracked map landmark. Missing positions remain unknown. It does not detect units, fit player skill or convert pixels into game units.

Both modules use the Python standard library. Run their checks from the repository root:

```sh
python -m unittest discover -s algorithms -p "test_*.py"
```

For alternative event engines, belief search or game-theoretic solvers discussed in Section 48, see [algorithm dependencies](../docs/algorithm_dependencies.md). These utilities are building blocks rather than a complete implementation of the decision model.


`risk_value.py` also exposes `relative_state_utility()`. It centers equal receipts and equal projected states at zero, normalizes health/mana/energy by each side's own maximum, credits natural and observed recovery, and compares cooldown, summoner-spell and consumable expenditure. The published two-layer score defaults to a fixed 50:50 strategy/execution mix; callers should keep confidence and coverage separate from that mix.
