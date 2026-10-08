"""Image pixels to floor metres through the camera homography (plan section 7)."""
from __future__ import annotations

from typing import Sequence

Matrix = list[list[float]]
Point = tuple[float, float]


def foot_point(bbox: tuple[float, float, float, float]) -> Point:
    """Bottom-centre of a bounding box: where the object touches the floor."""
    x1, _, x2, y2 = bbox
    return (x1 + x2) / 2, y2


def apply_homography(h: Matrix, u: float, v: float) -> Point:
    w = h[2][0] * u + h[2][1] * v + h[2][2]
    if abs(w) < 1e-12:
        raise ValueError("point maps to infinity")
    return (h[0][0] * u + h[0][1] * v + h[0][2]) / w, (h[1][0] * u + h[1][1] * v + h[1][2]) / w


def solve_homography(image_points: Sequence[Point], floor_points: Sequence[Point]) -> Matrix:
    """Homography from exactly four image points to their floor coordinates."""
    if len(image_points) != 4 or len(floor_points) != 4:
        raise ValueError("need exactly four point pairs")
    rows, rhs = [], []
    for (u, v), (x, y) in zip(image_points, floor_points):
        rows.append([u, v, 1, 0, 0, 0, -x * u, -x * v])
        rhs.append(x)
        rows.append([0, 0, 0, u, v, 1, -y * u, -y * v])
        rhs.append(y)
    a, b, c, d, e, f, g, h = _solve(rows, rhs)
    return [[a, b, c], [d, e, f], [g, h, 1.0]]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [list(map(float, row)) + [float(b[i])] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-10:
            raise ValueError("points are degenerate (three in a line, or repeated)")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col:
                factor = m[r][col] / m[col][col]
                m[r] = [x - factor * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


class FloorMapper:
    def __init__(self, homography: Matrix, size_m: tuple[float, float]) -> None:
        self.homography = homography
        self.size_m = size_m

    def to_floor(self, bbox: tuple[float, float, float, float]) -> Point:
        """Floor position of a detection, clamped to the floor footprint."""
        x, y = apply_homography(self.homography, *foot_point(bbox))
        return min(max(x, 0.0), self.size_m[0]), min(max(y, 0.0), self.size_m[1])
