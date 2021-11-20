from typing import Set, Dict, Union, Callable, Tuple

from hwt.hdl.value import HValue
from hwt.serializer.utils import RtlSignal_sort_key
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwtHls.hlsStreamProc.ssa.value import SsaValue
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead


class MemorySSAUpdater():
    """
    :see: https://github.com/llvm/llvm-project/blob/4f94121cce24af28b64a9b67e2f5355bcca43574/llvm/lib/Analysis/MemorySSAUpdater.cpp

    :ivar sealedBlocks: Set of blocks connected to all direct predecessors
    """

    def __init__(self,
                 onBlockReduce: Callable[[SsaBasicBlock, SsaBasicBlock], None],
                 hwtExprToSsa: Callable[
                     [SsaBasicBlock, Union[RtlSignal, HValue]],
                     Tuple[SsaBasicBlock, Union[SsaValue, HValue]]
                ]):
        """
        :param onBlockReduce: function (old, new) called if some block is reduced
        """
        self.currentDef = {}
        self.sealedBlocks: Set[SsaBasicBlock] = set()
        self.incompletePhis: Dict[SsaBasicBlock, Dict[RtlSignal, SsaPhi]] = {}
        self._onBlockReduce = onBlockReduce
        self._hwtExprToSsa = hwtExprToSsa

    def writeVariable(self, variable: RtlSignal,
                      indexes: Tuple[Union[SsaValue, BitsVal, HSliceVal], ...],
                      block: SsaBasicBlock,
                      value: Union[SsaPhi, SsaValue, HValue]) -> int:
        """
        :param variable: A variable which is beeing written to.
        :param indexes: A list of indexes where in the variable is written.
        :param block: A bock where this is taking place.
        :param value: A value which is beeing written.

        :returns: unique index of tmp variable for phi function
        """
        defs = self.currentDef.setdefault(variable, {})
        new_bb = block
        if indexes:
            if len(indexes) != 1 or not isinstance(variable._dtype, Bits):
                raise NotImplementedError(block, variable, indexes, value)

            i = indexes[0]
            if isinstance(i, SsaValue):
                raise NotImplementedError("indexing using address variable, we need to use getelementptr etc.")

            else:
                assert isinstance(i, HValue), (block, variable, indexes, value)
                if isinstance(i, BitsVal):
                    low = int(i)
                    high = low + 1

                else:
                    assert isinstance(i, HSliceVal), (block, variable, indexes, value)
                    assert int(i.val.step) == -1, (block, variable, indexes, value)
                    low = int(i.val.stop)
                    high = int(i.val.start)

                assert isinstance(variable, RtlSignal), variable
                width = variable._dtype.bit_length()
                parts = []
                if high < width:
                    parts.append(variable[width:high])

                if isinstance(value, SsaValue) and not isinstance(value, HlsStreamProcRead):
                    assert value.origin is not None
                    parts.append(value.origin)

                else:
                    parts.append(value)

                if low > 0:
                    parts.append(variable[low:0])

                v = Concat(*parts)
                assert v._dtype.bit_length() == variable._dtype.bit_length()
                new_bb, new_var = self._hwtExprToSsa(block, v)
                value = new_var

        defs[new_bb] = value
        return new_bb

    def readVariable(self, variable: RtlSignal, block: SsaBasicBlock) -> SsaPhi:
        try:
            # local value numbering
            return self.currentDef[variable][block]
        except KeyError:
            pass

        # global value numbering
        return self.readVariableRecursive(variable, block)

    def readVariableRecursive(self, variable: RtlSignal, block: SsaBasicBlock) -> Union[SsaPhi, HValue]:
        """
        :returns: actual phi function variable or value which represents the symbolic variable in current block
        """
        if block not in self.sealedBlocks:
            # Incomplete CFG
            phi = SsaPhi(block.ctx, variable._dtype, origin=variable)
            block.appendPhi(phi)
            self.incompletePhis.setdefault(block, {})[variable] = phi

        elif len(block.predecessors) == 1:
            # Optimize the common case of one predecessor: No phi needed
            phi = self.readVariable(variable, block.predecessors[0])

        else:
            # Break potential cycles with operandless phi
            phi = SsaPhi(block.ctx, variable._dtype, origin=variable)
            block.appendPhi(phi)
            self.writeVariable(variable, (), block, phi)
            phi = self.addPhiOperands(variable, phi)

        if isinstance(phi, SsaPhi):
            self.writeVariable(variable, (), block, phi)
        elif isinstance(phi, HValue):
            pass
        else:
            raise TypeError(phi.__class__)

        return phi

    def addPhiOperands(self, variable: RtlSignal, phi: SsaPhi):
        # Determine operands from predecessors
        for pred in phi.block.predecessors:
            phi.appendOperand(self.readVariable(variable, pred), pred)

        return self.tryRemoveTrivialPhi(phi)

    def tryRemoveTrivialPhi(self, phi: SsaPhi):
        same = None
        for (op, _) in phi.operands:
            if op is same or op is phi:
                # Unique value or self−reference
                continue
            elif same is not None:
                # The phi merges at least two values: not trivial -> keep it
                return phi
            else:
                # now first unique value seen
                same = op

        if same is None:
            same = phi._dtype.from_py(None)  # The phi is unreachable or in the start block

        users = [use for use in phi.users if use is not phi]  # Remember all users except the phi itself
        phi.replaceUseBy(same)  # Reroute all uses of phi to same and remove phi
        phi.block.phis.remove(phi)
        # Try to recursively remove all phi users, which might have become trivial
        for use in users:
            if isinstance(use, SsaPhi):
                self.tryRemoveTrivialPhi(use)

        return same

    @staticmethod
    def transferBlockPhis(src: SsaBasicBlock, dst: SsaBasicBlock):
        new_phis = []
        for phi in src.phis:
            phi: SsaPhi
            # merge into some other phi if possible
            if len(phi.users) == 1:
                u = phi.users[0]
                if isinstance(u, SsaPhi):
                    u: SsaPhi
                    assert u.block is dst
                    u.operands = (*(o for o in u.operands if o[0] is not phi), *phi.operands)
                    continue

            new_phis.append(phi)
            phi.block = dst

        src.phis.clear()

        new_phis.extend(dst.phis)
        dst.phis = new_phis

    @staticmethod
    def transfertTargetsToBlock(src: SsaBasicBlock, dst: SsaBasicBlock):
        src.successors.targets.remove((None, dst))
        dst.predecessors.remove(src)

        for pred in src.predecessors:
            targets = pred.successors.targets
            for i, (cond, target) in enumerate(targets):
                if target is src:
                    targets[i] = (cond, dst)

    def sealBlock(self, block: SsaBasicBlock):
        phis = self.incompletePhis.pop(block, None)

        if phis:
            for variable, phi in sorted(
                    phis.items(),
                    key=lambda x: RtlSignal_sort_key(x[0])):
                self.addPhiOperands(variable, phi)

        # reduce the block with just phis
        for pred in tuple(block.predecessors):
            pred: SsaBasicBlock
            # if predecessors contains only phis and has only this successor unconditionally
            if pred in self.sealedBlocks and\
                    len(pred.successors) == 1 and\
                    not pred.body and\
                    pred.successors.targets[0][0] is None:

                if block.phis:
                    if not pred.predecessors:
                        # we can not propagate predecessors because there are any
                        # and the predecessor block would be missing for some phi
                        continue

                    # if the predecessor has same predecessors as this block we can not reduce
                    # because we would not be abble to select correctly in phis
                    for pp in pred.predecessors:
                        if pp in block.predecessors:
                            continue
                self.transferBlockPhis(pred, block)
                self.transfertTargetsToBlock(pred, block)
                self._onBlockReduce(pred, block)

        self.sealedBlocks.add(block)
