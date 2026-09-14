"""Simple stop-ordering heuristic for `ordering: auto` (nearest neighbour + 2-opt).

Works on a travel-time matrix over indices. Deliberately basic; OR-Tools replaces
this once the fully optimised scenario is built.
"""

from __future__ import annotations

Matrix = list[list[int]]


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


def order_stops(stop_indices: list[int], start: int, end: int, matrix: Matrix) -> list[int]:
    """Return `stop_indices` in visiting order for a route start -> stops -> end."""
    if len(stop_indices) <= 1:
        return list(stop_indices)
    initial = _nearest_neighbour(stop_indices, start, end, matrix)
    return _two_opt(initial, start, end, matrix)
