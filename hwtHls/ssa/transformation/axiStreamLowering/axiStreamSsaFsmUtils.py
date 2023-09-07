from math import ceil, floor
from typing import Tuple, Optional, List, Union, Dict, Set, Generator

from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE, BIT
from hwt.hdl.value import HValue
from hwt.interfaces.structIntf import StructIntf
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteEndOfFrame, HlsWrite, \
    HlsStmWriteStartOfFrame
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.io.amba.axiStream.stmWrite import HlsStmWriteAxiStream
from hwtHls.ssa.analysis.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.instr import SsaInstr, ConditionBlockTuple
from hwtHls.ssa.transformation.utils.hoisting import ssaTryHoistBeforeInSameBlock
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream
from pyMathBitPrecise.bit_utils import mask


class SliceOfStreamWord():
    """
    :note: highBitNo and lowBitNo are related only to data part, masks and other word signals slices are deduced from this
    """

    def __init__(self, word: HlsRead, highBitNo: int, lowBitNo: int):
        self.word = word
        self.highBitNo = highBitNo
        self.lowBitNo = lowBitNo


class StreamChunkLastMeta():
    """
    Container which holds information about if the chunk write is las in packet or not.
    """

    def __init__(self, isLast: Union[None, bool, SsaInstr]):
        self.isLast = isLast
        self.prevWordMayBePending: bool = True


class StreamEoFMeta():

    def __init__(self, inlinedToPredecessors: bool):
        self.inlinedToPredecessors = inlinedToPredecessors


class AxiStreamSsaFsmUtils():

    def __init__(self, hls: "HlsScope", ssaBuilder: SsaExprBuilder, memUpdater: MemorySSAUpdater, intf: AxiStream, startBlock: SsaBasicBlock):
        self.ssaBuilder = ssaBuilder
        self.memUpdater = memUpdater
        self.startBlock = startBlock
        self.hls = hls
        self.intf = intf
        self.word_t = HlsStmReadAxiStream._getWordType(intf)
        self.DATA_WIDTH = intf.DATA_WIDTH
        self.seenPredecessors: Dict[SsaBasicBlock, Set[SsaBasicBlock]] = {}
        self.instrMeta: Dict[Union[HlsStmWriteAxiStream, HlsStmWriteEndOfFrame], Union[StreamChunkLastMeta, StreamEoFMeta]] = {}

    def resetBlockSeals(self, globalStartBlock: SsaBasicBlock):
        self.memUpdater.sealedBlocks.clear()
        self.memUpdater.sealedBlocks.add(globalStartBlock)

    def _sealBlocksUntilStart(self, curBlock: SsaBasicBlock):
        if curBlock is self.startBlock or curBlock in self.memUpdater.sealedBlocks:
            return

        self.memUpdater.sealBlock(curBlock)
        for pred in curBlock.predecessors:
            self._sealBlocksUntilStart(pred)

    def _prepareOffsetVariable(self) -> Tuple[RtlSignal, MemorySSAUpdater]:
        """
        Prepare a variable for an offset of data in current stream word.
        """
        offsetVar = self.hls._ctx.sig(f"{self.intf._name}_offset", Bits(log2ceil(self.intf.DATA_WIDTH - 1)))
        self.memUpdater.writeVariable(offsetVar, (), self.startBlock, offsetVar._dtype.from_py(None))
        return offsetVar

    def _preparePendingVariable(self) -> Tuple[RtlSignal, MemorySSAUpdater]:
        """
        Prepare a variable in SSA for word write pending flag, this flag is used to notify that the previous word
        was not written to output and should be output once we resolve if it is the end of stream.
        """
        pendingVar = self.hls._ctx.sig(f"{self.intf._name}_pending", BIT)
        self.memUpdater.writeVariable(pendingVar, (), self.startBlock, BIT.from_py(0))
        return pendingVar

    def _prepareWordVariable(self, name: str):
        """
        Prepare a variable which will represent stream word variable.
        """
        intf = self.intf
        data_w = intf.DATA_WIDTH
        mask_w = 0
        if intf.USE_KEEP:
            mask_w += ceil(data_w / 8)
        if intf.USE_STRB:
            mask_w += ceil(data_w / 8)
        control_w = 1  # "last" signal

        if intf.ID_WIDTH:
            raise NotImplementedError()
        if intf.DEST_WIDTH:
            raise NotImplementedError()

        # convert all reads to reads of complete words only
        wordVar = self.hls._ctx.sig(f"{intf._name:s}_{name:s}", Bits(control_w + mask_w + data_w))
        self.memUpdater.writeVariable(wordVar, (), self.startBlock, wordVar._dtype.from_py(None))
        return wordVar

    @staticmethod
    def _applyConcatAdd(ssaBuilder: SsaExprBuilder, curent: Optional[SsaValue], toAdd: RtlSignal):
        """
        :param _toAdd: high bits to concatenate to current
        """
        _toAdd = ssaBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if curent is None:
            return _toAdd
        else:
            return ssaBuilder.concat(curent, _toAdd)

    @staticmethod
    def _applyAndAdd(ssaBuilder: SsaExprBuilder, current: Optional[SsaValue], toAdd: RtlSignal):
        _toAdd = ssaBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if current is None:
            return _toAdd
        elif toAdd is None:
            return current
        else:
            return ssaBuilder._binaryOp(_toAdd, AllOps.AND, current)

    @classmethod
    def _applyWordPartsConcat(cls, ssaBuilder: SsaExprBuilder, read: HlsRead, parts: List[Union[HlsRead, SliceOfStreamWord]]):
        """
        :param parts: concatenation arguments, lowest bits first
        """
        intf = read._src
        if intf.DEST_WIDTH or intf.ID_WIDTH or intf.USER_WIDTH:
            raise NotImplementedError(read, "Not sure how these should be handled when slicing parts from the stream words")
        if intf.USE_STRB and intf.USE_KEEP:
            raise NotImplementedError(read, "Not sure which mask should be used")

        data = None
        strb = None
        keep = None
        last = None
        DW = intf.DATA_WIDTH
        MASK_WIDTH = DW // 8
        applySlice = ssaBuilder.buildSliceConst
        applyConcatAdd = cls._applyConcatAdd
        for part in parts:
            if isinstance(part, SliceOfStreamWord):
                hi, lo = part.highBitNo, part.lowBitNo
                part = part.word
                if intf.USE_STRB or intf.USE_KEEP:
                    assert hi % 8 == 0, hi
                    assert lo % 8 == 0, lo
                    mhi, mlo = hi // 8, lo // 8
                    if hi == DW:
                        nextMaskBit = None
                    else:
                        nextMaskBitOff = DW + mhi
                        nextMaskBit = applySlice(part, nextMaskBitOff + 1, nextMaskBitOff)
                elif hi == DW:
                    nextMaskBit = None
                else:
                    nextMaskBit = 1

                # derived SsaPhi and RtlSignal does not have data,strb,keep and last property
                data = applyConcatAdd(ssaBuilder, data, applySlice(part, hi, lo))
                off = DW
                if intf.USE_STRB:
                    strb = applyConcatAdd(ssaBuilder, strb, applySlice(part, off + mhi, off + mlo))
                    off += DW // 8

                if intf.USE_KEEP:
                    keep = applyConcatAdd(ssaBuilder, keep, applySlice(part, off + mhi, off + mlo))
                    off += DW // 8

            else:
                assert isinstance(part, HlsRead), part
                data = applyConcatAdd(ssaBuilder, data, applySlice(part, DW, 0))
                off = DW
                if intf.USE_STRB:
                    strb = applyConcatAdd(ssaBuilder, strb, applySlice(part, off + MASK_WIDTH, off))
                    off += MASK_WIDTH
                if intf.USE_KEEP:
                    keep = applyConcatAdd(ssaBuilder, keep, applySlice(part, off + MASK_WIDTH, off))
                    off += MASK_WIDTH

                nextMaskBit = None

            if nextMaskBit is None:
                # this part is at the end of the stream word, just use last of the word
                last = applySlice(part, off + 1, off)
            elif isinstance(nextMaskBit, int) and nextMaskBit == 1:
                # this part is never last
                last = BIT.from_py(0)
            else:
                # must check if the next mask bit is 0 to detect if this part is truly last
                last = applySlice(part, off + 1, off)
                last = cls._applyAndAdd(ssaBuilder, last, ssaBuilder._unaryOp(nextMaskBit, AllOps.NOT))

        return ssaBuilder.concat(data,
                                  * ((strb,) if intf.USE_STRB else ()),
                                  * ((keep,) if intf.USE_KEEP else ()),
                                  last), last

    def _getAdditionalWordCnt(self, offset: int, width: int):
        DATA_WIDTH = self.intf.DATA_WIDTH
        if offset == 0:
            return ceil(width / DATA_WIDTH)
        else:
            dataBitsAvailableInLastWord = DATA_WIDTH - offset
            return ceil(max(0, (width - dataBitsAvailableInLastWord)) / DATA_WIDTH)

    def _resolveMinMaxWordCount(self, possibleOffsets: List[int], chunkWidth: int):
        minWordCnt = None
        maxWordCnt = None
        # add read for every word which will be used in this read of frame fragment
        for off in possibleOffsets:
            wCnt = self._getAdditionalWordCnt(off, chunkWidth)

            if minWordCnt is None:
                minWordCnt = wCnt
            else:
                minWordCnt = min(wCnt, minWordCnt)
            if maxWordCnt is None:
                maxWordCnt = wCnt
            else:
                maxWordCnt = max(wCnt, maxWordCnt)
        return minWordCnt, maxWordCnt

    def _insertIntfWrite(self, curWordVar: StructIntf,
                         originalWrite: Union[HlsStmWriteAxiStream, HlsStmWriteEndOfFrame]):
        """
        Create a write of curWordVar variable to output interface.
        """
        ssaBuilder = self.ssaBuilder
        parts = [self.memUpdater.readVariable(v._sig, ssaBuilder.block) for v in curWordVar._interfaces]
        lastWordVal = ssaBuilder.concat(*parts)
        lastWordWr = HlsWrite(originalWrite.parent, lastWordVal, originalWrite.dst, self.word_t)
        ssaBuilder._insertInstr(lastWordWr)
        self._setWriteData(curWordVar, (), 0)
        self._setWriteMask(curWordVar, 0, 0)
        self._setWriteLast(curWordVar, 0)

    def _setWriteMask(self, curWordVar: StructIntf, offset: int, bitsToTake: int):
        """
        Set bits in mask vector to specified value and all bits after that to 0
        
        :param bitsToTake: how many bits are written in this word
        :param offset: number of bits in this word before part set in this function
        :param curWordVar: variable storing a bus word
        """
        intf = self.intf
        if intf.USE_KEEP or intf.USE_STRB:
            DATA_WIDTH = self.DATA_WIDTH
            usedBytes = floor(bitsToTake / 8)
            mLow = ceil(offset / 8)
            if mLow == 0 and usedBytes == DATA_WIDTH // 8:
                maskSlice = ()
            else:
                maskSlice = (SLICE.from_py(slice(DATA_WIDTH // 8, mLow, -1)),)
            masks = []
            if intf.USE_KEEP:
                masks.append(curWordVar.keep)
            if intf.USE_STRB:
                masks.append(curWordVar.strb)
            maskVal = Bits(DATA_WIDTH // 8 - mLow).from_py(mask(usedBytes))
            for m in masks:
                self.memUpdater.writeVariable(m._sig, maskSlice, self.ssaBuilder.block, maskVal)

    def _setWriteLast(self, curWordVar: StructIntf, val: Union[bool, SsaInstr]):
        if isinstance(val, (bool, int)):
            val = BIT.from_py(val)
        self.memUpdater.writeVariable(curWordVar.last._sig, (), self.ssaBuilder.block, val)

    def _setWriteData(self, curWordVar: StructIntf, sliceIndicies: Tuple[HValue, ...], val: Union[int, SsaValue]):
        if isinstance(val, int):
            val = curWordVar.data._sig._dtype.from_py(val)
        self.memUpdater.writeVariable(curWordVar.data._sig, sliceIndicies, self.ssaBuilder.block, val)

    # @classmethod
    # def _prevWordMayBePending(cls, cfg: StreamReadWriteGraphDetector, instr: HlsStmWriteEndOfFrame):
    #    pevWordMaybePending = False  # there may be last word which was not output0
    #    predecessorIsOnlySoF = True
    #    for pred in cfg.predecessors[instr]:
    #        if not isinstance(pred, HlsStmWriteStartOfFrame):
    #            predecessorIsOnlySoF = False
    #        allAreEoFs = True
    #        allAreNotEoFs = True
    #        for (_, predSucc) in  cfg.cfg[pred]:
    #            isEoF = isinstance(predSucc, HlsStmWriteEndOfFrame)
    #            allAreEoFs &= isEoF
    #            allAreNotEoFs &= not isEoF
    #        if (allAreEoFs or allAreNotEoFs):
    #            pevWordMaybePending = True
    #    return not predecessorIsOnlySoF and pevWordMaybePending

    def prepareLastExpressionForWrites(self, cfg: StreamReadWriteGraphDetector):
        eofs = []
        instrMeta = self.instrMeta
        for write in cfg.allStms:
            if isinstance(write, HlsStmWriteAxiStream):
                isLast = self._isLastWrite(cfg, write)
                if isLast is None:
                    isLast = self._tryToGetConditionToEnableEoF(write, cfg)
                meta = StreamChunkLastMeta(isLast)
                instrMeta[write] = meta
            elif isinstance(write, HlsStmWriteEndOfFrame):
                eofs.append(write)

        for eof in eofs:
            inlinedToPredecessors = True
            for pred in cfg.predecessors[eof]:
                predMeta = instrMeta.get(pred)
                if predMeta is None or predMeta.isLast is None:
                    inlinedToPredecessors = False
                    break

            meta = StreamEoFMeta(inlinedToPredecessors)
            instrMeta[eof] = meta

        for write in cfg.allStms:
            if isinstance(write, HlsStmWriteAxiStream):
                meta = instrMeta[write]
                prevWordMayBePending = False
                for pred in cfg.predecessors[write]:
                    predMeta = instrMeta.get(pred)
                    if predMeta is not None and predMeta.isLast is None:
                        prevWordMayBePending = True
                meta.prevWordMayBePending = prevWordMayBePending

    # @classmethod
    # def _everyPredecessorHasThisAsOnlySuccessor(cls, cfg: StreamReadWriteGraphDetector, instr: HlsStmWriteEndOfFrame):
    #    for pred in cfg.predecessors[instr]:
    #        predSuccessors = cfg.cfg[pred]
    #        if len(predSuccessors) != 1 or instr is not predSuccessors[0][1]:
    #            return False
    #
    #    return True
    #
    @classmethod
    def _isLastWrite(cls, cfg: StreamReadWriteGraphDetector,
                     instr: Union[HlsStmWriteStartOfFrame, HlsStmWriteAxiStream]) -> Optional[bool]:
        """
        :returns: True if the EOF (HlsStmWriteEndOfFrame) is only successor, False if EOF is not a successor, None if EOF is not only successor.
        """
        allAreEoFs = True
        allAreNotEoFs = True
        for (_, predSucc) in cfg.cfg[instr]:
            isEoF = isinstance(predSucc, HlsStmWriteEndOfFrame)
            allAreEoFs &= isEoF
            allAreNotEoFs &= not isEoF
        if not allAreEoFs and not allAreNotEoFs:
            return None
        elif allAreEoFs:
            return True
        else:
            assert allAreNotEoFs
            return False

    @classmethod
    def _resolveBranchGroupCondition(cls,
                                     ssaBuilder: SsaExprBuilder,
                                     targets: Generator[ConditionBlockTuple, None, None],
                                     trueBlocks: Set[SsaBasicBlock]) -> Tuple[Optional[SsaInstr], bool]:
        """
        :returns: condtion expression is some trueBlock was seen else None, flag which is True if some trueBlock was seen
        """
        try:
            c, suc, _ = next(targets)
        except StopIteration:
            return None, False

        rightSideOfExpr, rightSideOfExprUseful = cls._resolveBranchGroupCondition(ssaBuilder, targets, trueBlocks)
        condIsUseful = rightSideOfExprUseful or suc in trueBlocks
        if rightSideOfExpr is None:
            if suc in trueBlocks or c is None:
                # c = c
                pass
            elif rightSideOfExprUseful:
                c = ssaBuilder._unaryOp(c, AllOps.NOT)

        else:
            assert c is not None, "If right side was useful this means this can not be last default branch which has condtion None"
            assert rightSideOfExprUseful
            if suc in trueBlocks and rightSideOfExprUseful:
                c = ssaBuilder._binaryOp(c, AllOps.OR, rightSideOfExpr)
            else:
                c = ssaBuilder._binaryOp(ssaBuilder._unaryOp(c, AllOps.NOT), AllOps.AND, rightSideOfExpr)
        return c, condIsUseful

    def _tryToGetConditionToEnableEoF(self, curWrite: Union[HlsStmWriteStartOfFrame, HlsStmWriteAxiStream],
                                      cfg: StreamReadWriteGraphDetector) -> Optional[SsaInstr]:
        curBlock = curWrite.block
        successorsWithEoF = set()
        for _, suc, _ in curBlock.successors.targets:
            # allow for linear sequences of blocks
            _suc = suc
            eofFound = False
            while True:
                for instr in _suc.body:
                    if instr in cfg.allStms:
                        if isinstance(instr, HlsStmWriteEndOfFrame):
                            eofFound = True
                        break
                if eofFound:
                    break
                else:
                    if len(_suc.successors.targets) == 1:
                        # follow linear sequence of blocks
                        _suc = _suc.successors.targets[0][1]
                    else:
                        # there is some branching, we do not follow it because the hoisting of code
                        # on such branches is not implemented on this level yet
                        break
            if eofFound:
                successorsWithEoF.add(suc)

        if not successorsWithEoF:
            return None

        importantConditions = set()
        firstEoFTargetSeen = False
        for cond, suc, _ in reversed(curBlock.successors.targets):
            if firstEoFTargetSeen:
                importantConditions.add(cond)
            elif suc in successorsWithEoF:
                firstEoFTargetSeen = True
                if cond is not None:
                    importantConditions.add(cond)

        hoistSuccess, writePosition = ssaTryHoistBeforeInSameBlock(curWrite, importantConditions)
        if hoistSuccess:
            # build the condition from parts
            ssaBuilder = self.ssaBuilder
            ssaBuilder.setInsertPoint(curWrite.block, writePosition)
            isLastCond, _ = self._resolveBranchGroupCondition(ssaBuilder, iter(curBlock.successors.targets), successorsWithEoF)
            assert isLastCond is not None
            return isLastCond
        else:
            return None
