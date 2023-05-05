from collections import defaultdict
from math import ceil
from typing import Dict, Optional, List, Union, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.ast.statements import HlsStm
from hwtHls.frontend.ast.statementsRead import HlsRead, HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteStartOfFrame, \
    HlsStmWriteEndOfFrame
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.transformation.axiStreamLowering.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class SliceOfStreamWord():
    """
    :note: highBitNo and lowBitNo are related only to data part, masks and other word signals slices are deduced from this
    """

    def __init__(self, word: HlsRead, highBitNo: int, lowBitNo: int):
        self.word = word
        self.highBitNo = highBitNo
        self.lowBitNo = lowBitNo
        

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
    """

    def _sealBlocksUntilStart(self, memUpdater: MemorySSAUpdater, startBlock: SsaBasicBlock, curBlock: SsaBasicBlock):
        if startBlock is curBlock or curBlock in memUpdater.sealedBlocks:
            return

        memUpdater.sealBlock(curBlock)
        for pred in curBlock.predecessors:
            self._sealBlocksUntilStart(memUpdater, startBlock, pred)
        
    def _detectIoAccessStatements(self, startBlock: SsaBasicBlock) -> Tuple[UniqList[AxiStream], Dict[AxiStream, UniqList[HlsStm]], UniqList[HlsStm]]:
        ios: UniqList[HlsStm] = UniqList()
        for block in collect_all_blocks(startBlock, set()):
            for instr in block.body:
                if isinstance(instr, (HlsStmReadAxiStream, HlsStmReadStartOfFrame, HlsStmReadEndOfFrame)):
                    ios.append(instr)

        intfs: UniqList[AxiStream] = UniqList()
        ioForIntf: Dict[AxiStream, UniqList[HlsStm]] = defaultdict(UniqList)
        for io in ios:
            intfs.append(io._src)
            ioForIntf[io._src].append(io)
        
        return intfs, ioForIntf, ios

    def _parseCfg(self, toSsa: HlsAstToSsa, intf: AxiStream, ioForIntf: Dict[AxiStream, UniqList[HlsStm]]):
        cfg = StreamReadWriteGraphDetector(intf.DATA_WIDTH, ioForIntf[intf])
        cfg.detectIoAccessGraphs(None, 0, toSsa.start, set())
        cfg.resolvePossibleOffset()
        predecessorsSeen = {r: 0 for r in cfg.allStms}
        startBlock = cfg.findStartBlock()
        return cfg, predecessorsSeen, startBlock

    def _prepareOffsetVariable(self, hls: "HlsScope", startBlock: SsaBasicBlock, intf: AxiStream,
                               memUpdater: MemorySSAUpdater) -> Tuple[RtlSignal, MemorySSAUpdater]:
        offsetVar = hls._ctx.sig(f"{intf._name}_offset", Bits(log2ceil(intf.DATA_WIDTH - 1)))
        memUpdater.writeVariable(offsetVar, (), startBlock, offsetVar._dtype.from_py(None))
        return offsetVar
        
    def _prepareWordVariable(self, hls: "HlsScope", startBlock: SsaBasicBlock,
                             intf: AxiStream, memUpdater: MemorySSAUpdater, name: str):
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
        wordVar = hls._ctx.sig(f"{intf._name:s}_{name:s}", Bits(control_w + mask_w + data_w))
        memUpdater.writeVariable(wordVar, (), startBlock, wordVar._dtype.from_py(None))
        return wordVar

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        intfs, ioForIntf, _ = self._detectIoAccessStatements(toSsa.start)
        memUpdater = toSsa.m_ssa_u

        for intf in intfs:
            intf: AxiStream
            cfg, predecessorsSeen, startBlock = self._parseCfg(toSsa, intf, ioForIntf)
            offsetVar = self._prepareOffsetVariable(hls, startBlock, intf, memUpdater)
            predWordVar = self._prepareWordVariable(hls, startBlock, intf, memUpdater, "pred_word")
            word_t = HlsStmReadAxiStream._getWordType(intf)
            self.rewriteAdtReadToReadOfWords(hls, memUpdater, startBlock, None, intf.DATA_WIDTH, cfg,
                                             predecessorsSeen, offsetVar, predWordVar, word_t)

    def _applyConcateAdd(self, exprBuilder: SsaExprBuilder, curent: Optional[SsaValue], toAdd: RtlSignal):
        """
        :param _toAdd: high bits to concatenate to current
        """
        _toAdd = exprBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if curent is None:
            return _toAdd
        else:
            return exprBuilder.concat(curent, _toAdd)

    def _applyOrAdd(self, exprBuilder: SsaExprBuilder, curent: Optional[SsaValue], toAdd: RtlSignal):
        _toAdd = exprBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if curent is None:
            return _toAdd
        else:
            return exprBuilder._binaryOp(_toAdd, AllOps.OR, curent)

    def _applyConcat(self, exprBuilder: SsaExprBuilder, read: HlsRead, parts: List[Union[HlsRead, SliceOfStreamWord]]):
        """
        :param parts: concatenation arguments, lowest bits first
        """
        intf = read._src
        if intf.DEST_WIDTH or intf.ID_WIDTH or intf.USER_WIDTH:
            raise NotImplementedError(read)
        # mask_w = ceil(data_w / 8)
        data = None
        strb = None
        keep = None
        last = None
        DW = intf.DATA_WIDTH
        applySlice = exprBuilder.buildSliceConst
        applyConcateAdd = self._applyConcateAdd
        for part in parts:
            if isinstance(part, SliceOfStreamWord):
                hi, lo = part.highBitNo, part.lowBitNo
                if intf.USE_STRB or intf.USE_KEEP:
                    assert hi % 8 == 0, hi
                    assert lo % 8 == 0, lo
                    mhi, mlo = hi // 8, lo // 8
                
                part = part.word
                # derived SsaPhi and RtlSignal does not have data,strb,keep and last property
                data = applyConcateAdd(exprBuilder, data, applySlice(part, hi, lo))
                off = DW
                if intf.USE_STRB:
                    strb = applyConcateAdd(exprBuilder, data, applySlice(part, off + mhi, off + mlo))
                    off += DW // 8

                if intf.USE_KEEP:
                    keep = applyConcateAdd(exprBuilder, data, applySlice(part, off + mhi, off + mlo))
                    off += DW // 8

            else:
                assert isinstance(part, HlsRead), part
                data = applyConcateAdd(exprBuilder, data, applySlice(part, DW, 0))
                off = DW
                if intf.USE_STRB:
                    strb = applyConcateAdd(exprBuilder, strb, applySlice(part, off + DW // 8, off))
                    off += DW // 8
                if intf.USE_KEEP:
                    keep = applyConcateAdd(exprBuilder, keep, applySlice(part, off + DW // 8, off))
                    off += DW // 8

            last = self._applyOrAdd(exprBuilder, last, applySlice(part, off + 1, off))

        return exprBuilder.concat(data,
                                  * ((strb,) if intf.USE_STRB else ()),
                                  * ((keep,) if intf.USE_KEEP else ()),
                                  last)
    
    def _getAdditionalWordCnt(self, offset: int, width: int, DATA_WIDTH: int):
        if offset == 0:
            return ceil(width / DATA_WIDTH)
        else:
            dataBitsAvailableInLastWord = DATA_WIDTH - offset
            return ceil(max(0, (width - dataBitsAvailableInLastWord)) / DATA_WIDTH)

    
    def rewriteAdtReadToReadOfWords(self,
                                    hls: "HlsScope",
                                    memUpdater: MemorySSAUpdater,
                                    startBlock: SsaBasicBlock,
                                    read: Optional[HlsStmReadAxiStream],
                                    DATA_WIDTH: int,
                                    cfg: StreamReadWriteGraphDetector,
                                    predecessorsSeen: Dict[HlsStmReadAxiStream, int],
                                    currentOffsetVar: RtlSignal,
                                    predWordVar: RtlSignal,
                                    word_t: HdlType):
        """
        :param read: a current read instruction object which should be rewritten
        :param DATA_WIDTH: number of bits in a single bus word
        :param cfg: an object which keeps the info about CFG and offsets of individual reads
        :param predecessorsSeen: a dictionary to run the rewrite only after all predecessors were rewritten

        If we could use a global state of the parser it would be simple:
        * we would just generate FSM where for each word we would distribute the data to field variables
        * FSM transition table can be directly generated from readGraph
        
        However on SSA level the parse graph is not linear and many branches of code do contain reads which may be optional
        which complicates the resolution of which read was actually last word which is required by next read.
        In order to solve this problem we must generate variables which will contain the value of this last word
        and a variable which will contain the offset in this last word.
        
        
        The rewrite does:
        * convert all reads to reads of stream words
        * move as many reads of stream words as possible to parent blocks to simplify their condition
        * generate last word and offset variable
        * use newly generated variables to select the values of the read data
          * in every block the value of offset is resolved
          * if the block requires the value the phi without operands is constructed
          * phi operands are filled in
        * for every read/write which may fail (due to premature end of frame) generate erorr handler jumps
        
        :note: If there are reads on multiple input streams this may result in changed order in which bus words are accepted
            which may result in deadlock.
            
        """
        readIsMarker = read is None or isinstance(read, (HlsStmReadStartOfFrame, HlsStmReadEndOfFrame,
                                                         HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame))
        if read is not None:
            assert read.block is not None, ("read instruction was removed", read)
            predecessorsSeen[read] += 1
            if len(cfg.predecessors[read]) != predecessorsSeen[read]:
                # not all predecessors have been seen and we run this function only after all predecessors were seen
                return
            else:
                # [todo] if the read has multiple predecessors and the last word from them is required and may differ we need o create
                # a phi to select it and then use it as a last word from previous read
                self._sealBlocksUntilStart(memUpdater, startBlock, read.block)

        possibleOffsets = cfg.inWordOffset[read]
        if not possibleOffsets:
            raise AssertionError("This is an accessible read, it should be already removed", read)
        
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
                    offset = currentOffsetVar._dtype.from_py(possibleOffsets[0])
                    memUpdater.writeVariable(currentOffsetVar, (), startBlock, offset)
        else:
            # [todo] do not rewrite if this is already a read of an aligned full word
            w = read._dtypeOrig.bit_length()
    
            # if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified 

            # shared words for offset variants
            exprBuilder = SsaExprBuilder(read.block, read.block.body.index(read))
 
            minWordCnt = None
            maxWordCnt = None
            # add read for every word which will be used in this read of frame fragment
            for off in possibleOffsets:
                wCnt = self._getAdditionalWordCnt(off, w, DATA_WIDTH)

                if minWordCnt is None:
                    minWordCnt = wCnt
                else:
                    minWordCnt = min(wCnt, minWordCnt)
                if maxWordCnt is None:
                    maxWordCnt = wCnt
                else:
                    maxWordCnt = max(wCnt, maxWordCnt)
 
            
            mayResultInDiffentNoOfWords = minWordCnt != maxWordCnt
            if mayResultInDiffentNoOfWords:
                _currentOffsetVar = memUpdater.readVariable(currentOffsetVar, read.block)
                offsetCaseCond = []
                for off in possibleOffsets:
                    wCnt = self._getAdditionalWordCnt(off, w, DATA_WIDTH)
                    if wCnt > minWordCnt:
                        assert wCnt == minWordCnt + 1, (wCnt, minWordCnt, maxWordCnt)
                        offEn = exprBuilder._binaryOp(_currentOffsetVar, AllOps.EQ,
                                              currentOffsetVar._dtype.from_py(off % DATA_WIDTH))
                        offsetCaseCond.append(offEn)

                extraReadEn = exprBuilder._binaryOpVariadic(AllOps.OR, offsetCaseCond)
                # original read should be moved to sequel
                # because now we are just preparing the data for it
                extraReadBranches, sequelBlock = exprBuilder.insertBlocks([
                    extraReadEn,
                    None
                ])
                extraReadExprBuilder = SsaExprBuilder(extraReadBranches[0], position=0)
                extraRead = HlsRead(read._parent, read._src, word_t, True)
                extraReadExprBuilder._insertInstr(extraRead)
                memUpdater.writeVariable(predWordVar, (), extraReadBranches[0], extraRead)
                # :note: it is not required to write offset because it does not change
                for br in extraReadBranches:
                    memUpdater.sealBlock(br)
                
                # append read of new word
                memUpdater.sealBlock(sequelBlock)
                exprBuilder.setInsertPoint(sequelBlock, 0) # just at the original read instruction

            # collect/construct all reads common for every successor branch

            prevWordVars: List[HlsRead] = [] 
            # load previous last word
            if possibleOffsets != [0, ] or minWordCnt != maxWordCnt:
                prevWordVars.append(memUpdater.readVariable(predWordVar, read.block))

 
            ## if other predecessor branches provide some leftover word part and there is a brach which does not provide any,
            ## create read on this branch as it is sure that the read will be performed bease this read needs some data 
   
            # offset may cause that may require to read 
                
            # fill reads to this block to obrain required amount of bits
            for last, _ in iter_with_last(range(minWordCnt)):
                partRead = HlsRead(read._parent, read._src, word_t, True)
                prevWordVars.append(partRead)
                exprBuilder._insertInstr(partRead)
                if last:
                    memUpdater.writeVariable(predWordVar, (), read.block, partRead)
            
            if len(possibleOffsets) > 1:
                # create branch for each offset variant
                offsetCaseCond = []
                _currentOffsetVar = memUpdater.readVariable(currentOffsetVar, read.block)
                for last, off in iter_with_last(possibleOffsets):
                    if last: 
                        # only option left, check not required
                        offEn = None
                    else:
                        offEn = exprBuilder._binaryOp(_currentOffsetVar, AllOps.EQ,
                                                      currentOffsetVar._dtype.from_py(off % DATA_WIDTH))
                    offsetCaseCond.append(offEn)

                offsetBranches, sequelBlock = exprBuilder.insertBlocks(offsetCaseCond)
                for br in offsetBranches:
                    memUpdater.sealBlock(br)
                memUpdater.sealBlock(sequelBlock)
                exprBuilder.setInsertPoint(sequelBlock, None)
                
            else:
                offsetBranches, sequelBlock = [read.block], read.block
            
            resVar = hls._ctx.sig(read._name, read._dtype)
            # [todo] aggregate rewrite for all reads in this same block to reduce number of branches because of offset
            for off, br in zip(possibleOffsets, offsetBranches):
                off: int
                br: SsaBasicBlock
                # memUpdater.sealBlock(br)
                if br is read.block:
                    _exprBuilder = exprBuilder
                else:
                    _exprBuilder = SsaExprBuilder(br)
                    
                end = off + w
                inWordOffset = off % DATA_WIDTH
                _w = w
                wordCnt = ceil(max(0, end - 1) / DATA_WIDTH)

                if inWordOffset == 0 and (minWordCnt != maxWordCnt) and self._getAdditionalWordCnt(off, w, DATA_WIDTH) == minWordCnt:
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

                readRes = self._applyConcat(_exprBuilder, read, parts)
                assert readRes._dtype.bit_length() == resVar._dtype.bit_length(), (readRes, readRes._dtype, resVar._dtype)

                memUpdater.writeVariable(resVar, (), br, readRes)
                memUpdater.writeVariable(currentOffsetVar, (), br, currentOffsetVar._dtype.from_py(end % DATA_WIDTH))
                memUpdater.writeVariable(predWordVar, (), br, chunkWords[-1])

            # resolve a value which will represent the original read
            readRes = memUpdater.readVariable(resVar, sequelBlock)
    
            # replace original read of ADT with a result composed of word reads
            read.replaceBy(readRes)
            read.block.body.remove(read)

        if not readIsMarker:
            sequelBlock = sequelBlock if sequelBlock is not None else read.block

        elif read is not None:
            read.block.body.remove(read)
        
        for _, suc in cfg.cfg[read]:
            self.rewriteAdtReadToReadOfWords(hls, memUpdater, startBlock, suc, DATA_WIDTH,
                                             cfg, predecessorsSeen,
                                             currentOffsetVar, predWordVar, word_t)
    
