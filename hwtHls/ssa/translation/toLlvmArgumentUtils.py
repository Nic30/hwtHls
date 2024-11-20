from typing import Union, Tuple, List

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIO import HwIO
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Argument, Type, PointerType
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtLib.amba.axi4Lite import Axi4Lite


def getArgumentForHwIO(toLlvm: 'ToLlvmIrTranslator', hwIo: Union[HwIO, RtlSignal],
                       readOrWriteObj: Union["HlsRead", "HlsWrite"], isRead: bool) -> Tuple[Argument, Type]:
    """
    :attention: do not store Argument object in non-llvm objects, because it may be replaced during compilation
        and taken reference in python would not be updated
    """
    argIndex = toLlvm.ioToArgIndex.get(hwIo)
    llvm: LlvmCompilationBundle = toLlvm.llvm
    if argIndex is None:
        reads = []
        writes = []
        if isRead:
            reads.append(readOrWriteObj)
        else:
            writes.append(readOrWriteObj)
        (ptrType, wordT, addrWidth) = _getInterfaceTypeForFnArg(toLlvm, hwIo, llvm.main.arg_size(), reads, writes)
        toLlvm.ioToArgIndex[hwIo] = llvm.main.arg_size()
        representativeIo = hwIo[0] if isinstance(hwIo, (MultiPortGroup, BankedPortGroup)) else hwIo
        argName = HwIO_getName(toLlvm.parentHwModule, representativeIo)
        toLlvm.ioSorted.append((hwIo, wordT, addrWidth, reads, writes))
        llvm.main = llvm.main.mutateFunctionAddArg(ptrType, llvm.strCtx.addTwine(argName))
        argIndex = llvm.main.arg_size() - 1
    else:
        _, wordT, _, reads, writes = toLlvm.ioSorted[argIndex]
        if isRead:
            reads.append(readOrWriteObj)
        else:
            writes.append(readOrWriteObj)

    hwIOArg = llvm.main.getArg(argIndex)
    assert hwIOArg.getParent() == toLlvm.llvm.main, (hwIOArg.getParent(), toLlvm.llvm.main)
    return hwIOArg, wordT


def _getInterfaceTypeForFnArg(toLlvm: 'ToLlvmIrTranslator',
                              hwio: Union[HwIO, MultiPortGroup, BankedPortGroup, RtlSignalBase],
                              ioIndex: int,
                              reads: List["HlsRead"],
                              writes: List["HlsWrite"]) -> Tuple[Type, Type]:
    wordType = None
    if reads:
        wordType = reads[0]._getNativeInterfaceWordType()
        if not reads[0]._isBlocking:
            wordType = HBits(wordType.bit_length() + 1)
        elif HdlType_isVoid(wordType):
            wordType = BIT  # can not construct load of void in llvm because isSized() returns false
        elif not isinstance(wordType, HBits):
            wordType = HBits(wordType.bit_length())

    if writes:
        _wordType = writes[0]._getNativeInterfaceWordType()
        if wordType is None or wordType is _wordType:
            wordType = _wordType
        else:
            w0 = wordType.bit_length()
            w1 = _wordType.bit_length()
            # the type may be different between read and write
            # this is for example if the write word has write mask and read has not
            # for LLVM we need just a single pointer, in this case we
            # we extend the type of pointer to larger type
            if w0 < w1:
                wordType = _wordType

    ptrT = PointerType.get(toLlvm.ctx, ioIndex + 1)
    hwio = getFirstInterfaceInstance(hwio)
    if isinstance(hwio, (HwIOBramPort_noClk, Axi4Lite)):
        addrWidth = hwio.ADDR_WIDTH
        arrTy = wordType[int(2 ** hwio.ADDR_WIDTH)]
        elmT = toLlvm._translateArrayType(arrTy)
    else:
        elmT = toLlvm._translateType(wordType)
        addrWidth = 0

    return ptrT, elmT, addrWidth
