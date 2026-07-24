"""Run-level metrics: accuracy, F1, AUC-ROC.

Implemented without scikit-learn so the core scoring path stays
dependency-light and unit-testable; results are cross-checked against
sklearn in the test suite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunMetrics:
    accuracy: float
    f1: float
    auc_roc: float | None
    n: int
    parse_failures: int


def f1_score(labels: list[int], predictions: list[int], positive: int = 1) -> float:
    tp = sum(1 for y, p in zip(labels, predictions) if y == positive and p == positive)
    fp = sum(1 for y, p in zip(labels, predictions) if y != positive and p == positive)
    fn = sum(1 for y, p in zip(labels, predictions) if y == positive and p != positive)
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def auc_roc(labels: list[int], scores: list[float]) -> float | None:
    """Rank-based AUC (Mann-Whitney U), with ties averaged."""
    positives = [s for y, s in zip(labels, scores) if y == 1]
    negatives = [s for y, s in zip(labels, scores) if y == 0]
    if not positives or not negatives:
        return None

    ordered = sorted(zip(scores, labels), key=lambda t: t[0])
    ranks: dict[int, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    rank_sum_pos = sum(ranks[k] for k, (_, y) in enumerate(ordered) if y == 1)
    n_pos, n_neg = len(positives), len(negatives)
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def score_binary(
    labels: list[int], predictions: list[int], scores: list[float], parse_failures: int
) -> RunMetrics:
    n = len(labels)
    accuracy = sum(1 for y, p in zip(labels, predictions) if y == p) / n if n else 0.0
    return RunMetrics(
        accuracy=accuracy,
        f1=f1_score(labels, predictions),
        auc_roc=auc_roc(labels, scores),
        n=n,
        parse_failures=parse_failures,
    )


def score_retrieval(
    correct_flags: list[bool], confidences: list[float], parse_failures: int
) -> RunMetrics:
    """Retrieval is scored as correct/incorrect selection; AUC measures
    whether the agent's own confidence separates its hits from its misses."""
    labels = [int(c) for c in correct_flags]
    predictions = [1] * len(labels)  # the agent always commits to a choice
    n = len(labels)
    accuracy = sum(labels) / n if n else 0.0
    return RunMetrics(
        accuracy=accuracy,
        f1=f1_score(labels, predictions),
        auc_roc=auc_roc(labels, confidences),
        n=n,
        parse_failures=parse_failures,
    )
