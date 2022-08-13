from typing import Optional, Union, List, Tuple

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.defs import SLICE
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.value import SsaValue


class SsaExprBuilderProxy():

    def __init__(self, parent:"SsaExprBuilder", var: SsaValue):
        self.parent = parent
        self.var = var

    def _normalize(self, other):
        if not isinstance(other, SsaValue):
            raise NotImplementedError()
        return other

    def __add__(self, other):
        return self.parent.binaryOp(self, AllOps.ADD, self._normalize(other))

    def __sub__(self, other):
        return self.parent.binaryOp(self, AllOps.SUB, self._normalize(other))

    def __mul__(self, other):
        return self.parent.binaryOp(self, AllOps.MUL, self._normalize(other))

    def __floordiv__(self, other):
        return self.parent.binaryOp(self, AllOps.DIV, self._normalize(other))

    def __and__(self, other):
        return self.parent.binaryOp(self, AllOps.AND, self._normalize(other))

    def __or__(self, other):
        return self.parent.binaryOp(self, AllOps.OR, self._normalize(other))

    def __xor__(self, other):
        return self.parent.binaryOp(self, AllOps.XOR, self._normalize(other))

    def __eq__(self, other):
        return self.parent.binaryOp(self, AllOps.EQ, self._normalize(other))

    def __ne__(self, other):
        return self.parent.binaryOp(self, AllOps.NE, self._normalize(other))

    def __gt__(self, other):
        return self.parent.binaryOp(self, AllOps.GT, self._normalize(other))

    def __ge__(self, other):
        return self.parent.binaryOp(self, AllOps.GE, self._normalize(other))

    def __lt__(self, other):
        return self.parent.binaryOp(self, AllOps.LT, self._normalize(other))

    def __le__(self, other):
        return self.parent.binaryOp(self, AllOps.LE, self._normalize(other))

    def __invert__(self):
        return self.parent.unaryOp(self, AllOps.NOT)

    def __neg__(self):
        return self.parent.binaryOp(self, AllOps.MINUS_UNARY)

    def __getitem__(self, key):
        return self.parent.binaryOp(self, AllOps.INDEX, self._normalize(key))


class SsaExprBuilder():

    def __init__(self, block:SsaBasicBlock, position: Optional[int]=None):
        self.block = block
        self.position = position
        # [todo] operator cache

    def setInsertPoint(self, block:SsaBasicBlock, position: Optional[int]):
        self.block = block
        self.position = position

    def _unaryOp(self, o: Union[SsaValue, HValue], operator: OpDefinition) -> SsaValue:
        o, oForTypeInference = self._normalizeOperandForOperatorResTypeEval(o)
        res = operator._evalFn(oForTypeInference)
        if o is oForTypeInference and isinstance(res, HValue):
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
        
    def unaryOp(self, o: Union[SsaValue, HValue], operator: OpDefinition) -> SsaExprBuilderProxy:
        return self.var(self._unaryOp(o.var, operator))

    def _normalizeOperandForOperatorResTypeEval(self,
                                                o: Union[SsaValue, HValue, RtlSignal, Signal]
                                                ) -> Tuple[Union[SsaValue, HValue], Union[SsaValue, HValue]]:
        """
        :returns: tuple (object for expressing, object for type inference)
        """
        if isinstance(o, Interface):
            o = o._sig
        
        if isinstance(o, HValue):
            return o, o

        elif isinstance(o, SsaValue):
            while isinstance(o, SsaPhi) and o.replacedBy is not None:
                o = o.replacedBy
            return o, o._dtype.from_py(None)

        elif o.origin is not None:
            origin = o.origin
            if isinstance(origin, SsaValue):
                return origin, o._dtype.from_py(None)

            elif isinstance(origin, Operator):
                origin: Operator
                ops = origin.operands

                if len(ops) == 1:
                    res = self._unaryOp(ops[0], origin.operator)
                elif len(ops) == 2:
                    res = self._binaryOp(ops[0], origin.operator, ops[1])
                else:
                    raise NotImplementedError(o.origin)

                if isinstance(res, HValue):
                    return res, res
                else:
                    while isinstance(res, SsaPhi) and res.replacedBy is not None:
                        res = res.replacedBy
                    return res, res._dtype.from_py(None)

            else:
                raise NotImplementedError(o.origin)

        else:
            return o, o._dtype.from_py(None)

    def _binaryOp(self, o0: Union[SsaValue, HValue, RtlSignal, Signal],
                        operator: OpDefinition,
                        o1: Union[SsaValue, HValue, RtlSignal, Signal]) -> SsaValue:
        o0, o0ForTypeInference = self._normalizeOperandForOperatorResTypeEval(o0)
        o1, o1ForTypeInference = self._normalizeOperandForOperatorResTypeEval(o1)
        
        if operator == AllOps.CONCAT:
            res = operator._evalFn(
                o1ForTypeInference,
                o0ForTypeInference,
            )
        else:
            res = operator._evalFn(
                o0ForTypeInference,
                o1ForTypeInference,
            )    
        if o0 is o0ForTypeInference and o1 is o1ForTypeInference and isinstance(res, HValue):
            return res

        instr = SsaInstr(self.block.ctx, res._dtype, operator, [o0, o1], origin=res)
        self._insertInstr(instr)
        return instr
    
    def binaryOp(self, o0: Union[SsaValue, HValue, RtlSignal, Signal],
                 operator: OpDefinition,
                 o1: Union[SsaValue, HValue, RtlSignal, Signal]) -> SsaExprBuilderProxy:
        return self.var(self._binaryOp(o0.var, operator, o1.var))

    def buildSliceConst(self, v: SsaValue, highBitNo: int, lowBitNo: int):
        i = SLICE.from_py(slice(highBitNo, lowBitNo, -1))
        return self._binaryOp(v, AllOps.INDEX, i)

    def var(self, v: SsaValue):
        return SsaExprBuilderProxy(self, v)

    def concat(self, *args) -> SsaValue:
        """
        :param args: operands for concatenation, lowest bits first
        """
        assert args
        res = None
        for p in args:
            if res is None:
                res = p
            else:
                # left must be the first, right the latest
                res = self._binaryOp(res, AllOps.CONCAT, p)
        return res

    def phi(self, args: List[Tuple[SsaValue, SsaBasicBlock]], dtype=None):
        if dtype is None:
            dtype = args[0][0]._dtype
        instr = SsaPhi(self.block.ctx, dtype)
        for val, pred in args:
            instr.appendOperand(val, pred)
        self._insertPhi(instr)
        return instr
        
    def insertBlocks(self, branchConditions: List[Optional[SsaValue]]):
        pos = self.position
        b = self.block
        blocks = [SsaBasicBlock(b.ctx, f"{b.label:s}_br{i}") for i in range(len(branchConditions))]
        
        if pos is None or pos + 1 == len(b.body) and not b.successors.targets:
            # can directly append the blocks
            raise NotImplementedError()
            sequel = None
        else:
            # must spot a sequel block, copy all instructions after this position and move all successors from original block
            sequel = SsaBasicBlock(b.ctx, b.label + "_sequel")
            if pos is not None:
                for instr in b.body[pos + 1:]:
                    instr.block = None
                    sequel.body.append(instr)
                del b.body[pos + 1:]

            for c, t, meta in b.successors.targets:
                t: SsaBasicBlock
                t.predecessors.remove(b)
                sequel.successors.addTarget(c, t).meta = meta

            b.successors.targets.clear()
            for c, t in zip(branchConditions, blocks):
                b.successors.addTarget(c, t)
                t.successors.addTarget(None, sequel)

        return blocks, sequel

