# shm_manager.py
import numpy as np
from multiprocessing import shared_memory
import multiprocessing as mp
import inspect


def _disable_resource_tracker_for_shm() -> None:
    try:
        from multiprocessing import resource_tracker
    except Exception:
        return
    if getattr(resource_tracker, "_shm_patched", False):
        return

    orig_register = resource_tracker.register
    orig_unregister = resource_tracker.unregister

    def register(name, rtype):
        if rtype == "shared_memory":
            return
        return orig_register(name, rtype)

    def unregister(name, rtype):
        if rtype == "shared_memory":
            return
        return orig_unregister(name, rtype)

    resource_tracker.register = register
    resource_tracker.unregister = unregister
    resource_tracker._shm_patched = True


_disable_resource_tracker_for_shm()

class SharedMemoryManager:
    def __init__(self,
                 schema,#: list[tuple[str, tuple[int,...], type]],
                 lock: mp.Lock,
                 name: str):
        """
        schema: [(field_name, shape, dtype), ...]
        """
        self.lock   = lock
        self.name   = name
        self._parse_schema(schema)
        self._create_or_connect()
        # 1D byte buffer view (supports mixed dtypes per field)
        self._buf = np.ndarray((self.length,), dtype=self.dtype, buffer=self.shm.buf)

        if self._owner:
            with self.lock:
                self._buf[:] = 0

    def _parse_schema(self, schema):
        offset = 0
        self.dtype = np.uint8
        self._fields = {}
        for fname, shape, dt in schema:
            dtype = np.dtype(dt)
            cnt = int(np.prod(shape))
            nbytes = cnt * dtype.itemsize
            self._fields[fname] = {
                "shape": shape,
                "offset": offset,
                "count": cnt,
                "dtype": dtype,
                "nbytes": nbytes,
            }
            offset += nbytes
        self.length   = offset
        self.shm_size = offset

    def _create_or_connect(self):
        has_track = "track" in inspect.signature(shared_memory.SharedMemory).parameters

        def _open_existing():
            if has_track:
                try:
                    return shared_memory.SharedMemory(name=self.name, track=False)
                except TypeError:
                    pass
            return shared_memory.SharedMemory(name=self.name)

        def _create_new():
            if has_track:
                try:
                    return shared_memory.SharedMemory(
                        name=self.name, create=True, size=self.shm_size, track=False
                    )
                except TypeError:
                    pass
            return shared_memory.SharedMemory(name=self.name, create=True, size=self.shm_size)

        try:
            # 기존에 있으면 연결
            self.shm = _open_existing()
            self._owner = False
            
        except FileNotFoundError:
            # 없으면 생성 시도
            try:
                self.shm = _create_new()
                self._owner = True
            except FileExistsError:
                # 누군가 먼저 만들었으면 다시 연결
                self.shm = _open_existing()
                self._owner = False


    def write_data(self, **kwargs):
        with self.lock:
            # 1) 기존 공유메모리 전체를 복사해서 스냅샷 확보
            flat = self._buf.copy()
            # 2) 전달된 필드만 덮어쓰기
            for k, v in kwargs.items():
                meta = self._fields[k]
                arr = np.asarray(v, dtype=meta["dtype"]).reshape(-1)
                arr = np.ascontiguousarray(arr)
                arr_bytes = arr.view(np.uint8)
                s, e = meta["offset"], meta["offset"] + meta["nbytes"]
                flat[s:e] = arr_bytes
            # 3) 수정된 전체 버퍼를 한 번에 반영
            self._buf[:] = flat

    def read_data(self):
        with self.lock:
            data = self._buf.copy()
        out = {}
        for k,meta in self._fields.items():
            s = meta["offset"]
            arr = np.frombuffer(
                data,
                dtype=meta["dtype"],
                count=meta["count"],
                offset=s,
            )
            out[k] = arr.reshape(meta["shape"])
        return out

    def main_unlink(self):
        self.shm.close()
        self.shm.unlink()

    def worker_close(self):
        self.shm.close()
