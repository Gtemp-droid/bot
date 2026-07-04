import logging
from heapq import heappush, heappop
from typing import Dict, List, Optional

from bot.grid import IsometricGrid

log = logging.getLogger(__name__)


def astar(grid: IsometricGrid, start: int, goal: int) -> Optional[List[int]]:
    if start == goal:
        return [start]

    frontier = [(0.0, start)]
    came_from: Dict[int, Optional[int]] = {start: None}
    cost_so_far: Dict[int, float] = {start: 0.0}

    while frontier:
        _, current = heappop(frontier)
        if current == goal:
            break
        for nidx in grid.get_neighbors(current):
            new_cost = cost_so_far[current] + 1.0
            if nidx not in cost_so_far or new_cost < cost_so_far[nidx]:
                cost_so_far[nidx] = new_cost
                priority = new_cost + grid.distance(nidx, goal)
                heappush(frontier, (priority, nidx))
                came_from[nidx] = current

    if goal not in came_from:
        return None

    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = came_from[cur]
    path.reverse()
    return path


def find_nearest_walkable(grid: IsometricGrid, cell_index: int) -> Optional[int]:
    if grid.get_cell(cell_index) and grid.get_cell(cell_index).walkable:
        return cell_index
    best = None
    best_dist = float("inf")
    for c in grid.walkable_cells:
        d = grid.distance(cell_index, c)
        if d < best_dist:
            best_dist = d
            best = c
    return best
