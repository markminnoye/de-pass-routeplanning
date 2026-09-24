"""Path-cost stop order for `ordering: auto` when the strategy is haversine.

Nearest neighbour plus 2-opt on the length of start → stops → end. That length
is the bus ride, not the longest passenger ride. A closed loop is the same
length in both directions, so after the search the route is oriented:

- `to_school`: open path that ends at the school (the deadhead out to the first
  stop is not what decides the direction). Far stops come first.
- `from_school`: the exact reverse, an open path that starts at the school.

The passenger objective lives in `busroutes.optimize` and is what
`ordering: auto` uses when the strategy is `matrix`.
"""

from __future__ import annotations

from typing import Literal

from busroutes.models import Direction

Matrix = list[list[int]]

# Where the cost matrix behind `ordering: "auto"` comes from. "matrix" is the default:
# real TomTom travel times, and the most expensive thing the evaluator does. "haversine"
# is free straight-line metres, for exploring many variants — it costs 4 to 13% more
# drive time on our own test set. See busroutes/tomtom.py.
OrderingStrategy = Literal["haversine", "matrix"]


def path_cost(path: list[int], matrix: Matrix) -> int:
    return sum(matrix[a][b] for a, b in zip(path, path[1:], strict=False))


def _nearest_neighbour(stops: list[int], start: int, end: int, matrix: Matrix) -> list[int]:
    """Build backwards from the school: the stop nearest the school is served last,
    then the stop nearest to that one, and so on. Keeps the tail of the route compact,
    which is what matters for ride time."""
    remaining = list(stops)
    order: list[int] = []
    current = end
    while remaining:
        nxt = min(remaining, key=lambda i: (matrix[i][current], i))
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt
    order.reverse()
    return order


def _two_opt(order: list[int], start: int, end: int, matrix: Matrix) -> list[int]:
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                if path_cost([start, *candidate, end], matrix) < path_cost(
                    [start, *best, end], matrix
                ):
                    best = candidate
                    improved = True
    return best


def _open_cost(order: list[int], start: int, end: int, matrix: Matrix, direction: Direction) -> int:
    """Length of the open route. `end` is the school node.

    `to_school` pays for stops → school and not for the deadhead from `start`.
    `from_school` pays for school → stops and not for a leg back.
    """
    if not order:
        return 0
    if direction == "from_school":
        return path_cost([end, *order], matrix)
    return path_cost([*order, end], matrix)


def _orient(
    order: list[int], start: int, end: int, matrix: Matrix, direction: Direction
) -> list[int]:
    """Pick the direction of a closed tour. Bus length breaks a tie."""
    reverse = list(reversed(order))

    def key(candidate: list[int]) -> tuple[int, int, list[int]]:
        closed = path_cost([start, *candidate, end], matrix)
        return (_open_cost(candidate, start, end, matrix, direction), closed, candidate)

    return min((order, reverse), key=key)


def open_route_matrix(
    matrix: Matrix, direction: Direction = "to_school"
) -> tuple[Matrix, int, int]:
    """Duration matrix with a dummy node so a solver can run an open school route.

    Node 0 of `matrix` is the school, nodes 1..n-1 are stops. The dummy is not a
    stop. `to_school` starts at the dummy (cost 0 to every stop) and ends at the
    school. `from_school` starts at the school and ends at the dummy (cost 0
    from every stop). An unused vehicle may take the direct dummy arc at cost 0.
    Arcs that would close the loop stay expensive.
    """
    n = len(matrix)
    dummy = n
    blocked = 100_000_000
    durations = [[blocked] * (n + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(n):
            durations[i][j] = matrix[i][j]
    durations[dummy][dummy] = 0
    if direction == "from_school":
        durations[0][dummy] = 0
        for stop in range(1, n):
            durations[stop][dummy] = 0
        return durations, 0, dummy
    durations[dummy][0] = 0
    for stop in range(1, n):
        durations[dummy][stop] = 0
    return durations, dummy, 0


def order_stops(
    stop_indices: list[int],
    start: int,
    end: int,
    matrix: Matrix,
    direction: Direction = "to_school",
) -> list[int]:
    """Return `stop_indices` in visiting order.

    The search still shortens start → stops → end. `direction` then picks which
    way that tour is driven. `from_school` is the reverse of `to_school`.
    """
    if direction == "from_school":
        morning = order_stops(stop_indices, start, end, matrix, direction="to_school")
        return list(reversed(morning))
    if len(stop_indices) <= 1:
        return list(stop_indices)
    initial = _nearest_neighbour(stop_indices, start, end, matrix)
    tuned = _two_opt(initial, start, end, matrix)
    return _orient(tuned, start, end, matrix, "to_school")
