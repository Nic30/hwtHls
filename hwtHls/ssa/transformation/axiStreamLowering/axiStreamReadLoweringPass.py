from itertools import islice
from math import ceil
from typing import Optional, List, Sequence, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.ast.statementsRead import HlsRead, HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.ssa.analysis.axisDetectIoAccessGraph import SsaAnalysisAxisDetectIoAccessGraph
from hwtHls.ssa.analysis.axisDetectReadStatements import SsaAnalysisAxisDetectReadStatements
from hwtHls.ssa.analysis.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamSsaFsmUtils import AxiStreamSsaFsmUtils, \
    SliceOfStreamWord
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream
from ipCorePackager.constants import DIRECTION


class SsaPassAxiStreamReadLowering(SsaPass):
    """
    Lower the read of abstract data type from AMBA AXI-stream interfaces to a read of native interface words.
    
    1. Build CFG of parsing and in stream chunk positions
        * DFS search the SSA for reads and compute the offset
    2. Rewrite reads of ADTs to read of words
    
    :note: Problematic features
        * SSA CFG does not correspond to read CFG
            * blocks may not contain reads, there there can be multiple paths between same reads
            * cycles in SSA does not necessary mean a cycle in read CFG
    
    
    If we could use a global state of the parser it would be simple:
        * we would just generate FSM where for each word we would distribute the data to field variables
        * FSM transition table can be directly generated from readGraph
        
    However on SSA level the parse graph is not linear and many branches of code do contain reads, which may be optional
    which complicates the resolution of which read was actually last word, which is required by next read.
    In order to solve this problem we must generate variables which will contain the value of this last word
    and a variable which will contain the offset in this last word.
    
    The rewrite does:
        * convert all reads to reads of native stream words
        * move as many reads of stream words as possible to parent blocks to simplify their condition
        * generate last word and offset variable
        * use newly generated variables to select the values of the read data
            * in every block the value of offset is resolved
            * if the block requires the value the phi without operands is constructed
            * phi operands are filled in
        * for every read/write which may fail (due to premature end of frame) generate erorr handler jumps
    
    :attention: If there are reads on multiple input streams this may result in changed order in which bus words are accepted
        which may result in deadlock.
    """

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        rStms: SsaAnalysisAxisDetectReadStatements = toSsa.getAnalysis(SsaAnalysisAxisDetectReadStatements)

        for intf in rStms.intfs:
            intf: AxiStream
            intfCfg: SsaAnalysisAxisDetectIoAccessGraph = toSsa.getAnalysis(SsaAnalysisAxisDetectIoAccessGraph(toSsa, intf, DIRECTION.IN))
            cfg = intfCfg.cfg
            ssaUtils = AxiStreamSsaFsmUtils(hls, toSsa.ssaBuilder, toSsa.m_ssa_u, intf, toSsa.start)
            offsetVar = ssaUtils._prepareOffsetVariable()
            predWordPendingVar = None
            predWordVar = ssaUtils._prepareWordVariable("predWord")
            ssaUtils.resetBlockSeals(toSsa.start)
            self.rewriteAdtAccessToWordAccess(ssaUtils, toSsa.start, cfg, offsetVar, predWordPendingVar, predWordVar)

            # assert that all original reads were removed from SSA
            self._checkAllInstructionsRemoved(cfg.allStms)

    @staticmethod
    def _checkAllInstructionsRemoved(instructions: Sequence[SsaValue]):
        # assert that all original reads were removed from SSA
        for instr in instructions:
            if instr is None:
                continue
            assert instr.block is None, ("All original instructions must be replaced", instr)

    @classmethod
    def _handleOptionalReadsDependingOnCurrentOffset(cls, ssaUtils: AxiStreamSsaFsmUtils,
                                                     possibleOffsets: List[int], minWordCnt: int, maxWordCnt: int, chunkWidth: int,
                                                     predWordVar: RtlSignal, curOffsetVar, read: HlsStmReadAxiStream):
        _curOffsetVar = ssaUtils.memUpdater.readVariable(curOffsetVar, read.block)
        assert not isinstance(_curOffsetVar, HValue), (
            "The value should not be constant, because "
            "if it is a constant it this should not be generated in the first place", _curOffsetVar)
        offsetCaseCond: List[SsaInstr] = []
        DATA_WIDTH = ssaUtils.DATA_WIDTH
        ssaBuilder = ssaUtils.ssaBuilder
        for off in possibleOffsets:
            wCnt = ssaUtils._getAdditionalWordCnt(off, chunkWidth)
            if wCnt > minWordCnt:
                assert wCnt == minWordCnt + 1, (wCnt, minWordCnt, maxWordCnt)
                offVal = curOffsetVar._dtype.from_py(off % DATA_WIDTH)
                offEn = ssaBuilder._binaryOp(_curOffsetVar, AllOps.EQ, offVal)
                offsetCaseCond.append(offEn)

        extraReadEn = ssaBuilder._binaryOpVariadic(AllOps.OR, offsetCaseCond)
        if "(readEn)" not in extraReadEn._name:
            extraReadEn._name += "(readEn)"
        # original read should be moved to sequel
        # because now we are just preparing the data for it
        extraReadBranches, sequelBlock = ssaBuilder.insertBlocks([
            (extraReadEn, f"{predWordVar.name}ExtraRead"),
            (None, f"{predWordVar.name}noExtraRead")
        ])
        extraRead = HlsRead(read._parent, read._src, ssaUtils.word_t, True)
        ssaBuilder.setInsertPoint(extraReadBranches[0], 0)
        ssaBuilder._insertInstr(extraRead)
        memUpdater = ssaUtils.memUpdater

        memUpdater.writeVariable(predWordVar, (), extraReadBranches[0], extraRead)
        # :note: it is not required to write offset because it does not change
        for br in extraReadBranches:
            memUpdater.sealBlock(br)

        # append read of new word
        memUpdater.sealBlock(sequelBlock)
        ssaBuilder.setInsertPoint(sequelBlock, 0)  # just at the original read instruction

    @classmethod
    def _createBranchForEachOffsetVariant(cls, memUpdater: MemorySSAUpdater, ssaBuilder: SsaExprBuilder,
                                          possibleOffsets: List[int], DATA_WIDTH: int,
                                          curOffsetVar, curBlock: SsaBasicBlock):
        if len(possibleOffsets) > 1:
            # create branch for each offset variant
            offsetCaseCond = []
            _curOffsetVar = memUpdater.readVariable(curOffsetVar, curBlock)
            for last, off in iter_with_last(possibleOffsets):
                if last:
                    # only option left, check not required
                    offEn = None
                else:
                    offEn = ssaBuilder._binaryOp(_curOffsetVar, AllOps.EQ,
                                                  curOffsetVar._dtype.from_py(off % DATA_WIDTH))
                offsetCaseCond.append((offEn, f"{curOffsetVar.name}{off}"))

            offsetBranches, sequelBlock = ssaBuilder.insertBlocks(offsetCaseCond)
            for br in offsetBranches:
                memUpdater.sealBlock(br)
            memUpdater.sealBlock(sequelBlock)
            ssaBuilder.setInsertPoint(sequelBlock, None)

        else:
            offsetBranches, sequelBlock = [curBlock], curBlock

        return offsetBranches, sequelBlock

    @classmethod
    def _consumeReadWordsAndCreateResultData(cls, ssaUtils: AxiStreamSsaFsmUtils, ssaBuilder: SsaExprBuilder,
                                             possibleOffsets: List[int], minWordCnt: int, maxWordCnt: int, chunkWidth: int,
                                             predWordVar: RtlSignal, curOffsetVar: RtlSignal, read: HlsStmReadAxiStream):
        prevWordVars: List[HlsRead] = []
        memUpdater = ssaUtils.memUpdater
        # load previous last word
        if possibleOffsets != [0, ] or minWordCnt != maxWordCnt:
            prevWordVars.append(memUpdater.readVariable(predWordVar, read.block))

        # # if other predecessor branches provide some leftover word part and there is a brach which does not provide any,
        # # create read on this branch as it is sure that the read will be performed bease this read needs some data

        # offset may cause that may require to read

        # fill reads to this block to obtains required amount of bits
        for last, _ in iter_with_last(range(minWordCnt)):
            partRead = HlsRead(read._parent, read._src, ssaUtils.word_t, True)
            prevWordVars.append(partRead)
            ssaBuilder._insertInstr(partRead)
            if last:
                memUpdater.writeVariable(predWordVar, (), read.block, partRead)

        DATA_WIDTH = ssaUtils.DATA_WIDTH
        offsetBranches, sequelBlock = cls._createBranchForEachOffsetVariant(
            memUpdater, ssaBuilder, possibleOffsets, DATA_WIDTH, curOffsetVar, read.block)

        curBlockPosition = ssaBuilder.position
        resVar = ssaUtils.hls._ctx.sig(read._name, read._dtype)
        # [todo] aggregate rewrite for all reads in this same block to reduce number of branches because of offset
        for off, br in zip(possibleOffsets, offsetBranches):
            off: int
            br: SsaBasicBlock
            # memUpdater.sealBlock(br)
            if br is read.block:
                ssaBuilder.setInsertPoint(read.block, curBlockPosition)
            else:
                ssaBuilder.setInsertPoint(br, 0)

            end = off + chunkWidth
            inWordOffset = off % DATA_WIDTH
            _w = chunkWidth
            wordCnt = ceil(max(0, end - 1) / DATA_WIDTH)

            if inWordOffset == 0 and (minWordCnt != maxWordCnt) and ssaUtils._getAdditionalWordCnt(off, chunkWidth) == minWordCnt:
                # now not reading last word of predecessor but other offsets variant are using it
                chunkWords = prevWordVars[1:]
            else:
                chunkWords = prevWordVars[:]

            assert len(chunkWords) == wordCnt, (read, wordCnt, chunkWords)

            parts = []
            for wordI in range(wordCnt):
                bitsToTake = min(_w, DATA_WIDTH - inWordOffset)
                partRead = chunkWords[wordI]

                if inWordOffset != 0:
                    # take from previous word
                    # [todo] potentially can be None if the start of stream is not aligned
                    partRead = SliceOfStreamWord(partRead, off + bitsToTake, off)
                    inWordOffset = 0
                else:
                    # read a new word
                    if bitsToTake != DATA_WIDTH:
                        assert bitsToTake > 0, bitsToTake
                        partRead = SliceOfStreamWord(partRead, inWordOffset + bitsToTake, inWordOffset)

                _w -= bitsToTake
                parts.append(partRead)

            readRes, isLast = ssaUtils._applyWordPartsConcat(ssaBuilder, read, parts)
            assert readRes._dtype.bit_length() == resVar._dtype.bit_length(), (readRes, readRes._dtype, resVar._dtype)
            if read._name not in readRes._name:
                readRes._name = f"{readRes._name:s}({read._name:s})"
            memUpdater.writeVariable(resVar, (), br, readRes)
            newOffset = end % DATA_WIDTH
            if newOffset != 0:
                br = cls._resetOffsetIfLast(ssaUtils, readRes._name, isLast, curOffsetVar, newOffset)
            else:
                memUpdater.writeVariable(curOffsetVar, (), br, curOffsetVar._dtype.from_py(0))

            memUpdater.writeVariable(predWordVar, (), br, chunkWords[-1])
            if br is read.block:
                curBlockPosition = ssaBuilder.position

        ssaBuilder.setInsertPoint(sequelBlock, curBlockPosition if sequelBlock is read.block else 0)
        # resolve a value which will represent the original read
        readRes = memUpdater.readVariable(resVar, sequelBlock)
        if read._name not in readRes._name:
            readRes._name = f"{readRes._name:s}({read._name:s})"
        return readRes, sequelBlock

    @classmethod
    def _resetOffsetIfLast(cls, ssaUtils: AxiStreamSsaFsmUtils,
                           name: str,
                           isLast: SsaValue,
                           curOffsetVar: RtlSignal,
                           elseValue: int):
        ssaBuilder = ssaUtils.ssaBuilder
        extraWriteBranches, sequelBlock = ssaBuilder.insertBlocks([
            (isLast, f"{name:s}Last"),
            (None, f"{name:s}NoLast")
        ])
        memUpdater = ssaUtils.memUpdater
        for br, v in zip(extraWriteBranches, (0, elseValue)):
            ssaBuilder.setInsertPoint(br, 0)
            memUpdater.writeVariable(curOffsetVar, (), br, curOffsetVar._dtype.from_py(v))

        # :note: it is not required to write offset because it does not change
        for br in extraWriteBranches:
            memUpdater.sealBlock(br)

        # append read of new word
        memUpdater.sealBlock(sequelBlock)
        ssaBuilder.setInsertPoint(sequelBlock, 0)  # just at the original place where we cut the orignal block and inserted the optional write before

        return sequelBlock

    def _rewriteAdtAccessToWordAccessInstruction(self,
                                              ssaUtils: AxiStreamSsaFsmUtils,
                                              cfg: StreamReadWriteGraphDetector,
                                              read: Optional[HlsStmReadAxiStream],
                                              curOffsetVar: RtlSignal,
                                              predWordPendingVar: None,
                                              predWordVar: RtlSignal) -> Tuple[SsaBasicBlock, Optional[int]]:
        memUpdater = ssaUtils.memUpdater
        readIsMarker = read is None or isinstance(read, (HlsStmReadStartOfFrame, HlsStmReadEndOfFrame))
        possibleOffsets = cfg.inWordOffset[read]
        if not possibleOffsets:
            raise AssertionError("This is an accessible read, it should be already removed", read)

        sequelBlock = None if read is None else read.block
        if readIsMarker:
            w = 0
            isStart = isinstance(read, HlsStmReadStartOfFrame)
            if isStart:
                if len(possibleOffsets) > 1:
                    # read words to satisfy initial offset
                    # for last, _ in iter_with_last(range(ceil(max(possibleOffsets) / DATA_WIDTH))):
                    #    endOfStream = last and not successors
                    #    r = HlsStmReadAxiStream(read._parent, read._src, Bits(DATA_WIDTH), endOfStream)
                    #    prevWordVars.append(r)
                    raise NotImplementedError("Use first word mask to resolve the offsetVar", possibleOffsets)
                else:
                    offset = curOffsetVar._dtype.from_py(possibleOffsets[0])
                    memUpdater.writeVariable(curOffsetVar, (), ssaUtils.startBlock, offset)
            if read is not None:
                sequelBlockPos = read.block.body.index(read)
                read.block.body.remove(read)
                read.block = None
            else:
                sequelBlockPos = None
        else:
            # [todo] do not rewrite if this is already a read of an aligned full word
            w = read._dtypeOrig.bit_length()

            # if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

            # shared words for offset variants
            ssaBuilder = ssaUtils.ssaBuilder
            ssaBuilder.setInsertPoint(read.block, read.block.body.index(read))

            minWordCnt, maxWordCnt = ssaUtils._resolveMinMaxWordCount(possibleOffsets, w,)
            mayResultInDiffentNoOfWords = minWordCnt != maxWordCnt
            if mayResultInDiffentNoOfWords:
                self._handleOptionalReadsDependingOnCurrentOffset(
                    ssaUtils, possibleOffsets, minWordCnt, maxWordCnt,
                    w, predWordVar, curOffsetVar, read)

            # collect/construct all reads common for every successor branch

            readRes, sequelBlock = self._consumeReadWordsAndCreateResultData(
                ssaUtils, ssaBuilder, possibleOffsets, minWordCnt, maxWordCnt,
                w, predWordVar, curOffsetVar, read)
            # replace original read of ADT with a result composed of word reads
            read.replaceBy(readRes)
            sequelBlockPos = read.block.body.index(read)
            read.block.body.remove(read)
            read.block = None

            defs = memUpdater.currentDef[read._sig]
            for bb, v in defs.items():
                if v is read:
                    defs[bb] = readRes

        return sequelBlock, sequelBlockPos

    def rewriteAdtAccessToWordAccess(self,
                                    ssaUtils: AxiStreamSsaFsmUtils,
                                    curBlock: SsaBasicBlock,
                                    cfg: StreamReadWriteGraphDetector,
                                    curOffsetVar: RtlSignal,
                                    predWordPendingVar: Optional[RtlSignal],
                                    predWordVar: RtlSignal):
        """
        :param cfg: an object which keeps the info about CFG and offsets of individual reads
        """
        if curBlock is ssaUtils.startBlock:
            _curBlock, _ = self._rewriteAdtAccessToWordAccessInstruction(
                ssaUtils, cfg, None, curOffsetVar, predWordPendingVar, predWordVar)
            assert _curBlock is None

        blockBodyIt = iter(curBlock.body)
        instrIndex = -1
        allStms = cfg.allStms
        while True:
            instr = next(blockBodyIt, None)
            if instr is None:
                break  # end of instruction list
            instrIndex += 1

            if instr in allStms:
                assert instr.block is not None, ("instruction was removed", instr)
                _curBlock, _instrIndex = self._rewriteAdtAccessToWordAccessInstruction(
                    ssaUtils, cfg, instr, curOffsetVar, predWordPendingVar, predWordVar)

                # handle update of iterator
                if _instrIndex is None:
                    _instrIndex = instrIndex + 1
                if _curBlock is not curBlock or _instrIndex != instrIndex + 1:
                    if _instrIndex == 0:
                        curBlock = _curBlock
                        blockBodyIt = iter(curBlock.body)
                        instrIndex = -1
                    else:
                        if curBlock is _curBlock and _instrIndex > instrIndex + 1:
                            posDiff = _instrIndex - instrIndex - 2
                            for _ in range(posDiff):
                                next(blockBodyIt)
                            instrIndex += posDiff
                        else:
                            blockBodyIt = iter(islice(curBlock.body, _instrIndex, None))
                            instrIndex = _instrIndex - 1

        # :note: curBlock may be a different than the original from arguments, because the block may be split etc.
        for sucBb in curBlock.successors.iterBlocks():
            seenPredecessors = ssaUtils.seenPredecessors.get(sucBb, None)
            if seenPredecessors is None:
                seenPredecessors = ssaUtils.seenPredecessors[sucBb] = set()
                thisBlockWasSeen = False
            else:
                thisBlockWasSeen = True
            thisEdgeWasSeen = curBlock in seenPredecessors
            seenPredecessors.add(curBlock)

            if not thisEdgeWasSeen and len(seenPredecessors) == len(sucBb.predecessors):
                if sucBb not in ssaUtils.memUpdater.sealedBlocks:
                    # it may be already sealed if it is was generated
                    ssaUtils.memUpdater.sealBlock(sucBb)

            if not thisBlockWasSeen:
                self.rewriteAdtAccessToWordAccess(
                    ssaUtils, sucBb, cfg, curOffsetVar, predWordPendingVar, predWordVar)

