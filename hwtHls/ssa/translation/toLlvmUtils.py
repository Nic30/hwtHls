import re
from typing import Union

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.struct import HStructField, HStruct, offsetof
from hwt.hwIO import HwIO
from hwtHls._llvmOpDefUtils import _llvmIntZExtConstructor, _llvmIntSExtConstructor
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.llvm.llvmIr import IRBuilder, Function, Type, LoopInfo, Twine, Value, \
    HwtHlsIoMetadata, HwtHlsIoMetadataSmallVector, LlvmCompilationBundle, HwtHlsIoMetadata_set, \
    IODirection
from hwtHls.frontend.ioProxy import IoProxy


class _USE_DEFAULT_IO_NODE_CONSTRUCTOR():
    pass


NetlistIoConstructorDictT = dict[HwIO, IoProxy]

RE_ID_WITH_NUMBER = re.compile('[^0-9]+|[0-9]+')

NaturalSortKey = tuple[Union[str, int]]

ToLlvmIoRecordTuple = tuple[Union[HwIO, MultiPortGroup, BankedPortGroup],
                            Type,  # elmT
                            int,  # addrWidth
                            IoProxy,
                            list[HlsRead],
                            list[HlsWrite],
                            HwtHlsIoMetadata]


def splitStrToStrsAndInts(name: str) -> NaturalSortKey:
    """
    Create a sorting key for natural sorting 
    """
    key = []
    for part in RE_ID_WITH_NUMBER.findall(name):
        try:
            key.append(int(part))
        except ValueError:
            key.append(part)
    return tuple(key)


def llvmFunctionSortArgsByName(toLlvm: "ToLlvmIrTranslator"):
    args: list[tuple[int, NaturalSortKey, ToLlvmIoRecordTuple]] = [
        (i, splitStrToStrsAndInts(arg.getName().str()), argTuple)
        for i, (argTuple, arg) in enumerate(zip(toLlvm.ioSorted, toLlvm.llvm.main.args()))
    ]
    args.sort(key=lambda x: x[1])
    orderIsChanged = False
    for i, (newI, _, _) in enumerate(args):
        if i != newI:
            orderIsChanged = True
            break

    if orderIsChanged:
        toLlvm.ioToArgIndex = {a[2][0]: i for i, a in enumerate(args)}
        toLlvm.ioSorted = [ioTuple for _, _, ioTuple in args]
        toLlvm.llvm.main = toLlvm.llvm.main.mutateFunctionShuffleArgs([i for i, _, _ in args])


def addHwtHlsFunctionIoMetadata(toLlvm: "ToLlvmIrTranslator"):
    """
    :attention: expects :func:`~.sortFunctionArgsByName` to be applied
    """
    F: Function = toLlvm.llvm.main
    assert F.arg_size() == len(toLlvm.ioSorted), (F.arg_size(), len(toLlvm.ioSorted))
    hwtHlsIoMds = HwtHlsIoMetadataSmallVector()
    for i, (_, _, addrWidth, proxy, reads, writes, md) in enumerate(toLlvm.ioSorted):
        proxy: IoProxy
        md: HwtHlsIoMetadata
        dir_ = IODirection.IO_DIR_OUT if writes else\
               IODirection.IO_DIR_IN if reads else\
               IODirection.IO_DIR_UNRESOLVED
        readWidth = 0
        writeWidth = 0
        hasBlockingRead = True
        hasBlockingStore = True
        protocolSpecificMd = None
        if reads:
            if proxy.hasBlockingRead is not None:
                hasBlockingRead &= proxy.hasBlockingRead

            t = proxy.getDataTypeOfNativeRead()
            readWidth = t.bit_length()
            if proxy.hasBlockingRead is not None and not proxy.hasBlockingRead:
                readWidth += 1
            readWidth = max(1, readWidth)

        if writes:
            if proxy.hasBlockingWrite is not None:
                hasBlockingStore &= proxy.hasBlockingWrite
            t = proxy.getDataTypeOfNativeWrite()
            writeWidth = max(1, t.bit_length())

        protocolSpecificMd = proxy._getLlvmIoProtocolMetadata(toLlvm)

        md.direction = dir_
        md.addrWidth = addrWidth
        md.readWordWidth = readWidth
        md.writeWordWidth = writeWidth
        md.hasBlockingLoad = hasBlockingRead
        md.hasBlockingStore = hasBlockingRead
        md.otherThreadFn = None
        md.otherArgIndex = i
        md.bufferCapacity = 0
        md.ioPropertyPath = None
        md.latenciesFromPredecessorIo = None
        md.ioProtocolMd = protocolSpecificMd
        proxy.updateLlvmHwtHlsIoMetadata(toLlvm, md)

        hwtHlsIoMds.push_back(md)

    HwtHlsIoMetadata_set(F, hwtHlsIoMds)


def  getIoNodeConstructors(toLlvm: "ToLlvmIrTranslator") -> NetlistIoConstructorDictT:
    res: NetlistIoConstructorDictT = {}
    for hwIO, argIndex in toLlvm.ioToArgIndex.items():
        _, _, _, ioProxy, _, _, _ = toLlvm.ioSorted[argIndex]
        res[hwIO] = ioProxy
    return res


def applyLateLoopPragma(toLlvm: "ToLlvmIrTranslator"):

    def collectLoops(LI: LoopInfo):
        for header, pragmas in toLlvm._lateLoopPragmaToApply:
            assert len(pragmas) == 1, "Only 1 loop metadata per loop, to chain more use followup property"
            L = LI.getLoopFor(header)
            assert L, ("block is not in any loop, there is no place to add this loop pragma", header, pragmas)
            loopId = L.getLoopID()
            assert loopId is None, "Only 1 loop metadata per loop, to chain more use followup property"
            pragma = pragmas[0]
            items = pragma.getLlvmLoopMetadataItems(toLlvm)
            getTuple = toLlvm.mdGetTuple
            llvmLoopMd = getTuple(items, True)
            L.setLoopID(llvmLoopMd)

    toLlvm.llvm.runLoopAnalysisGet(collectLoops)


def ToLlvmIrTranslator_createOperatorConstructorDictionaries(b: IRBuilder):

    def _truncConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        resTy = b.getIntNTy(int(instr.operands[1]))
        return b.CreateTrunc(op0, resTy, name)

    def _dotToBitRangeGetConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        a0 = instr.operands[0]
        structTy: HStruct = a0._dtype
        structTyField: HStructField = a0._dtype.field_by_name[op1]
        offset = offsetof(structTy, structTyField)
        return b.CreateBitRangeGetConst(op0, offset, structTyField.dtype.bit_length(), name)

    opConstructorMap = {
        HwtOps.AND: b.CreateAnd,
        HwtOps.OR: b.CreateOr,
        HwtOps.XOR: b.CreateXor,

        HwtOps.ADD: b.CreateAdd,
        HwtOps.SUB: b.CreateSub,
        HwtOps.MUL: b.CreateMul,
        HwtOps.UREM: b.CreateURem,
        HwtOps.SREM: b.CreateSRem,
        HwtOps.UDIV: b.CreateUDiv,
        HwtOps.SDIV: b.CreateSDiv,

    }
    opConstructorMap2 = {
        HwtOps.SEXT: _llvmIntSExtConstructor,
        HwtOps.ZEXT: _llvmIntZExtConstructor,
        HwtOps.TRUNC: _truncConstructor,
        HwtOps.DOT: _dotToBitRangeGetConstructor,
    }

    opConstructorMapCmp = {
        HwtOps.NE: b.CreateICmpNE,
        HwtOps.EQ: b.CreateICmpEQ,

        HwtOps.SLE: b.CreateICmpSLE,
        HwtOps.SLT: b.CreateICmpSLT,
        HwtOps.SGT: b.CreateICmpSGT,
        HwtOps.SGE: b.CreateICmpSGE,

        HwtOps.ULE: b.CreateICmpULE,
        HwtOps.ULT: b.CreateICmpULT,
        HwtOps.UGT: b.CreateICmpUGT,
        HwtOps.UGE: b.CreateICmpUGE,
    }
    return opConstructorMap, opConstructorMap2, opConstructorMapCmp,

