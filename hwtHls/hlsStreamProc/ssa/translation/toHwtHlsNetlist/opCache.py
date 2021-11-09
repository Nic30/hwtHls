from typing import Union

from hwtHls.netlist.nodes.ports import HlsOperationOut, HlsOperationOutLazy
from hwtHls.tmpVariable import HlsTmpVariable


class SsaToHwtHlsNetlistOpCache():

    def __init__(self):
        self._to_hls_cache = {}

    def __contains__(self, k):
        return k in self._to_hls_cache

    def items(self):
        return self._to_hls_cache.items()

    def add(self, k, v:HlsOperationOut) -> None:
        """
        Register object in _to_hls_cache dictionary, which is used to avoid duplication of object in the circuit.
        """
        assert not isinstance(k, HlsTmpVariable), (k, "tmp variable has to always be tied to some block")
        if isinstance(v, HlsOperationOutLazy):
            assert v.replaced_by is None, (v, v.replaced_by)
            v.keys_of_self_in_cache.append(k)

        cur = self._to_hls_cache.get(k, None)
        if cur is not None:
            assert isinstance(cur, HlsOperationOutLazy), (k, cur, v)
            assert cur is not v, ("redefining the same", k, v)
            cur.replace_driver(v)
            return

        self._to_hls_cache[k] = v

    def get(self, k) -> Union[HlsOperationOut, HlsOperationOutLazy]:
        """
        Load object form _to_hls_cache dictionary, if the object is not preset temporary placeholder (HlsOperationOutLazy)
        is returned instead (and must be replaced later).
        """
        try:
            v = self._to_hls_cache[k]
            assert not isinstance(v, HlsOperationOutLazy) or v.replaced_by is None, (k, v)
            return v
        except KeyError:
            o = HlsOperationOutLazy(k, self)
            self._to_hls_cache[k] = o
            return o
