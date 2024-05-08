import os
from pathlib import Path

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, parseMIR, Function
from tests.baseSsaTest import BaseSsaTC


class BaseLlvmMirTC(BaseSsaTC):

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        raise NotImplementedError("Override this in your implementation of this abstract class")

    def _test_mir_file(self):
        nameOfMain = self.getTestName()
        ctx = LlvmCompilationBundle(nameOfMain)

        inputFileName = Path(self.__FILE__).expanduser().resolve().parent / "dataIn" / (nameOfMain + ".in.mir.ll")
        with open(inputFileName) as f:
            parseMIR(f.read(), nameOfMain, ctx)
        assert ctx.module is not None

        f = ctx.module.getFunction(ctx.strCtx.addStringRef(nameOfMain))
        assert f is not None, ("specified file does not contain function of expected name", inputFileName, nameOfMain)
        ctx.main = f
        self._runTestOpt(ctx)
        MMI = ctx.getMachineModuleInfo()
        MF = MMI.getMachineFunction(f)
        assert MF is not None
        outFileName = os.path.join("data", self.__class__.__name__ + "." + nameOfMain + ".out.mir.ll")
        self.assert_same_as_file(str(MF), outFileName)

