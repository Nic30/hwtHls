from typing import Union, Dict, Tuple, Set
from hwtHls.llvm.llvmIr import MachineBasicBlock, Register

from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy,\
    HlsNetNodeOutAny
from hwt.hdl.types.hdlType import HdlType

MirValue = Union[Register, MachineBasicBlock]


class MirToHwtHlsNetlistOpCache():
    """
    :ivar _unresolvedBlockInputs: container of HlsNetNodeOutLazy object which are inputs inputs to block
        and needs to be replaced once the value is resolved in the predecessor block
    """
    def __init__(self):
        self._toHlsCache: Dict[object, Union[HlsNetNodeOut, HlsNetNodeOutLazy]] = {}
        self._unresolvedBlockInputs: Dict[MachineBasicBlock, Dict[object, HlsNetNodeOutLazy]] = {}

    def __contains__(self, k: Tuple[MachineBasicBlock, MirValue]):
        return k in self._toHlsCache

    def items(self):
        return self._toHlsCache.items()

    def add(self, block: MachineBasicBlock, reg: MirValue, v: HlsNetNodeOut, isFromInsideOfBlock: bool) -> None:
        """
        Register object in _toHlsCache dictionary, which is used to avoid duplication of object in the circuit.
        """
        k = (block, reg)
        if isinstance(v, HlsNetNodeOutLazy):
            assert v.replaced_by is None, (v, v.replaced_by)
            v.keys_of_self_in_cache.append(k)

        cur = self._toHlsCache.get(k, None)
        if cur is not None:
            # we already requested this value in this block or it was defined externally in advance
            cur: HlsNetNodeOutAny

            if isFromInsideOfBlock:
                # we can not replace the input itself, we need to just replace the current value
                if isinstance(cur, HlsNetNodeOutLazy):
                    ubi = self._unresolvedBlockInputs.get(block, None)
                    if ubi is None:
                        ubi = self._unresolvedBlockInputs[block] = {}
                    assert reg not in ubi
                    ubi[reg] = cur
                    cur.keys_of_self_in_cache.remove(k)
            else:
                try:
                    ubi = self._unresolvedBlockInputs[block][reg]
                except KeyError:
                    ubi = None

                if ubi is not None:
                    ubi: HlsNetNodeOutLazy
                    ubi.replace_driver(v)
                    self._unresolvedBlockInputs[block].pop(reg)
                    return
                else:
                    assert isinstance(cur, HlsNetNodeOutLazy), ("redefining already defined", k, cur, v)
                    # however it is possible to redefine variable if the variable was live on input of the block and
                    # it comes from body of this block
                    assert cur is not v, ("redefining to the same", k, v)
                    cur.replace_driver(v)
                    return

        self._toHlsCache[k] = v

    def get(self, block: MachineBasicBlock, v: MirValue, dtype: HdlType) -> HlsNetNodeOutAny:
        """
        Load object form _toHlsCache dictionary, if the object is not preset temporary placeholder (HlsNetNodeOutLazy)
        is returned instead (and must be replaced later).
        """
        k = (block, v)
        try:
            v: HlsNetNodeOutAny = self._toHlsCache[k]
            assert not isinstance(v, HlsNetNodeOutLazy) or v.replaced_by is None, (k, v)
            assert v._dtype == dtype or v._dtype.bit_length() == dtype.bit_length(), ("Datatype is not what was expected", v, v._dtype, dtype)
            return v

        except KeyError:
            o = HlsNetNodeOutLazy([k], self, dtype)
            self._toHlsCache[k] = o
            return o
