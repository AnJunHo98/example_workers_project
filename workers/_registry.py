from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, Iterable, Set

from core.worker_base import WorkerContext

WorkerBuilder = Callable[[WorkerContext], object]


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    builder: WorkerBuilder
    enabled: bool = True
    daemon: bool = True
    external: bool = False
    python: str | None = None


def _build_keyboard(ctx: WorkerContext):
    from workers._keyboard_worker import KeyboardWorker

    return KeyboardWorker(ctx, hz=60.0)


def _build_single(ctx: WorkerContext):
    from workers._single_example import SingleExampleWorker

    return SingleExampleWorker(ctx, hz=100.0)


def _build_dual(ctx: WorkerContext):
    from workers._dual_example import DualExampleWorker

    return DualExampleWorker(ctx, slow_hz=100.0, fast_hz=200.0)

def _build_external(ctx: WorkerContext):
    from workers._single_example import SingleExampleWorker
    return SingleExampleWorker(ctx,hz=15.0)  



WORKER_SPECS: Dict[str, WorkerSpec] = {
    "single": WorkerSpec(name="single", builder=_build_single, enabled=True, daemon=True, 
                         external=False, python=None),
    "dual": WorkerSpec(name="dual", builder=_build_dual, enabled=True, daemon=True, 
                       external=False, python=None),
    "keyboard": WorkerSpec(name="keyboard", builder=_build_keyboard, enabled=True, daemon=True, 
                           external=False, python=None),
    "external": WorkerSpec(name="external",builder=_build_external,enabled=False,daemon=True, 
                        external=True,python=".external/bin/python"),
}


def list_worker_names() -> list[str]:
    return sorted(WORKER_SPECS.keys())


def get_worker_spec(name: str) -> WorkerSpec:
    return WORKER_SPECS[name]


def build_worker(name: str, ctx: WorkerContext):
    spec = get_worker_spec(name)
    return spec.builder(ctx)


def get_worker_specs(external_workers: Iterable[str] | None = None) -> Dict[str, WorkerSpec]:
    external = set(external_workers or [])
    specs: Dict[str, WorkerSpec] = {}
    for name, spec in WORKER_SPECS.items():
        if name in external:
            specs[name] = replace(spec, enabled=False)
        else:
            specs[name] = spec
    return specs


def parse_external_workers_env() -> Set[str]:
    return {name for name, spec in WORKER_SPECS.items() if spec.external}


def get_external_worker_python(name: str) -> str | None:
    spec = WORKER_SPECS.get(name)
    if spec is None:
        return None
    return spec.python
