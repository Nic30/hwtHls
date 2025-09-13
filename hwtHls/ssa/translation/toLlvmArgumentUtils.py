from typing import Union, Tuple

from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Argument, Type, HwtHlsIoMetadata
from hwtHls.frontend.ioProxy import IoProxy


def getArgumentForHwIO(toLlvm: 'ToLlvmIrTranslator',
                       hwIo: Union[HwIO, RtlSignal],
                       ioProxy: IoProxy,
                       readOrWriteObj: Union["HlsRead", "HlsWrite"],
                       isRead: bool) -> Tuple[Argument, Type]:
    """
    :attention: do not store Argument object in non-llvm objects, because it may be replaced during compilation
        and taken reference in python would not be updated
    """
    llvm: LlvmCompilationBundle = toLlvm.llvm

    argIndex = toLlvm.ioToArgIndex.get(hwIo)
    if argIndex is None:
        (ptrType, wordT, addrWidth) = ioProxy._getInterfaceTypeForLlvmFnArg(toLlvm, llvm.main.arg_size())
        toLlvm.ioToArgIndex[hwIo] = llvm.main.arg_size()
        representativeIo = hwIo[0] if isinstance(hwIo, (MultiPortGroup, BankedPortGroup)) else hwIo
        argName = HwIO_getName(toLlvm.parentHwModule, representativeIo)
        toLlvm.ioSorted.append((hwIo, wordT, addrWidth, ioProxy,
                                 [readOrWriteObj] if isRead else [],
                                 [] if isRead else [readOrWriteObj],
                                  HwtHlsIoMetadata()))
        llvm.main = llvm.main.mutateFunctionAddArg(ptrType, llvm.strCtx.addTwine(argName))
        argIndex = llvm.main.arg_size() - 1
    else:
        _, wordT, _, _, reads, writes, _ = toLlvm.ioSorted[argIndex]
        if isRead:
            reads.append(readOrWriteObj)
        else:
            writes.append(readOrWriteObj)

    hwIOArg = llvm.main.getArg(argIndex)
    assert hwIOArg.getParent() == toLlvm.llvm.main, (hwIOArg.getParent(), toLlvm.llvm.main)
    return hwIOArg, wordT

