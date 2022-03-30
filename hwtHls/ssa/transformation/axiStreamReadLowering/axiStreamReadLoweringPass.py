from collections import defaultdict
from math import ceil
from typing import Dict, Optional, List, Set, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcReadAxiStream, IN_STREAM_POS, \
    HlsStreamProcRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.transformation.axiStreamReadLowering.readGraphDetector import ReadGraphDetector
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromAst.memorySSAUpdater import MemorySSAUpdater
from hwtLib.amba.axis import AxiStream
from hwtHls.ssa.value import SsaValue


class SliceOfStreamWord():
    """
    :note: highBitNo and lowBitNo are related only to data part, masks and other word signals slices are deduced from this
    """

    def __init__(self, word: HlsStreamProcRead, highBitNo: int, lowBitNo: int):
        self.word = word
        self.highBitNo = highBitNo
        self.lowBitNo = lowBitNo
        

class SsaPassAxiStreamReadLowering(SsaPass):
    """
    Lower the read of abstract datatype from AMBA AXI-stream interfaces to a read of words.
    
    1. Build CFG of parsing and in stream chunk positions
        * DFS search the SSA for reads and compute the offset
    2. Rewrite reads of ADTs to read of words
    
    :note: Problematic features
        * SSA CFG does not correspond to read CFG
            * blocks may not contain reads, there can be multiple paths between same reads
            * cycles in SSA does not necessary mean a cycle in read CFG
    """

    @classmethod
    def collectAllReachableReadsFromBlockEnd(cls, b: SsaBasicBlock, seen: Set[SsaBasicBlock],
                                             firstReadInBlock: Dict[SsaBasicBlock, HlsStreamProcReadAxiStream]):
        seen.add(b)
        r = firstReadInBlock.get(b, None)
        if r is not None:
            yield r
            return
        
        for suc in b.successors.iterBlocks():
            if suc not in seen:
                yield from cls.collectAllReachableReadsFromBlockEnd(suc, seen, firstReadInBlock)

    def _sealBlocksUntilStart(self, memUpdater: MemorySSAUpdater, startBlock: SsaBasicBlock, curBlock: SsaBasicBlock):
        if startBlock is curBlock or curBlock in memUpdater.sealedBlocks:
            return
        memUpdater.sealBlock(curBlock)
        for pred in curBlock.predecessors:
            self._sealBlocksUntilStart(memUpdater, startBlock, pred)
        
    def _detectReads(self, startBlock: SsaBasicBlock):
        reads: UniqList[HlsStreamProcReadAxiStream] = UniqList()
        for block in collect_all_blocks(startBlock, set()):
            for instr in block.body:
                if isinstance(instr, HlsStreamProcReadAxiStream):
                    instr: HlsStreamProcReadAxiStream
                    intf = instr._src
                    if isinstance(intf, AxiStream):
                        reads.append(instr)
        return reads

    def apply(self, hls: "HlsStreamProc", to_ssa: AstToSsa):
        reads = self._detectReads(to_ssa.start)
        intfs = UniqList()
        readsForIntf = defaultdict(UniqList)
        for r in reads:
            intfs.append(r._src)
            readsForIntf[r._src].append(r)
        
        # blocks = list(collect_all_blocks(to_ssa.start, set()))
        for intf in intfs:
            intf: AxiStream
            readCfg = ReadGraphDetector(intf.DATA_WIDTH, readsForIntf[intf])
            readCfg.detectReadGraphs(None, 0, to_ssa.start)
            readCfg.resolvePossibleOffset()

            offsetVar = hls._ctx.sig(f"{intf._name}_offset", Bits(log2ceil(intf.DATA_WIDTH - 1)))
            
            data_w = intf.DATA_WIDTH
            mask_w = 0
            if intf.USE_KEEP:
                mask_w += ceil(data_w / 8)
            if intf.USE_STRB:
                mask_w += ceil(data_w / 8)
            control_w = 1  # "last" signal
    
            if intf.ID_WIDTH:
                raise NotImplementedError()
            
            predWordVar = hls._ctx.sig(f"{intf._name}_pred_word", Bits(control_w + mask_w + data_w))
            # convert all reads to reads of complete words only
            predecessorsSeen = {r: 0 for r in readCfg.allReads}
            startBlock = readCfg.findReadStartBlock()
            memUpdater = MemorySSAUpdater(None, None)
            memUpdater.writeVariable(offsetVar, (), startBlock, offsetVar._dtype.from_py(None))
            memUpdater.writeVariable(predWordVar, (), startBlock, predWordVar._dtype.from_py(None))
            
            self.rewriteAdtReadToReadOfWords(hls, memUpdater, startBlock, None, intf.DATA_WIDTH, readCfg,
                                             predecessorsSeen, offsetVar, predWordVar)

    def _applySlice(self, exprBuilder: SsaExprBuilder, read: HlsStreamProcRead, highBitNo: int, lowBitNo: int):
        # :note: this method is used to select the part from word read which belongs to some ADT read
        return exprBuilder._binaryOp(read, AllOps.INDEX, SLICE.from_py(slice(highBitNo, lowBitNo, -1)))

    def _applyConcateAdd(self, exprBuilder: SsaExprBuilder, curent: Optional[SsaValue], toAdd: RtlSignal):
        _toAdd = exprBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if curent is None:
            return _toAdd
        else:
            return exprBuilder.concat(_toAdd, curent)

    def _applyOrAdd(self, exprBuilder: SsaExprBuilder, curent: Optional[SsaValue], toAdd: RtlSignal):
        _toAdd = exprBuilder._normalizeOperandForOperatorResTypeEval(toAdd)[0]
        if curent is None:
            return _toAdd
        else:
            return exprBuilder._binaryOp(_toAdd, AllOps.OR, curent)

    def _applyConcat(self, exprBuilder: SsaExprBuilder, read: HlsStreamProcRead, parts: List[Union[HlsStreamProcRead, SliceOfStreamWord]]):
        intf = read._src
        if intf.DEST_WIDTH or intf.ID_WIDTH or intf.USER_WIDTH:
            raise NotImplementedError(read)
        # mask_w = ceil(data_w / 8)
        data = None
        strb = None
        keep = None
        last = None
        DW = intf.DATA_WIDTH
        for part in parts:
            if isinstance(part, SliceOfStreamWord):
                hi, lo = part.highBitNo, part.lowBitNo
                if intf.USE_STRB or intf.USE_KEEP:
                    assert hi % 8 == 0, hi
                    assert lo % 8 == 0, lo
                    mhi, mlo = hi // 8, lo // 8
                
                part = part.word
                # derived SsaPhi and RtlSignal does not have data,strb,keep and last property
                data = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, hi, lo))
                off = DW
                if intf.USE_STRB:
                    strb = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, off + mhi, off + mlo))
                    off += DW // 8

                if intf.USE_KEEP:
                    keep = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, off + mhi, off + mlo))
                    off += DW // 8

            else:
                assert isinstance(part, HlsStreamProcRead), part
                data = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, DW, 0))
                off = DW
                if intf.USE_STRB:
                    strb = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, off + DW // 8, off))
                    off += DW // 8
                if intf.USE_KEEP:
                    keep = self._applyConcateAdd(exprBuilder, data, self._applySlice(exprBuilder, part, off + DW // 8, off))
                    off += DW // 8

            last = self._applyOrAdd(exprBuilder, last, self._applySlice(exprBuilder, part, off + 1, off))

        return exprBuilder.concat(data,
                                  * ((strb,) if intf.USE_STRB else ()),
                                  * ((keep,) if intf.USE_KEEP else ()),
                                  last)

    def rewriteAdtReadToReadOfWords(self,
                                    hls: "HlsStreamProc",
                                    memUpdater: MemorySSAUpdater,
                                    startBlock,
                                    read: Optional[HlsStreamProcReadAxiStream],
                                    DATA_WIDTH: int,
                                    readCfg: ReadGraphDetector,
                                    predecessorsSeen: Dict[HlsStreamProcReadAxiStream, int],
                                    currentOffsetVar: RtlSignal,
                                    predWordVar: RtlSignal):
        """
        :param read: a current read instruction object which should be rewritten
        :param DATA_WIDTH: number of bits in a single bus word
        :param readCfg: an object which keeps the info about CFG and offsets of individual reads
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
        * for every read which may fail (due to premature end of frame) generate erorr handler jumps
        
        :note: If there are reads on multiple input streams this may result in changed order in which bus words are accepted
            which may result in deadlock.
            
        """
        if read is not None:
            predecessorsSeen[read] += 1
            if len(readCfg.predecessors[read]) != predecessorsSeen[read]:
                # not all predecessors have been seen and we run this function only after all predecessors were seen
                return
            else:
                # [todo] if the read has multiple predecessors and the last word from them is required and may differ we need o create
                # a phi to select it and then use it as a last word from previous read
                self._sealBlocksUntilStart(memUpdater, startBlock, read.block)

        possibleOffsets = readCfg.inWordOffset[read]
        if not possibleOffsets:
            raise AssertionError("This is an accessible read, it should be already removed", read)
        
        if read is None:
            w = 0
            if possibleOffsets != [0, ]:
                # read words to satisfy initial offset
                # for last, _ in iter_with_last(range(ceil(max(possibleOffsets) / DATA_WIDTH))):
                #    endOfStream = last and not successors
                #    r = HlsStreamProcReadAxiStream(read._parent, read._src, Bits(DATA_WIDTH), endOfStream)
                #    prevWordVars.append(r)
                raise NotImplementedError("Use first word mask to resolve the offsetVar", possibleOffsets)
            else:
                memUpdater.writeVariable(currentOffsetVar, (), startBlock, currentOffsetVar._dtype.from_py(0))
        else:
            # [todo] do not rewrite if this is already a read of an aligned full word
            sequelBlock = read.block
            w = read._dtypeOrig.bit_length()
    
            # if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified 

            # shared words for offset variants
            minOffset = min(possibleOffsets)
            maxOffset = max(possibleOffsets)
            exprBuilder = SsaExprBuilder(read.block, read.block.body.index(read))
            mayResultInDiffentNoOfWords = ceil((minOffset + w) / DATA_WIDTH) != ceil((maxOffset + w) / DATA_WIDTH)
            if mayResultInDiffentNoOfWords:
                raise NotImplementedError("Create a block which reads an extra last word and create a transitions from it to all blocks for that offsets")
            
            # collect/construct all reads common for every successor branch
            prevWordVars: List[HlsStreamProcRead] = [] 
            # load last word
            if possibleOffsets != [0, ]:
                prevWordVars.append(memUpdater.readVariable(predWordVar, read.block))

            # add read for every word which will be used in this read of frame fragment
            if maxOffset == 0 or read._inStreamPos.isBegin():
                minNoOfWords = ceil((minOffset + w) / DATA_WIDTH)
            else:
                # only the data which will overflow to another words
                minNoOfWords = ceil(max(0, (w - (DATA_WIDTH - minOffset))) / DATA_WIDTH)

            if minNoOfWords != 0:
                word_t = HlsStreamProcReadAxiStream._getWordType(read._src)
            else:
                word_t = None

            for last, _ in iter_with_last(range(minNoOfWords)):
                # endOfStream = last and read._inStreamPos.isEnd()
                partRead = HlsStreamProcRead(read._parent, read._src, word_t)
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
                memUpdater.sealBlock(sequelBlock)
            else:
                offsetBranches, sequelBlock = [read.block], read.block
            
            resVar = hls._ctx.sig(read._name, read._dtype)
            # [todo] aggregate rewrite for all reads in this same block to reduce number of branches because of offset
            for off, br in zip(possibleOffsets, offsetBranches):
                off: int
                br: SsaBasicBlock
                # memUpdater.sealBlock(br)
                if br is not read.block:
                    _exprBuilder = SsaExprBuilder(br)
                else:
                    _exprBuilder = exprBuilder
                    
                end = off + w
                inWordOffset = off % DATA_WIDTH
                _w = w
                wordCnt = ceil(max(0, end - 1) / DATA_WIDTH)
                if inWordOffset == 0 and len(possibleOffsets) > 1:
                    # now not reading last word of predecessor but other offsets variant are using it
                    chunkWords = prevWordVars[1:]
                else:
                    chunkWords = prevWordVars[:]

                assert len(chunkWords) == wordCnt, (read, wordCnt, chunkWords)
                parts = []
                for wordI in range(wordCnt):
                    bitsToTake = min(_w, DATA_WIDTH - inWordOffset)
                    # endOfStream = read._inStreamPos.isEnd() and _w - bitsToTake == 0
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

                readRes = self._applyConcat(exprBuilder, read, reversed(parts))
                assert readRes._dtype.bit_length() == resVar._dtype.bit_length(), (readRes, readRes._dtype, resVar._dtype)

                memUpdater.writeVariable(resVar, (), br, readRes)
                memUpdater.writeVariable(currentOffsetVar, (), br, currentOffsetVar._dtype.from_py(end % DATA_WIDTH))
                memUpdater.writeVariable(predWordVar, (), br, chunkWords[-1])

            # resolve a value which will represent the original read
            readRes = memUpdater.readVariable(resVar, sequelBlock)
    
            # replace original read of ADT with a result composed of word reads
            read.replaceBy(readRes)
            read.block.body.remove(read)

        if read is not None:
            sequelBlock = sequelBlock if sequelBlock is not None else read.block
        
        for _, suc in readCfg.cfg[read]:
            self.rewriteAdtReadToReadOfWords(hls, memUpdater, startBlock, suc, DATA_WIDTH,
                                             readCfg, predecessorsSeen,
                                             currentOffsetVar, predWordVar)
    
