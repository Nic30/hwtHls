
from typing import Dict

from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.uniqList import UniqList
from hwtHls.llvm.llvmIr import Function, Value, ValueToConstantInt, ValueToUndefValue, \
    ValueToArgument, Argument, BasicBlock, Instruction, InstructionToLoadInst, \
    LoadInst, InstructionToStoreInst, StoreInst, Type, TypeToIntegerType, IntegerType, \
    ConstantInt, InstructionToReturnInst, InstructionToBinaryOperator, BinaryOperator, \
    InstructionToICmpInst, ICmpInst, InstructionToSelectInst, SelectInst, InstructionToCallInst
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.translation.hlsNetlistExprToLlvmIr import HlsNetlistExprToLlvmIr
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from pyMathBitPrecise.bit_utils import to_unsigned


class LlvmIrExprToHlsNetlist():
    OPS_MAP = {
        Instruction.And: AllOps.AND,
        Instruction.Or: AllOps.OR,
        Instruction.Xor: AllOps.XOR,
        Instruction.Add: AllOps.ADD,
        Instruction.Sub: AllOps.SUB,
        Instruction.Mul: AllOps.MUL,
        Instruction.SDiv: AllOps.SDIV,
        Instruction.UDiv: AllOps.UDIV,
    }

    def __init__(self, netlist: HlsNetlistCtx):
        self.netlist = netlist
        self.varMap: Dict[Value, HlsNetNodeOut] = {}

    def fillInConstantNodesFromToLlvmIrExpr(self, toLlvmIr: HlsNetlistExprToLlvmIr):
        # fill in constants so we do not have to create extra nodes for them
        varMap = self.varMap
        for out in toLlvmIr.varMap.keys():
            oObj = out.obj
            if isinstance(oObj, HlsNetNodeConst):
                cur = varMap.get(oObj.val, None)
                if cur is not None and cur.obj._id <= oObj._id:
                    # skip because we use only node of constant with smallest ID to guarantee determinism
                    # as we are now iterating dictionary
                    continue
                varMap[oObj.val] = out

    def _translateType(self, t: Type):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return Bits(it.getBitWidth())
        raise NotImplementedError(t)

    def _translateExpr(self, v: Value):
        t = self._translateType(v.getType())

        ci = ValueToConstantInt(v)
        if ci is not None:
            ci: ConstantInt
            val = int(ci.getValue())
            if not t.signed and val < 0:
                val = to_unsigned(val, t.bit_length())
            v = t.from_py(val)
            # try to use already existing constant
            _v = self.varMap.get(v, None)
            if _v is None:
                self.varMap[v] = _v
                return v
            else:
                return _v

        uv = ValueToUndefValue(v)
        if uv is not None:
            v = t.from_py(None)
            # try to use already existing constant
            _v = self.varMap.get(v, None)
            if _v is None:
                self.varMap[v] = _v
                return v
            else:
                return _v

        return self.varMap[v]  # if variable was defined it must be there

    def translate(self, fn: Function, inputs: UniqList[HlsNetNodeOut], outputs: UniqList[HlsNetNodeOut]):
        newOutputs = [None for _ in range(len(outputs))]
        assert fn.arg_size() == len(inputs) + len(outputs), (fn, inputs, outputs)
        # for a, inp in zip(fn.args(), inputs):
        #     a: Argument
        #     self.varMap[a] = inp
        b: HlsNetlistBuilder = self.netlist.builder
        outputArgIndexOffset = len(inputs)
        varMap = self.varMap
        for bb in fn:
            bb: BasicBlock
            for i in bb:
                i: Instruction
                ld = InstructionToLoadInst(i)
                if ld is not None:
                    ld: LoadInst
                    _ptrArg, = ld.iterOperandValues()
                    ptrArg = ValueToArgument(_ptrArg)
                    assert ptrArg, ld
                    ptrArg: Argument
                    inI = ptrArg.getArgNo()
                    assert inI <= outputArgIndexOffset
                    varMap[i] = inputs[inI]
                    continue

                st = InstructionToStoreInst(i)
                if st is not None:
                    st: StoreInst
                    _v, _ptrArg = st.iterOperandValues()
                    v = self._translateExpr(_v)
                    ptrArg = ValueToArgument(_ptrArg)
                    assert ptrArg, st
                    ptrArg: Argument
                    outI = ptrArg.getArgNo() - outputArgIndexOffset
                    assert outI >= 0, ("Store only to output args is expected", ptrArg)
                    assert newOutputs[outI] == None, ("It is expected that every output is writen only once", st, newOutputs[outI])
                    name = i.getName().str()
                    if name and v.obj.name is None:
                        v.obj.name = name
                    newOutputs[outI] = v
                    continue

                bi = InstructionToBinaryOperator(i)
                if bi is not None:
                    bi: BinaryOperator
                    _op0, _op1 = bi.iterOperandValues()
                    op0 = self._translateExpr(_op0)
                    opc = bi.getOpcode()
                    if opc == Instruction.Xor:
                        op1c = ValueToConstantInt(_op1)
                        if op1c is not None:
                            if int(op1c.getValue()) == -1:
                                # x xor -1 -> ~x
                                v = b.buildNot(op0)
                                varMap[i] = v
                                continue
                    resT = op0._dtype
                    operator = self.OPS_MAP[opc]
                    op1 = self._translateExpr(_op1)
                    v = b.buildOp(operator, resT, op0, op1, name=i.getName().str())
                    varMap[i] = v
                    continue

                cmp = InstructionToICmpInst(i)
                if cmp is not None:
                    cmp: ICmpInst
                    _op0, _op1 = cmp.iterOperandValues()
                    pred = cmp.getPredicate()
                    op0 = self._translateExpr(_op0)
                    op1 = self._translateExpr(_op1)
                    operator: OpDefinition = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
                    assert not op0._dtype.signed, ("signed types should not be used internally", cmp, op0)
                    assert not op1._dtype.signed, ("signed types should not be used internally", cmp, op1)
                    v = b.buildOp(operator, BIT, op0, op1)
                    name = i.getName().str()
                    if name and v.obj.name is None:
                        v.obj.name = name
                    varMap[i] = v
                    continue

                si = InstructionToSelectInst(i)
                if si is not None:
                    si: SelectInst
                    opC, opV0, opV1 = (self._translateExpr(op) for op in si.iterOperandValues())
                    name = si.getName().str()
                    if not name:
                        name = None
                    v = b.buildMux(opV0._dtype, (opV0, opC, opV1), name)
                    varMap[i] = v
                    continue

                ci = InstructionToCallInst(i)
                if ci is not None:
                    fnName = ci.getCalledFunction().getName().str()
                    name = ci.getName().str()
                    if not name:
                        name = None

                    if fnName.startswith("llvm.umin."):
                        opV0, opV1 = (self._translateExpr(op.get()) for op in ci.args())
                        lt = b.buildULt(opV0, opV1)
                        v = b.buildMux(opV0._dtype, (opV0, lt, opV1), name)
                    elif fnName.startswith("llvm.umax."):
                        opV0, opV1 = (self._translateExpr(op.get()) for op in ci.args())
                        lt = b.buildULt(opV0, opV1)
                        v = b.buildMux(opV0._dtype, (opV1, lt, opV0), name)
                    else:
                        raise NotImplementedError()
                    varMap[i] = v
                    continue
                opc = i.getOpcode()
                if opc in (Instruction.SExt, Instruction.ZExt):
                    opV0, = (self._translateExpr(op) for op in i.iterOperandValues())
                    w = opV0._dtype.bit_length()
                    resTwidth = i.getType().getIntegerBitWidth()
                    if opc == Instruction.SExt:
                        if opV0._dtype.bit_length() == 1:
                            msb = opV0
                        else:
                            msb = b.buildIndexConstSlice(resT, opV0, w, w - 1)
                        v = b.buildConcat(opV0, *(msb for _ in range(resTwidth - w)))
                    else:
                        assert opc == Instruction.ZExt, opc
                        v = b.buildConcat(opV0, b.buildConst(Bits(resTwidth - w).from_py(0)))

                    name = i.getName().str()
                    if name and v.obj.name is None:
                        v.obj.name = name
                    varMap[i] = v
                    continue

                if InstructionToReturnInst(i) is not None:
                    break

                raise NotImplementedError(i)

        for o in newOutputs:
            assert o is not None, ("Each output has to have StoreInst", fn)
        return newOutputs
