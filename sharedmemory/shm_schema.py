# shm_schema.py
from dataclasses import dataclass

import numpy as np

Schema = list[tuple[str, tuple[int, ...], type]]


CAMERA: Schema = [
    ("realsense", (720, 1280, 3), np.uint8),
]

# Example small numeric payload (add/modify as needed)
SYSTEM_STATUS: Schema = [
    ("ok", (1,), np.uint8),
    ("counter", (1,), np.int32),
    ("timestamp", (1,), np.float64),
]


@dataclass(frozen=True)
class ShmSpec:
    key: str
    schema: Schema
    lock_key: str
    shm_name: str | None = None

    def resolved_name(self) -> str:
        return self.shm_name or self.key


SHM_SPECS: tuple[ShmSpec, ...] = (
    ShmSpec(key="camera_shm", schema=CAMERA, lock_key="camera_lock"),
    ShmSpec(key="system_status_shm", schema=SYSTEM_STATUS, lock_key="system_status_lock"),
)


def build_shm_name_map(overrides: dict[str, str] | None = None) -> dict[str, str]:
    names = {spec.key: spec.resolved_name() for spec in SHM_SPECS}
    if overrides:
        names.update(overrides)
    return names
