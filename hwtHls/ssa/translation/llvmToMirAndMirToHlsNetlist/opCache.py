from typing import Union, Dict, Tuple

from hwt.hdl.types.hdlType import HdlType
from hwtHls.llvm.llvmIr import MachineBasicBlock, Register
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.branchOutLabel import BranchOutLabel

MirValue = Union[Register, MachineBasicBlock, BranchOutLabel]


class BranchOutLabel():
    """
    A label used in :class:`MirToHwtHlsNetlistOpCache` as a key for value which is 1 if the control is passed from src to dst.
    """

    def __init__(self, src: MachineBasicBlock, dst: MachineBasicBlock):
        self.src = src
        self.dst = dst

    def __hash__(self):
        return hash((self.__class__, self.src, self.dst))

    def __eq__(self, other):
        return type(self) is type(other) and self.src == other.src and self.dst == other.dst


class MirToHwtHlsNetlistOpCache():
    """
    :ivar _unresolvedBlockInputs: container of HlsNetNodeOutLazy object which are inputs inputs to block
        and needs to be replaced once the value is resolved in the predecessor block
    """

    def __init__(self, netlist: HlsNetlistCtx):
        self._netlist = netlist
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
                    self._moveLazyOutToUnresolvedBlockInputs(block, reg, cur, k)
            else:
                self._replaceOutOnInputOfBlock(block, reg, cur, k, v)
                return

        self._toHlsCache[k] = v

    def _moveLazyOutToUnresolvedBlockInputs(self, block: MachineBasicBlock, reg: MirValue, lazyOut: HlsNetNodeOutLazy, k):
        ubi = self._unresolvedBlockInputs.get(block, None)
        if ubi is None:
            ubi = self._unresolvedBlockInputs[block] = {}
        assert reg not in ubi
        ubi[reg] = lazyOut
        if k is not None:
            lazyOut.keys_of_self_in_cache.remove(k)

    def _replaceOutOnInputOfBlock(self, block: MachineBasicBlock, reg: MirValue, cur: HlsNetNodeOutLazy, k, v: HlsNetNodeOut):
        try:
            ubi = self._unresolvedBlockInputs[block][reg]
        except KeyError:
            ubi = None

        searchForSyncRead = False
        if isinstance(v, HlsNetNodeOut) and isinstance(v.obj, HlsNetNodeExplicitSync):
            assert v.obj._associatedReadSync is None
            searchForSyncRead = True
            
        if ubi is not None:
            ubi: HlsNetNodeOutLazy
            if searchForSyncRead:
                for user in ubi.dependent_inputs:
                    if isinstance(user.obj, HlsNetNodeReadSync):
                        v.obj._associatedReadSync = user.obj
                        break
                    
            ubi.replaceDriverObj(v)
            self._unresolvedBlockInputs[block].pop(reg)  # rm ubi
        else:
            assert isinstance(cur, HlsNetNodeOutLazy), ("redefining already defined", k, cur, v)
            # however it is possible to redefine variable if the variable was live on input of the block and
            # it comes from body of this block
            assert cur is not v, ("redefining to the same", k, v)
            if searchForSyncRead:
                for user in cur.dependent_inputs:
                    if isinstance(user.obj, HlsNetNodeReadSync):
                        v.obj._associatedReadSync = user.obj
                        break
                    
            cur.replaceDriverObj(v)
            if self._toHlsCache[k] is cur:
                self._toHlsCache[k] = v

    def get(self, block: MachineBasicBlock, v: MirValue, dtype: HdlType) -> HlsNetNodeOutAny:
        """
        Load object form _toHlsCache dictionary, if the object is not preset temporary placeholder (HlsNetNodeOutLazy)
        is returned instead (and must be replaced later).
        """
        k = (block, v)
        try:
            _v: HlsNetNodeOutAny = self._toHlsCache[k]
            assert not isinstance(_v, HlsNetNodeOutLazy) or _v.replaced_by is None, (k, v)
            assert _v._dtype == dtype or _v._dtype.bit_length() == dtype.bit_length(), ("Datatype is not what was expected", v, _v._dtype, dtype, _v)
            return _v

        except KeyError:
            o = HlsNetNodeOutLazy(self._netlist, [k], self, dtype)
            self._toHlsCache[k] = o
            return o
