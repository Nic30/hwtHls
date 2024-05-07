from itertools import chain, islice
from typing import List

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.frontend.ast.astToSsa import IoPortToIoOpsDictionary
from hwtHls.llvm.llvmIr import Type, BasicBlock, PointerType, Argument, verifyFunction
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class HlsNetlistExprToLlvmIr(ToLlvmIrTranslator):

    def __init__(self, label: str):
        topIo: IoPortToIoOpsDictionary = {}
        parentUnit = None
        super(HlsNetlistExprToLlvmIr, self).__init__(label, topIo, parentUnit)

    def _translateExpr(self, out: HlsNetNodeOut):
        v = self.varMap.get(out, None)
        if v is not None:
            return v

        obj = out.obj
        if isinstance(obj, HlsNetNodeConst):
            v = obj.val
            c = self._translateExprHValue(v)
            self.varMap[out] = c
            return c
        else:
            assert isinstance(obj, HlsNetNodeOperator), obj
            ops = obj.dependsOn
            if obj.operator == AllOps.TERNARY:
                assert len(ops) == 3
                ops = (ops[1], ops[0], ops[2])

            v = self._translateExprOperand(obj.operator, obj._outputs[0]._dtype, ops, obj.name, obj)
            self.varMap[out] = v
            return v

    def translate(self, inputs: UniqList[HlsNetNodeOut], outputs: UniqList[HlsNetNodeOut]):
        # name, pointer type, element type, address width
        params: List[str, Type, Type, int] = []
        for ioIndex, io in enumerate(chain(inputs, outputs)):
            io: HlsNetNodeOut
            wordType = io._dtype
            ptrT = PointerType.get(self.ctx, ioIndex + 1)
            elmT = self._translateType(wordType)
            name = io.getPrettyName()
            params.append((name, ptrT, elmT, 0))

        strCtx = self.strCtx
        self.llvm.main = main = self.createFunctionPrototype(self.label, params, Type.getVoidTy(self.ctx))
        b = self.b
        mainBB = BasicBlock.Create(self.ctx, strCtx.addTwine("entry"), main, None)
        b.SetInsertPoint(mainBB)

        ioToVar = self.ioToVar
        for a, o, (_, ptrT, t, _) in zip(main.args(), inputs, params):
            a: Argument
            o: HlsNetNodeOut
            ioToVar[o] = (a, ptrT, t)
            self.varMap[o] = b.CreateLoad(t, a, False, strCtx.addTwine(a.getName().str()))

        for a, o, (_, ptrT, t, _) in zip(islice(main.args(), len(inputs), None), outputs, params):
            a: Argument
            o: HlsNetNodeOut
            t: Type
            assert o not in inputs, o
            src = self._translateExpr(o)
            b.CreateStore(src, a, True)

        b.CreateRetVoid()
        assert verifyFunction(main) is False

