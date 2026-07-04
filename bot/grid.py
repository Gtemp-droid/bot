import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bot.config import BotConfig

log = logging.getLogger(__name__)

INVALID_CELLS = frozenset({
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
    14, 27, 28, 41, 42, 55, 56, 69, 70, 83, 84, 97, 98,
    111, 112, 125, 126, 139, 140, 153, 154, 167, 168,
    181, 182, 195, 196, 209, 210, 223, 224, 237, 238,
    251, 252, 265, 266, 279, 280, 293,
})


@dataclass
class Cell:
    index: int
    row: int
    col: int
    walkable: bool = True

    def __hash__(self):
        return self.index


class IsometricGrid:
    def __init__(self, config: BotConfig):
        self.config = config
        self.rows = config.grid_rows
        self.cols = config.grid_cols
        self.cw = config.cell_width
        self.ch = config.cell_height
        self.ox = config.grid_origin_x
        self.oy = config.grid_origin_y
        self._cells: List[Cell] = []
        self._build()

    def _build(self):
        self._cells = []
        for i in range(self.rows):
            for j in range(self.cols):
                idx = i * self.cols + j
                cell = Cell(index=idx, row=i, col=j,
                            walkable=idx not in INVALID_CELLS)
                self._cells.append(cell)

    def cell_to_screen(self, cell_index: int) -> Optional[Tuple[float, float]]:
        cell = self.get_cell(cell_index)
        if cell is None:
            return None
        d = cell.col - cell.row
        s = cell.row + cell.col
        sx = self.ox + d * (self.cw / 2) + s * self.config.grid_shear_x
        sy = self.oy + s * (self.ch / 2) + d * self.config.grid_shear_y
        return (sx, sy)

    def screen_to_cell(self, sx: float, sy: float) -> Optional[int]:
        rx = sx - self.ox
        ry = sy - self.oy
        det = (self.cw / 2) * (self.ch / 2) - self.config.grid_shear_x * self.config.grid_shear_y
        if abs(det) < 0.001:
            return None
        d = (rx * (self.ch / 2) - ry * self.config.grid_shear_x) / det
        s = (ry * (self.cw / 2) - rx * self.config.grid_shear_y) / det
        col_f = (d + s) / 2
        row_f = (s - d) / 2
        col = round(col_f)
        row = round(row_f)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            idx = row * self.cols + col
            if idx not in INVALID_CELLS:
                return idx
        return None

    def get_neighbors(self, cell_index: int) -> List[int]:
        neighbors = []
        cell = self.get_cell(cell_index)
        if cell is None:
            return neighbors
        dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        for dr, dc in dirs:
            nr, nc = cell.row + dr, cell.col + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                nidx = nr * self.cols + nc
                if nidx not in INVALID_CELLS:
                    neighbor = self._cells[nidx]
                    if neighbor.walkable:
                        neighbors.append(nidx)
        return neighbors

    def get_cell(self, index: int) -> Optional[Cell]:
        if 0 <= index < len(self._cells):
            return self._cells[index]
        return None

    def distance(self, a: int, b: int) -> float:
        ca = self.get_cell(a)
        cb = self.get_cell(b)
        if ca is None or cb is None:
            return float("inf")
        return abs(ca.row - cb.row) + abs(ca.col - cb.col)

    def set_walkable(self, cell_index: int, walkable: bool):
        cell = self.get_cell(cell_index)
        if cell:
            cell.walkable = walkable

    @property
    def cells(self) -> List[Cell]:
        return self._cells

    @property
    def walkable_cells(self) -> List[int]:
        return [c.index for c in self._cells if c.walkable]
