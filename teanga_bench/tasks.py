"""One Inspect task per dataset file. There is no fixed task list."""

from __future__ import annotations

from inspect_ai import Task
from inspect_ai.dataset import json_dataset

from teanga_bench.datasets import DatasetFile
from teanga_bench.scorers import teanga_scorer, teanga_solver


def build_task(dataset: DatasetFile, epochs: int) -> Task:
    return Task(
        dataset=json_dataset(str(dataset.path)),
        solver=[teanga_solver()],
        scorer=teanga_scorer(),
        epochs=epochs,
        name=f"{dataset.suite}_{dataset.test}",
        metadata={"suite": dataset.suite, "test": dataset.test, "dataset": dataset.kind},
    )
