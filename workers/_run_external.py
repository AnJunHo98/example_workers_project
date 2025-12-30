from __future__ import annotations

import argparse
from typing import Dict

import logging_mp
from core.events import EventBus, create_shared_events
from core.worker_base import WorkerContext
from ipc.manager import connect_ipc_server, decode_authkey
from sharedmemory.shm_init_clean import _init_shared_memory
from workers._registry import build_worker, list_worker_names

logger = logging_mp.get_logger(__name__)
logging_mp.basic_config(level=logging_mp.INFO)


def _parse_kv_list(items: list[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --shm value: {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _parse_name_list(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a worker in an external process.")
    parser.add_argument("--worker", required=True, choices=list_worker_names())
    parser.add_argument("--ipc-host", required=True)
    parser.add_argument("--ipc-port", type=int, required=True)
    parser.add_argument("--ipc-auth", required=True, help="Auth key hex string.")
    parser.add_argument("--shm", action="append", default=[], help="key=name (repeatable)")
    parser.add_argument("--lock", action="append", default=[], help="lock name (repeatable)")
    args = parser.parse_args(argv)

    authkey = decode_authkey(args.ipc_auth)
    manager = connect_ipc_server(args.ipc_host, args.ipc_port, authkey)

    level = create_shared_events(manager)
    bus = EventBus(level)
    
    lock_names = _parse_name_list(args.lock)
    shared_lock = {name: manager.get_lock(name) for name in lock_names}

    shm_name = _parse_kv_list(args.shm)

    main_shms = _init_shared_memory(shm_name, shared_lock)

    ctx = WorkerContext(
        name=args.worker,
        bus=bus,
        shared_lock=shared_lock,
        shm_name=shm_name,
        shared_memory=main_shms,
    )

    worker = build_worker(args.worker, ctx)
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
