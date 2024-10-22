from typing import List

from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeFunctionPragma
from hwtHls.llvm.llvmIr import Function


class PyBytecodeSkipPass(_PyBytecodeFunctionPragma):
    """
    Skip pass by its name. For example:

    .. code-block:: llvm

        define void @main() !hwtHls.skipPass !0 {
        ...
        }
        !0 = !{!"hwtHls::SlicesToIndependentVariablesPass", !"ADCEPass"}
    """

    def __init__(self, skipedPassNames: List[str]):
        _PyBytecodeFunctionPragma.__init__(self)
        assert isinstance(skipedPassNames, (list, tuple)), skipedPassNames
        self.skipedPassNames = skipedPassNames

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", mainFn: Function):
        getStr = irTranslator.mdGetStr
        getTuple = irTranslator.mdGetTuple
        items = [getStr(passName) for passName in self.skipedPassNames]
        mainFn.setMetadata(irTranslator.strCtx.addStringRef("hwtHls.skipPass"), getTuple(items, False))
