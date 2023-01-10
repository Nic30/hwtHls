from typing import Set, Dict, Union, Callable, Tuple

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.serializer.utils import RtlSignal_sort_key
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.exprBuilder import SsaExprBuilder


class MemorySSAUpdater():
    """
    :see: https://github.com/llvm/llvm-project/blob/4f94121cce24af28b64a9b67e2f5355bcca43574/llvm/lib/Analysis/MemorySSAUpdater.cpp

    :ivar sealedBlocks: Set of blocks connected to all direct predecessors
    """

    def __init__(self,
                 hwtExprToSsa: Callable[
                     [SsaBasicBlock, Union[RtlSignal, HValue]],
                     Tuple[SsaBasicBlock, Union[SsaValue, HValue]]
                ]):
        """
        :param onBlockReduce: function (old, new) called if some block is reduced
        """
        self.currentDef: Dict[RtlSignal, Dict[SsaBasicBlock, Union[SsaValue, HValue]]] = {}
        self.currentDefRev: Dict[Union[SsaValue, HValue], Dict[SsaBasicBlock, UniqList[RtlSignal]]] = {} 
        self.sealedBlocks: Set[SsaBasicBlock] = set()
        self.incompletePhis: Dict[SsaBasicBlock, Dict[RtlSignal, SsaPhi]] = {}
        self._hwtExprToSsa = hwtExprToSsa

    def writeVariable(self, variable: RtlSignal,
                      indexes: Tuple[Union[SsaValue, BitsVal, HSliceVal], ...],
                      block: SsaBasicBlock,
                      value: Union[SsaPhi, SsaValue, HValue]) -> int:
        """
        :param variable: A variable which is being written to.
        :param indexes: A list of indexes where in the variable is written.
        :param block: A block where this is taking place.
        :param value: A value which is being written.

        :return: unique index of tmp variable for PHI function
        """
        assert isinstance(variable, RtlSignal), variable
        assert isinstance(block, SsaBasicBlock), block
        if isinstance(value, SsaInstr):
            assert value.block is not None, (value, "Must not be removed from SSA")
        else:
            assert isinstance(value, HValue), value

        new_bb = block
        if indexes:
            _intf, _indexes, _sign_cast_seen = variable._getIndexCascade()
            assert not _indexes, (variable, "Must tot be a slice of signal")
            if len(indexes) != 1 or not isinstance(variable._dtype, Bits):
                raise NotImplementedError(block, variable, indexes, value)

            i = indexes[0]
            if isinstance(i, SsaValue):
                raise NotImplementedError("indexing using address variable, we need to use getelementptr/extractelement/insertelement etc.")

            else:
                assert isinstance(i, HValue), (block, variable, indexes, value)
                if isinstance(i, BitsVal):
                    assert value._dtype.bit_length() == 1, value
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
                    # append upper bits which are not modified
                    parts.append(variable[width:high])

                # append modified bits
                if isinstance(value, HlsRead):
                    parts.append(value._sig[value._dtype.bit_length():])
                
                elif isinstance(value, SsaValue):
                    assert value.origin is not None, value
                    parts.append(value.origin)

                else:
                    parts.append(value)

                # append lower unmodified bits
                if low > 0:
                    parts.append(variable[low:0])

                v = Concat(*parts)
                assert v._dtype.bit_length() == variable._dtype.bit_length(), (v, variable)
                new_bb, new_var = self._hwtExprToSsa(block, v)
                value = new_var
        else:
            assert value._dtype.bit_length() == variable._dtype.bit_length(), (variable, value._dtype, variable._dtype)

        defs = self.currentDef.setdefault(variable, {})
        defs[new_bb] = value
        self.currentDefRev.setdefault(value, {}).setdefault(new_bb, UniqList()).append(variable)
        
    def readVariable(self, variable: RtlSignal, block: SsaBasicBlock) -> SsaPhi:
        assert isinstance(variable, RtlSignal), variable
        assert isinstance(block, SsaBasicBlock), block
        try:
            # local value numbering
            v = self.currentDef[variable][block]
            assert isinstance(v, HValue) or v.block is not None, (v, "was already removed from SSA and should not be there")
            # if this assert fails it may be consequence of wrong block sealing which resulted in a situation where the PHI
            # was optimized out before block which used this PHI was added
            return v
        except KeyError:
            pass

        # global value numbering
        return self.readVariableRecursive(variable, block)

    def readVariableRecursive(self, variable: RtlSignal, block: SsaBasicBlock) -> Union[SsaPhi, HValue]:
        """
        :return: actual phi function variable or value which represents the symbolic variable in current block
        """
        if block not in self.sealedBlocks:
            # Incomplete CFG
            v = SsaPhi(block.ctx, variable._dtype, origin=variable)
            SsaExprBuilder.appendPhiToBlock(block, v)
            self.incompletePhis.setdefault(block, {})[variable] = v

        elif len(block.predecessors) == 1:
            # Optimize the common case of one predecessor: No phi needed
            v = self.readVariable(variable, block.predecessors[0])

        else:
            # Break potential cycles with operandless phi
            v = SsaPhi(block.ctx, variable._dtype, origin=variable)
            SsaExprBuilder.appendPhiToBlock(block, v)
            self.writeVariable(variable, (), block, v)
            v = self.addPhiOperands(variable, v)

        if isinstance(v, (SsaPhi, SsaInstr)):
            self.writeVariable(variable, (), block, v)
        elif isinstance(v, (HValue, HlsRead)):
            pass
        else:
            raise TypeError(v.__class__)
        
        assert isinstance(v, HValue) or v.block is not None, (v, "was already removed from SSA and should not be there")
        return v

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
        elif isinstance(same, SsaValue):
            assert same.block is not None

        users = [use for use in phi.users if use is not phi]  # Remember all users except the phi itself
        phi.replaceUseBy(same)  # Reroute all uses of phi to same and remove phi
        phi.block.phis.remove(phi)
        phi.block = None
        sameIsAlsoPhi = isinstance(same, SsaPhi)
        for b, varList in self.currentDefRev[phi].items():
            for v in varList:
                d = self.currentDef.setdefault(v, {})
                if d[b] is phi:
                    d[b] = same
                    if sameIsAlsoPhi:
                        self.currentDefRev[same].setdefault(b, UniqList()).append(v)
        del self.currentDefRev[phi]

        # Try to recursively remove all phi users, which might have become trivial
        for use in users:
            if isinstance(use, SsaPhi) and use.block is not None:
                # potentially could be already removed
                self.tryRemoveTrivialPhi(use)

        return same

    def sealBlock(self, block: SsaBasicBlock):
        assert block not in self.sealedBlocks, ("Block can be sealed only once", block)
        phis = self.incompletePhis.pop(block, None)

        if phis:
            for variable, phi in sorted(
                    phis.items(),
                    key=lambda x: RtlSignal_sort_key(x[0])):
                self.addPhiOperands(variable, phi)

        # :note: can not reduce trivial blocks because we may need their defs later
        self.sealedBlocks.add(block)
