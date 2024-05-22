from itertools import chain
from typing import Optional, Union, List, Tuple, Sequence

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.defs import SLICE
from hwt.hdl.types.sliceConst import HSliceConst
from hwt.hdl.const import HConst
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.value import SsaValue


class SsaExprBuilder():

    def __init__(self, block:SsaBasicBlock, position: Optional[int]=None):
        self.block = block
        self.position = position
        # [todo] operator cache

    def setInsertPoint(self, block:SsaBasicBlock, position: Optional[int]):
        self.block = block
        self.position = position

    def _unaryOp(self, o: Union[SsaValue, HConst], operator: HOperatorDef) -> SsaValue:
        o, oForTypeInference = self._normalizeOperandForOperatorResTypeEval(o)
        res = operator._evalFn(oForTypeInference)
        if o is oForTypeInference and isinstance(res, HConst):
            return res

        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o, ], origin=res)
        self._insertInstr(instr)
        return instr

    def _insertInstr(self, instr: SsaValue):
        assert isinstance(instr, SsaValue), instr
        pos = self.position
        b = self.block
        assert instr.block is None, (instr, instr.block, b)
        instr.block = b
        if pos is None:
            b.body.append(instr)
        else:
            b.body.insert(pos, instr)
            self.position += 1

    @staticmethod
    def appendPhiToBlock(block: SsaBasicBlock, instr: SsaPhi):
        assert isinstance(instr, SsaPhi), instr
        assert instr.block is None, (instr, instr.block, block)
        instr.block = block
        block.phis.append(instr)

    def _insertPhi(self, instr: SsaPhi):
        pos = self.position
        b = self.block
        assert isinstance(instr, SsaPhi)
        assert instr.block is None, (instr, instr.block, b)
        instr.block = b
        if pos is None:
            # assert not self.body, ("Adding phi if already have instructions", self, phi)
            b.phis.append(instr)
        else:
            b.phis.insert(pos, instr)
            self.position += 1

    def _normalizeOperandForOperatorResTypeEval(self,
                                                o: Union[SsaValue, HConst, RtlSignal, HwIOSignal]
                                                ) -> Tuple[Union[SsaValue, HConst], Union[SsaValue, HConst]]:
        """
        :return: tuple (object for expressing, object for type inference)
        """
        if isinstance(o, HwIO):
            o = o._sig

        if isinstance(o, HConst):
            return o, o

        elif isinstance(o, SsaValue):
            while isinstance(o, SsaPhi) and o.replacedBy is not None:
                o = o.replacedBy
            return o, o._dtype.from_py(None)

        elif o.origin is not None:
            origin = o.origin
            if isinstance(origin, SsaValue):
                return origin, o._dtype.from_py(None)

            elif isinstance(origin, HOperatorNode):
                origin: HOperatorNode
                ops = origin.operands

                if len(ops) == 1:
                    res = self._unaryOp(ops[0], origin.operator)
                elif len(ops) == 2:
                    res = self._binaryOp(ops[0], origin.operator, ops[1])
                else:
                    raise NotImplementedError(o.origin)

                if isinstance(res, HConst):
                    return res, res
                else:
                    while isinstance(res, SsaPhi) and res.replacedBy is not None:
                        res = res.replacedBy
                    return res, res._dtype.from_py(None)

            else:
                raise NotImplementedError(o.origin)

        else:
            return o, o._dtype.from_py(None)

    def _binaryOp(self, o0: Union[SsaValue, HConst, RtlSignal, HwIOSignal],
                        operator: HOperatorDef,
                        o1: Union[SsaValue, HConst, RtlSignal, HwIOSignal]) -> SsaValue:
        o0, o0ForTypeInference = self._normalizeOperandForOperatorResTypeEval(o0)
        o1, o1ForTypeInference = self._normalizeOperandForOperatorResTypeEval(o1)

        if operator == HwtOps.CONCAT:
            res = operator._evalFn(
                o1ForTypeInference,
                o0ForTypeInference,
            )
        else:
            res = operator._evalFn(
                o0ForTypeInference,
                o1ForTypeInference,
            )
        if o0 is o0ForTypeInference and o1 is o1ForTypeInference and isinstance(res, HConst):
            return res

        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o0, o1], origin=res)
        self._insertInstr(instr)
        return instr

    def _binaryOpVariadic(self, operator: HOperatorDef, ops: Sequence[Union[SsaValue, HConst, RtlSignal, HwIOSignal]]):
        assert ops
        if operator == HwtOps.CONCAT:
            ops = reversed(ops)

        instr = None
        for o in ops:
            if instr is None:
                instr = o
            else:
                instr = self._binaryOp(instr, operator, o)

        assert instr is not None
        return instr

    def buildSliceConst(self, v: SsaValue, highBitNo: int, lowBitNo: int) -> Union[SsaValue, HConst]:
        if highBitNo - lowBitNo == v._dtype.bit_length():
            return v
        elif isinstance(v, HConst):
            return v[highBitNo:lowBitNo]
        elif isinstance(v, SsaInstr):
            if v.operator == HwtOps.CONCAT:
                op0, op1 = v.operands
                half = op0._dtype.bit_length()
                if highBitNo <= half:
                    return self.buildSliceConst(op0, highBitNo, lowBitNo)
                elif lowBitNo >= half:
                    return self.buildSliceConst(op1, highBitNo - half, lowBitNo - half)

        i = SLICE.from_py(slice(highBitNo, lowBitNo, -1))
        return self._binaryOp(v, HwtOps.INDEX, i)

    def concat(self, *args) -> SsaValue:
        """
        :note: merges consequent slices
        :param args: operands for concatenation, lowest bits first
        """
        assert args
        res = None
        conseqeuentSliceSrc = None
        conseqeuentSliceLow = None
        conseqeuentSliceHigh = None
        mergedMultipleConsequentSlices = False
        lastSlice = None
        handle = object()  # using handle to check for leftover from slice merging after last item
        for p in chain(args, (handle,)):
            pIsSlice = isinstance(p, SsaInstr) and p.operator == HwtOps.INDEX and isinstance(p.operands[1], HConst)
            if pIsSlice:
                src, i = p.operands
                if isinstance(i, HSliceConst):
                    i = i.val
                    assert int(i.step) == -1, (p, i)
                    low = int(i.stop)
                    high = int(i.start)
                else:
                    i = int(i)
                    low = i
                    high = i + 1

                if conseqeuentSliceSrc is None or \
                        conseqeuentSliceSrc is not src or\
                        conseqeuentSliceHigh != low:
                    endOfSlice = conseqeuentSliceSrc is not None
                else:
                    conseqeuentSliceHigh = high
                    mergedMultipleConsequentSlices = True
                    endOfSlice = False
                    # continue
            if p is handle or not pIsSlice or endOfSlice:
                if conseqeuentSliceSrc is not None:
                    if mergedMultipleConsequentSlices:
                        # create larger slice from previous parts
                        lastSlice = self.buildSliceConst(conseqeuentSliceSrc, conseqeuentSliceHigh, conseqeuentSliceLow)

                    # lazy merge laastSlice
                    if res is None:
                        res = lastSlice
                    else:
                        # left must be the first, right the latest
                        res = self._binaryOp(res, HwtOps.CONCAT, lastSlice)

                if p is handle:
                    break

                mergedMultipleConsequentSlices = False
                if pIsSlice:
                    conseqeuentSliceSrc = src
                    conseqeuentSliceLow = low
                    conseqeuentSliceHigh = high
                    lastSlice = p
                    continue
                elif conseqeuentSliceSrc is not None:
                    conseqeuentSliceSrc = None
                    conseqeuentSliceLow = None
                    conseqeuentSliceHigh = None
                    lastSlice = None

            if res is None:
                res = p
            else:
                # left must be the first, right the latest
                res = self._binaryOp(res, HwtOps.CONCAT, p)

        return res

    def phi(self, args: List[Tuple[SsaValue, SsaBasicBlock]], dtype=None):
        if dtype is None:
            dtype = args[0][0]._dtype
        instr = SsaPhi(self.block.ctx, dtype)
        for val, pred in args:
            instr.appendOperand(val, pred)
        self._insertPhi(instr)
        return instr

    def insertBlocks(self, branchConditions: List[Tuple[Optional[SsaValue], str]]):
        """
        Split current block to predecessor block and sequel block and insert branch blocks between them with a condition specified in branchConditions.

        :note: instruction on current insert point will end up in sequel block
        """
        pos = self.position
        b = self.block
        blocks = [SsaBasicBlock(b.ctx, f"{b.label:s}_{suffix}") for (_, suffix) in branchConditions]

        if (pos is None or pos == len(b.body)) and not b.successors.targets:
            # can directly append the blocks
            raise NotImplementedError("block without any successors or instructions inside")
            sequel = None
        else:
            # must spot a sequel block, copy all instructions after this position and move all successors from original block
            sequel = SsaBasicBlock(b.ctx, b.label + "_sequel")
            if pos is not None:
                for instr in b.body[pos:]:
                    instr.block = None
                    sequel.body.append(instr)
                    instr.block = sequel
                del b.body[pos:]

            for c, t, meta in b.successors.targets:
                t: SsaBasicBlock
                t.predecessors.remove(b)
                sequel.successors.addTarget(c, t, meta=meta)

            b.successors.targets.clear()
            for (c, _), t in zip(branchConditions, blocks):
                assert c is None or isinstance(c, SsaValue), c
                b.successors.addTarget(c, t)
                t.successors.addTarget(None, sequel)

        return blocks, sequel

