import re
from typing import Dict, Tuple, Optional, Union, List

from hwt.hdl.operatorDefs import HwtOps
from hwt.hwIO import HwIO
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.llvm.llvmIr import IRBuilder, Function, Type, LoopInfo

NetlistIoConstructorDictT = Dict[HwIO, Tuple[Optional[HlsRead], Optional[HlsWrite]]]

RE_ID_WITH_NUMBER = re.compile('[^0-9]+|[0-9]+')

NaturalSortKey = Tuple[Union[str, int]]

ToLlvmIoRecordTuple = Tuple[Union[HwIO, MultiPortGroup, BankedPortGroup],
                            Type,  # elmT
                            int,  # addrWidth
                            List[HlsRead],
                            List[HlsWrite]]


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
    args: List[Tuple[int, NaturalSortKey, ToLlvmIoRecordTuple]] = [
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


def addHwtHlsFunctionMetadata(toLlvm: "ToLlvmIrTranslator"):
    """
    :attention: expects :func:`~.sortFunctionArgsByName` to be applied
    """
    F: Function = toLlvm.llvm.main
    assert F.arg_size() == len(toLlvm.ioSorted), (F.arg_size(), len(toLlvm.ioSorted))
    argAddrWidths = toLlvm.mdGetTuple([toLlvm.mdGetUInt32(addrWidth) for (_, _, addrWidth, _, _) in toLlvm.ioSorted], False)
    F.setMetadata(toLlvm.strCtx.addStringRef("hwtHls.param_addr_width"),
                               toLlvm.mdGetTuple([argAddrWidths, ], True))


def  getIoNodeConstructors(toLlvm: "ToLlvmIrTranslator") -> NetlistIoConstructorDictT:
    res: NetlistIoConstructorDictT = {}
    for hwIO, argIndex in toLlvm.ioToArgIndex.items():
        _, _, _, reads, writes = toLlvm.ioSorted[argIndex]
        res[hwIO] = (
            reads[0] if reads else None,
            writes[0] if writes else None,
            )
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
    opConstructorMap = {
        HwtOps.AND: b.CreateAnd,
        HwtOps.OR: b.CreateOr,
        HwtOps.XOR: b.CreateXor,

        HwtOps.ADD: b.CreateAdd,
        HwtOps.SUB: b.CreateSub,
        HwtOps.MUL: b.CreateMul,
        HwtOps.UDIV: b.CreateUDiv,
        HwtOps.SDIV: b.CreateSDiv,
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
    return opConstructorMap, opConstructorMapCmp

