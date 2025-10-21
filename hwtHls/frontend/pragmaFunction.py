from typing import List

from hwt.hwIO import HwIO
from hwtHls.frontend.ioProxyStream import IoProxyStream
from hwtHls.frontend.pragma import _PyBytecodeFunctionPragma
from hwtHls.llvm.llvmIr import Function, HwtHlsIoMetadata, ThreadExtractIoFsmMetadata


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

    def __repr__(self) -> str:
        # :attention: This object is likely to be used in HwParam.
        #  This means that this methods also generates the string which is matched on HDL level
        #  to check that parameter have expected value (so it should not contain runtime dependent things like object address)
        return f"<{self.__class__.__name__:s} {self.skipedPassNames}>"


class PyBytecodeThreadExtractIoFsm(_PyBytecodeFunctionPragma):
    """
    Extract io access instructions together with private code to separate thread function
    (and create all necessary communication between original and extracted thread)

    :see: ThreadExtractIoFsmPass
    
    :ivar io: and instance of io port for which to perform the extraction
    :ivar inputBufferCapacity: size of FIFO for data passed from original code to extracted region
    :ivar outputBufferCapacity: size of FIFO for data passed from extracted region to original code
    """

    def __init__(self, io: HwIO, inputBufferCapacity:int=1, outputBufferCapacity:int=0):
        _PyBytecodeFunctionPragma.__init__(self)
        self.io = io
        self.inputBufferCapacity = inputBufferCapacity
        self.outputBufferCapacity = outputBufferCapacity

    def __hash__(self) -> int:
        return hash(self.asTuple())

    def asTuple(self):
        return (self.__class__, tuple(self.skipedPassNames))

    def __eq__(self, other):
        return type(self) == type(other) and self.asTuple() == other.asTuple()

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", mainFn: Function):
        getTuple = irTranslator.mdGetTuple

        io_ = self.io
        if isinstance(io_, IoProxyStream):
            io_ = io_.interface
        ioArgIndex = irTranslator.ioToArgIndex.get(io_)
        if ioArgIndex is None:
            raise AssertionError("The argument is not IO of function or it has not been seen yet", io_)

        _, _, _, _, _, _, md = irTranslator.ioSorted[ioArgIndex]
        md: HwtHlsIoMetadata
        ioFsmExtractMd = getTuple([
            irTranslator.mdGetStr(ThreadExtractIoFsmMetadata.METADATA_NAME),
            irTranslator.mdGetUInt32(self.inputBufferCapacity),
            irTranslator.mdGetUInt32(self.outputBufferCapacity),
            ], False)
        md.unparsedMd.append(ioFsmExtractMd.asMetadata())

    def __repr__(self) -> str:
        # :attention: This object is likely to be used in HwParam.
        #  This means that this methods also generates the string which is matched on HDL level
        #  to check that parameter have expected value (so it should not contain runtime dependent things like object address)
        return f"<{self.__class__.__name__:s} {self.ioObj}>"
