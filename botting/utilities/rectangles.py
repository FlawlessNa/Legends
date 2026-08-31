"""
Rectangle grouping, ported from OpenCV.

`cv2.groupRectangles` was removed in OpenCV 5. It is a load-bearing part of both
template matching (`find_image`) and the configurable character-detection
pipeline, so the algorithm is reproduced here rather than approximated with
`cv2.dnn.NMSBoxes` -- NMS keeps the single best-scoring box, whereas this
clusters overlapping rectangles, averages each cluster, and rejects clusters
that too few rectangles voted for. Those are different answers.

This is a direct port of `groupRectangles` and `SimilarRects` from OpenCV 4's
`modules/objdetect/src/cascadedetect.cpp`, verified against the real
`cv2.groupRectangles` output -- see `tests/test_botting/test_rectangles.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _similar(r1: Sequence[int], r2: Sequence[int], eps: float) -> bool:
    """OpenCV's `SimilarRects` predicate: same position and size within `eps`."""
    if eps <= 0:
        return tuple(r1) == tuple(r2)
    delta = eps * (min(r1[2], r2[2]) + min(r1[3], r2[3])) * 0.5
    return (
        abs(r1[0] - r2[0]) <= delta
        and abs(r1[1] - r2[1]) <= delta
        and abs(r1[0] + r1[2] - r2[0] - r2[2]) <= delta
        and abs(r1[1] + r1[3] - r2[1] - r2[3]) <= delta
    )


def _partition(rects: list[Sequence[int]], eps: float) -> tuple[list[int], int]:
    """
    OpenCV's `partition`: union-find over the equivalence predicate.

    Note this takes the transitive closure -- two rectangles that are not
    themselves similar still land in one cluster if something is similar to
    both. That is OpenCV's behaviour and callers depend on it.
    """
    n = len(rects)
    parent = list(range(n))

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:  # path compression
            parent[i], i = root, parent[i]
        return root

    for i in range(n):
        for j in range(i + 1, n):
            if _similar(rects[i], rects[j], eps):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    roots: dict[int, int] = {}
    labels = [0] * n
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        labels[i] = roots[r]
    return labels, len(roots)


def _average(total: int, count: int) -> int:
    """
    Reproduce OpenCV's cluster averaging exactly.

    C++ computes `saturate_cast<int>(total * (1.f / count))` -- a *float32*
    reciprocal multiply, then `cvRound`, which is round-half-to-**even**. Doing
    this in float64 or with round-half-away-from-zero puts a whole pixel of
    drift into roughly a third of all clusters.
    """
    scaled = np.float32(total) * (np.float32(1.0) / np.float32(count))
    return int(np.rint(scaled))


def group_rectangles(
    rect_list: Sequence[Sequence[int]], group_threshold: int, eps: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """
    Cluster similar rectangles and keep the ones with enough support.

    Drop-in replacement for `cv2.groupRectangles`, including its quirks: a
    `group_threshold` of 0 returns the input untouched, and clusters with
    `group_threshold` or fewer members are discarded (so the common idiom of
    appending each rectangle twice is what lets a lone match survive
    `group_threshold=1`).

    :param rect_list: rectangles as (x, y, width, height).
    :param group_threshold: minimum cluster size minus one. 0 disables grouping.
    :param eps: relative tolerance for treating two rectangles as the same.
    :return: (rectangles, weights) -- the surviving averaged rectangles and the
     number of input rectangles that voted for each.
    """
    rects = [list(map(int, r)) for r in rect_list]

    if group_threshold <= 0 or not rects:
        # OpenCV returns the input untouched here, but still emits a weight of
        # 1 per rectangle rather than an empty array.
        return (
            np.array(rects, dtype=np.int32).reshape(-1, 4),
            np.ones(len(rects), dtype=np.int32),
        )

    labels, nclasses = _partition(rects, eps)

    sums = [[0, 0, 0, 0] for _ in range(nclasses)]
    weights = [0] * nclasses
    for rect, cls in zip(rects, labels):
        for k in range(4):
            sums[cls][k] += rect[k]
        weights[cls] += 1

    averaged = [
        [_average(sums[i][k], weights[i]) for k in range(4)]
        for i in range(nclasses)
    ]

    kept_rects: list[list[int]] = []
    kept_weights: list[int] = []
    for i in range(nclasses):
        r1, n1 = averaged[i], weights[i]
        if n1 <= group_threshold:
            continue

        # Drop a rectangle that sits inside a better-supported one.
        for j in range(nclasses):
            if j == i or weights[j] <= group_threshold:
                continue
            r2, n2 = averaged[j], weights[j]
            dx, dy = int(r2[2] * eps), int(r2[3] * eps)
            if (
                r1[0] >= r2[0] - dx
                and r1[1] >= r2[1] - dy
                and r1[0] + r1[2] <= r2[0] + r2[2] + dx
                and r1[1] + r1[3] <= r2[1] + r2[3] + dy
                and (n2 > max(3, n1) or n1 < 3)
            ):
                break
        else:
            kept_rects.append(r1)
            kept_weights.append(n1)

    return (
        np.array(kept_rects, dtype=np.int32).reshape(-1, 4),
        np.array(kept_weights, dtype=np.int32),
    )
