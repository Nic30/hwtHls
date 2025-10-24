from itertools import chain, islice
from typing import List, Tuple, Union

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import Type, BasicBlock, PointerType, Argument, verifyFunction, \
    Value
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class HlsNetlistExprToLlvmIr(ToLlvmIrTranslator):

    def __init__(self, llvmModuleName: str):
        parentHwModule = None
        super(HlsNetlistExprToLlvmIr, self).__init__(parentHwModule, [], llvmModuleName=llvmModuleName)

    @override
    def _translateExprToLlvm(self, block: BasicBlock, var: Union[HlsNetNodeOut, Value], allowHConst:bool=False) -> Tuple[BasicBlock, Value]:
        if isinstance(var, Value):
            return block, var

        varDict = self._variableInBlock.get(block, None)
        assert varDict is not None
        # check for case that expression was already translated in this block
        cur = varDict.get(var, None)
        if cur is not None:
            return block, cur

        obj = var.obj
        if isinstance(obj, HlsNetNodeConst):
            v = obj.val
            c = self._translateExprHConst(block, v)
            varDict[var] = c
            return block, c
        else:
            assert isinstance(obj, HlsNetNodeOperator), obj
            block, v = self._translateExprOperator(block, obj, obj.operator, obj._outputs[0]._dtype, obj.dependsOn, obj.name)
            varDict[var] = v
            return block, v

    def translate(self, inputs: SetList[HlsNetNodeOut], outputs: SetList[HlsNetNodeOut]):
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
        self.llvm.main = main = self.createFunctionPrototype("main", params, Type.getVoidTy(self.ctx))
        b = self.b
        mainBB = BasicBlock.Create(self.ctx, strCtx.addTwine("entry"), main, None)
        b.SetInsertPoint(mainBB)

        varDict = self._variableInBlock[mainBB] = {}
        for a, o, (_, ptrT, t, _) in zip(main.args(), inputs, params):
            a: Argument
            o: HlsNetNodeOut
            self.ioToArgIndex[o] = a.getArgNo()
            varDict[o] = b.CreateLoad(t, a, False, strCtx.addTwine(a.getName().str()))

        for a, o, (_, ptrT, t, _) in zip(islice(main.args(), len(inputs), None), outputs, params):
            a: Argument
            o: HlsNetNodeOut
            t: Type
            assert o not in inputs, o
            _block, src = self._translateExprToLlvm(mainBB, o)
            assert _block == mainBB, (_block, mainBB)
            b.CreateStore(src, a, True)

        b.CreateRetVoid()
        assert verifyFunction(main) is False

