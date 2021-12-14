from typing import Union, Tuple, Dict

from hwtHls.netlist.nodes.ports import HlsOperationOut, HlsOperationOutLazy
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.basicBlock import SsaBasicBlock


class SsaToHwtHlsNetlistOpCache():

    def __init__(self):
        self._to_hls_cache: Dict[object, Union[HlsOperationOut, HlsOperationOutLazy]] = {}
        self.oldPhiCyclicArgs: Dict[Tuple[SsaBasicBlock, SsaValue], HlsOperationOutLazy] = {}

    def __contains__(self, k):
        return k in self._to_hls_cache

    def items(self):
        return self._to_hls_cache.items()

    def add(self, k, v:HlsOperationOut, isDefOfPhiCyclicArg: bool) -> None:
        """
        Register object in _to_hls_cache dictionary, which is used to avoid duplication of object in the circuit.

        :param isDefOfPhiCyclicArg: True if we are adding the definition of a variable which is also a phi argument in some predecessor
            and is virtually used in phi before its definition.
            For this type of variables we need to keep 2 values (before def. and after).
            This happens for variables in cycles which are defined somewhere in loop body and are used in cycle header PHIs.
        """
        assert not isinstance(k, SsaValue), (k, "variables have to be added always in format tuple(bloc, var)")
        if isinstance(v, HlsOperationOutLazy):
            assert v.replaced_by is None, (v, v.replaced_by)
            v.keys_of_self_in_cache.append(k)

        cur = self._to_hls_cache.get(k, None)
        if cur is not None:
            cur: HlsOperationOutLazy
            if isDefOfPhiCyclicArg:
                assert k not in self.oldPhiCyclicArgs, (k, self.oldPhiCyclicArgs[k])
                self.oldPhiCyclicArgs[k] = cur
                if isinstance(cur, HlsOperationOutLazy):
                    for k in cur.keys_of_self_in_cache:
                        self._to_hls_cache[k] = v
                    cur.keys_of_self_in_cache.clear()
                    return

            else:
                assert isinstance(cur, HlsOperationOutLazy), ("redefinig already defined", k, cur, v)
                # however it is possible to redefine variable if the variable was live on input of the block and
                # it comes from body of this block
                assert cur is not v, ("redefining to the same", k, v)
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
