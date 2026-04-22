#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, VectorOfTypePtr, FunctionType, \
    Function, Type, HwtHlsIoMetadataSmallVector, HwtHlsIoMetadata, IODirection, \
    BasicBlock, HwtHlsIoMetadata_set, HwtHlsIoMetadata_get, \
    VectorOfStringRef, PointerType


class LlvmIrFunctionMutating_TC(unittest.TestCase):
    mdCommon2 = (
        True, # hasBlockingLoad
        True, # hasBlockingStore 
        0,  # bufferCapacity
        None,  # ioPropertyPath
        None,  # latenciesFromPredecessorIo
        None,  # protocolSpecificMetadata
        None,  # ioVectorization 
    )

    def _createFunctionPrototype(self,
                                 ctx: LlvmCompilationBundle,
                                 returnType: Type,
                                 name:str,
                                 params: list[tuple[str, Type]]) -> Function:
        strCtx = ctx.strCtx
        _argTypes = VectorOfTypePtr()
        for _, t in params:
            _argTypes.append(t)

        FT = FunctionType.get(returnType, _argTypes, False)
        F = Function.Create(FT, Function.LinkageTypes.ExternalLinkage, strCtx.addTwine(name), ctx.module)

        for a, (aName, _) in zip(F.args(), params):
            a.setName(strCtx.addTwine(aName))
        return F

    def _createFunction(self, ctx: LlvmCompilationBundle, name: str, paramCnt: int):
        params = [(f"a{argI}", PointerType.get(ctx.ctx, argI + 1)) for argI in range(paramCnt)]
        F: Function = self._createFunctionPrototype(ctx, Type.getVoidTy(ctx.ctx), name, params)
        BasicBlock.Create(ctx.ctx, ctx.strCtx.addTwine("bb0"), F, None)
        return F

    def _getFunctions(self, ctx: LlvmCompilationBundle, fnNames: tuple[str]):
        return (ctx.module.getFunction(ctx.strCtx.addStringRef(fnName)) for fnName in fnNames)

    def test_addHwtHlsIoMD(self):
        ctx = LlvmCompilationBundle("test", [])
        F = self._createFunction(ctx, "f0", 2)
        hwtHlsIoMds = HwtHlsIoMetadataSmallVector()
        for i in range(2):
            dir_ = IODirection.IO_DIR_IN
            addrWidth = 0
            readWidth = 8
            writeWidth = 8
            md = HwtHlsIoMetadata(dir_, addrWidth, readWidth, writeWidth, 
                                  None,  # otherThreadFn
                                  i,  # otherArgIndex
                                  * self.mdCommon2
                                  )
            hwtHlsIoMds.push_back(md)

        HwtHlsIoMetadata_set(F, hwtHlsIoMds)

        hwtHlsIoMds2 = HwtHlsIoMetadata_get(F)
        self.assertSequenceEqual(hwtHlsIoMds, hwtHlsIoMds2)

        F.setMetadata(ctx.strCtx.addStringRef(HwtHlsIoMetadata.METADATA_NAME), None)

        paramTypes = VectorOfTypePtr()
        paramTypes.append(PointerType.get(ctx.ctx, 3))
        paramTypes.append(PointerType.get(ctx.ctx, 4))
        paramNames = VectorOfStringRef()
        paramNames.append(ctx.strCtx.addStringRef('a2'))
        paramNames.append(ctx.strCtx.addStringRef('a3'))
        F = F.mutateFunctionAddArgs(paramTypes, paramNames)
        hwtHlsIoMds2 = HwtHlsIoMetadata_get(F)
        self.assertEqual(str(F),
"""\
define void @f0(ptr addrspace(1) %a0, ptr addrspace(2) %a1, ptr addrspace(3) %a2, ptr addrspace(4) %a3) {
bb0:
}
""")
        F = F.mutateFunctionShuffleArgs([2, 3, 0, 1])
        self.assertEqual(str(F),
"""\
define void @f0(ptr addrspace(1) %a2, ptr addrspace(2) %a3, ptr addrspace(3) %a0, ptr addrspace(4) %a1) {
bb0:
}
""")

    def test_shuffleArgsOfConnectedFunctions(self):
        ctx = LlvmCompilationBundle("test", [])
        F0 = self._createFunction(ctx, "f0", 3)
        F1 = self._createFunction(ctx, "f1", 2)

        addrWidth = 0
        readWidth = 8
        writeWidth = 8
        mdCommon = (addrWidth, readWidth, writeWidth, )
        mdCommon2 = self.mdCommon2
        IN = IODirection.IO_DIR_IN
        OUT = IODirection.IO_DIR_OUT
        hwtHlsIoMds = HwtHlsIoMetadataSmallVector()
        hwtHlsIoMds.push_back(HwtHlsIoMetadata(IN, *mdCommon, None, 0, *mdCommon2))
        hwtHlsIoMds.push_back(HwtHlsIoMetadata(OUT, *mdCommon, F1, 0, *mdCommon2))
        hwtHlsIoMds.push_back(HwtHlsIoMetadata(IN, *mdCommon, F1, 1, *mdCommon2))
        HwtHlsIoMetadata_set(F0, hwtHlsIoMds)

        hwtHlsIoMds = HwtHlsIoMetadataSmallVector()
        hwtHlsIoMds.push_back(HwtHlsIoMetadata(IN, *mdCommon, F0, 1, *mdCommon2))
        hwtHlsIoMds.push_back(HwtHlsIoMetadata(OUT, *mdCommon, F0, 2, *mdCommon2))
        HwtHlsIoMetadata_set(F1, hwtHlsIoMds)

        F0 = F0.mutateFunctionShuffleArgs([1, 2, 0], argsToDiscardFromEndCnt=1)
        self.assertEqual(str(F0),
"""\
define void @f0(ptr addrspace(1) %a1, ptr addrspace(2) %a2) !hwtHls.io !0 {
bb0:
}
""")
        self.assertEqual(str(F1),
"""\
define void @f1(ptr addrspace(1) %a0, ptr addrspace(2) %a1) !hwtHls.io !3 {
bb0:
}
""")
        md0 = list(HwtHlsIoMetadata_get(F0))
        md1 = list(HwtHlsIoMetadata_get(F1))
        self.assertSequenceEqual(md0,
                                 [HwtHlsIoMetadata(OUT, *mdCommon, F1, 0, *mdCommon2),
                                  HwtHlsIoMetadata(IN, *mdCommon, F1, 1, *mdCommon2)])
        self.assertSequenceEqual(md1,
                                 [HwtHlsIoMetadata(IN, *mdCommon, F0, 0, *mdCommon2),
                                  HwtHlsIoMetadata(OUT, *mdCommon, F0, 1, *mdCommon2)])

    def test_shuffleArgsRmArg2(self):
        ctx = LlvmCompilationBundle("test", [])
        F0 = self._createFunction(ctx, "f0", 4)
        IN = IODirection.IO_DIR_IN
        hwtHlsIoMds = HwtHlsIoMetadataSmallVector()
        addrWidth = 0
        readWidth = 8
        writeWidth = 8
        mdCommon = (addrWidth, readWidth, writeWidth, )
        for i in range(4):
            hwtHlsIoMds.push_back(HwtHlsIoMetadata(IN, *mdCommon, None, i, *self.mdCommon2))
        HwtHlsIoMetadata_set(F0, hwtHlsIoMds)
        F0 = F0.mutateFunctionShuffleArgs([0, 3, 1, 2], 1)
        self.assertEqual(str(F0),
"""\
define void @f0(ptr addrspace(1) %a0, ptr addrspace(2) %a3, ptr addrspace(3) %a1) !hwtHls.io !0 {
bb0:
}
""")


if __name__ == "__main__":
    unittest.main()
