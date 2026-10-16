"""Finite-horizon event scheduling with caller-supplied state transitions."""
from dataclasses import dataclass, field
from copy import deepcopy
import heapq
import math
from typing import Any, Callable


@dataclass(order=True, frozen=True)
class Event:
    time: float
    priority: int
    id: str
    kind: str = field(compare=False)
    payload: Any = field(default=None, compare=False)


@dataclass
class Transition:
    state: Any
    events: tuple[Event, ...] = ()


@dataclass
class Result:
    state: Any
    processed: tuple[Event, ...]
    pending: tuple[Event, ...]


def advance(initial_state: Any, events: list[Event], transition: Callable,
            start: float, end: float, max_events: int = 100000) -> Result:
    """Process through end inclusively; priority then id breaks time ties.

    transition(state, event) must return Transition. It supplies all game
    mechanics, including legality, damage, cancellation and reward accounting.
    No champion configuration, targeting policy or initial state is bundled.
    """
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ValueError('finite start <= end is required')
    if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events <= 0:
        raise ValueError('max_events must be a positive integer')
    queue, seen, processed = [], set(), []

    def add(event, now, floor=None):
        if not isinstance(event, Event) or not math.isfinite(event.time) or event.time < now:
            raise ValueError('events require finite times at or after current time')
        if not event.id or event.id in seen:
            raise ValueError('event ids must be nonempty and globally unique')
        if floor is not None and event.time == now and event < floor:
            raise ValueError('generated simultaneous event precedes its cause in tie order')
        seen.add(event.id)
        heapq.heappush(queue, event)

    for event in events:
        add(event, start)
    state = deepcopy(initial_state)
    while queue and queue[0].time <= end:
        if len(processed) >= max_events:
            raise RuntimeError('event limit reached; inspect zero-time event cycles')
        event = heapq.heappop(queue)
        update = transition(state, event)
        if not isinstance(update, Transition):
            raise TypeError('transition must return Transition')
        state = update.state
        processed.append(event)
        for child in update.events:
            add(child, event.time, event)
    return Result(state, tuple(processed), tuple(sorted(queue)))
