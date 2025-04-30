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

    def __hash__(self) -> int:
        return hash(self.asTuple())

    def asTuple(self):
        return (self.__class__, tuple(self.skipedPassNames))

    def __eq__(self, other):
        return type(self) == type(other) and self.asTuple() == other.asTuple()

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", mainFn: Function):
        getStr = irTranslator.mdGetStr
        getTuple = irTranslator.mdGetTuple
        items = [getStr(passName) for passName in self.skipedPassNames]
        mdName = irTranslator.strCtx.addStringRef("hwtHls.skipPass")
        cur = mainFn.getMetadata(mdName)
        if cur is not None:
            items.extend(op.get() for op in cur.iterOperands())
        mainFn.setMetadata(mdName, getTuple(items, False))
