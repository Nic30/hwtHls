from collections import defaultdict
from collections import deque
from math import ceil
from typing import Dict, Optional, List, Set, DefaultDict, Deque

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, IN_STREAM_POS
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromAst.memorySSAUpdater import MemorySSAUpdater
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class ReadCfg():
    """
    Container of informations about stream read operations control flow graph

    :ivar cfg: the depndencies of reads as they appear in code
    :note: None represents the starting node
    :ivar inStreamPos: the bit offset of start of the read
    :ivar mustProduceOffset: True if the read must produce a variable with current offset of successors to use
    """

    def __init__(self):
        self.cfg: DefaultDict[HlsStreamProcRead, UniqList[HlsStreamProcRead]] = defaultdict(UniqList)
        self.cfg[None] = UniqList()
        self.inStreamPos: DefaultDict[HlsStreamProcRead, UniqList[int]] = defaultdict(UniqList)
        self.mustProduceOffset: Dict[Optional[HlsStreamProcRead], bool] = {}
        self.predecessors: Dict[Optional[HlsStreamProcRead], Set[HlsStreamProcRead]] = {}
    
    def addTransition(self, src: HlsStreamProcRead, dst: HlsStreamProcRead):
        self.cfg[src].append(dst)
    
    def resolvePredecessors(self):
        predecessors = self.predecessors
        for r in self.cfg.keys():
            predecessors[r] = set()

        for r, sucs in self.cfg.items():
            for suc in sucs:
                predecessors[suc].add(r)

    def resolveFragmentAlignments(self, cur: Optional[HlsStreamProcRead]):
        """
        The new word from stream is required if there is not enough of bits in previous word.
        """
        curWidth = 0 if cur is None else cur._dtype.bit_length()
        for suc in self.cfg[cur]:
            sucBegins = self.inStreamPos[suc]
            for curBegin in self.inStreamPos[cur]:
                curEnd = curBegin + curWidth 
                if curEnd not in sucBegins:
                    sucBegins.append(curEnd)
                    self.resolveFragmentAlignments(suc) 


class SsaPassAxiStreamReadLowering(SsaPass):
    """
    Lower the read of abstract datatype from AMBA AXI-stream interfaces to a read of words.
    
    1. Build CFG of parsing and in stream chunk possitions
        * DFS search the SSA for reads and compute the offset
    2. Rewrite reads of ADTs to read of words
    
    :note: Problematic features
        * SSA CFG does nore corresponds to read CFG
            * blocks may not constain reads, there can be multiple paths between same reads
            * cycles in SSA does not necessary mean a cycle in read CFG
    """

    def collectAllReachableReadsFromBlockEnd(self, b: SsaBasicBlock, seen: Set[SsaBasicBlock],
                                             firstReadInBlock: Dict[SsaBasicBlock, HlsStreamProcRead]):
        seen.add(b)

        r = firstReadInBlock.get(b, None)
        if r is not None:
            yield r
            return
        
        for suc in b.successors.iter_blocks():
            if suc not in seen:
                yield from self.collectAllReachableReadsFromBlockEnd(suc, seen, firstReadInBlock)

    def detectReadGraphs(self,
                         predecessor: Optional[HlsStreamProcRead],
                         block: SsaBasicBlock,
                         allReads: UniqList[HlsStreamProcRead],
                         readCfg: ReadCfg,
                         ):
        """
        DFS search all read sequences
        
        :note: 1 read instance can actualy be readed multiple times e.g. in cycle
            however the thing what we care about are possible successor reads of a read
        """

        for instr in block.body:
            if instr in allReads:
                if instr in readCfg.cfg or instr in readCfg.cfg[predecessor]:
                    return
                instr: HlsStreamProcRead
                readCfg.addTransition(predecessor, instr)
                if instr is not None and instr._inStreamPos.isEnd():
                    predecessor = None
                else:
                    predecessor = instr
        
        for suc in block.successors.iter_blocks():
            self.detectReadGraphs(predecessor, suc, allReads, readCfg)
        
    def rewriteAdtReadToReadOfWords(self,
                                    memUpdater: MemorySSAUpdater,
                                    startBlock,
                                    read: Optional[HlsStreamProcRead],
                                    DATA_WIDTH: int,
                                    readCfg: ReadCfg,
                                    prevWordVars: Deque[SsaValue],
                                    predecessorsSeen: Dict[HlsStreamProcRead, int],
                                    currentOffsetVar: RtlSignal):
        """
        :param read: a current read instruction object which shoul be rewritten
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
                pass
        possibleOffset = readCfg.inStreamPos[read]
        successors = readCfg.cfg[read]
#        if len(successors) > 1:
#            raise NotImplementedError(successors)
        
        if read is None:
            w = 0
            if possibleOffset != [0, ]:
                # read words to satisfy initial offset
                # for last, _ in iter_with_last(range(ceil(max(possibleOffset) / DATA_WIDTH))):
                #    endOfStream = last and not successors
                #    r = HlsStreamProcRead(read._parent, read._src, Bits(DATA_WIDTH), endOfStream)
                #    prevWordVars.append(r)
                raise NotImplementedError("Use first word mask to resolve the offsetVar")
            else:
                memUpdater.writeVariable(currentOffsetVar, (), startBlock, currentOffsetVar._dtype.from_py(0))
        else:
            # [todo] do not rewrite if this is already a read of a full word
            w = read._dtype.bit_length()
    
            # if number of words differs in offset varvariants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitely specified 

            # shared words for offset variants
            minOffset = min(possibleOffset) % DATA_WIDTH
            maxOffset = max(possibleOffset) % DATA_WIDTH
            exprBuilder = SsaExprBuilder(read.block, read.block.body.index(read))
            mayResultInDiffentNoOfWords = ceil((minOffset + w) / DATA_WIDTH) != ceil((maxOffset + w) / DATA_WIDTH)
            if mayResultInDiffentNoOfWords:
                raise NotImplementedError("Create a block which reads an extra last word and create a transitions from it to all blocks for that offsets")
        
            if maxOffset == 0:
                maxNoOfWords = ceil(w / DATA_WIDTH)
            else:
                maxNoOfWords = ceil((w - (DATA_WIDTH - maxOffset)) / DATA_WIDTH)

            for last, _ in iter_with_last(range(maxNoOfWords)):
                endOfStream = last and read._inStreamPos.isEnd()
                partRead = HlsStreamProcRead(read._parent, read._src, Bits(DATA_WIDTH), endOfStream)
                prevWordVars.append(partRead)
                exprBuilder._insertInstr(partRead)
            
            if len(possibleOffset) > 1:
                offsetCaseCond = []
                _currentOffsetVar = memUpdater.readVariable(currentOffsetVar, read.block)
                for last, off in iter_with_last(possibleOffset):
                    if last: 
                        # only option left, check not required
                        offEn = None
                    else:
                        offEn = exprBuilder._binaryOp(_currentOffsetVar, AllOps.EQ, currentOffsetVar._dtype.from_py(off % DATA_WIDTH))
                    offsetCaseCond.append(offEn)

                offsetBranches, sequelBlock = exprBuilder.insertBlocks(offsetCaseCond)
            else:
                offsetBranches, sequelBlock = [read.block], None

            readResults = []
            for off, br in zip(possibleOffset, offsetBranches):
                off: int
                br: SsaBasicBlock
                if br is not read.block:
                    _exprBuilder = SsaExprBuilder(br)
                else:
                    _exprBuilder = exprBuilder
                    
                parts = []
                end = off + w
                inWordOffset = off % DATA_WIDTH
                _w = w
                wordCnt = ceil((end - off) / DATA_WIDTH)
                if inWordOffset == 0 and len(possibleOffset) > 1:
                    # now not reading last word of predecessor but other offsets variant are using it
                    chunkWords = prevWordVars[1:]
                else:
                    chunkWords = prevWordVars

                for wordI in range(wordCnt):
                    bitsToTake = min(_w, DATA_WIDTH - inWordOffset)
                    endOfStream = read._inStreamPos.isEnd() and _w - bitsToTake == 0
                    partRead = chunkWords[wordI]

                    if inWordOffset != 0:
                        # take from previous word
                        # [todo] potentially can be None if the start of stream is not aligned
                        partRead = _exprBuilder._binaryOp(partRead, AllOps.INDEX, SLICE.from_py(slice(off + bitsToTake, off, -1)))
                        inWordOffset = 0
                    else:
                        # read a new word
                        if bitsToTake != DATA_WIDTH:
                            assert bitsToTake > 0, bitsToTake
                            partRead = _exprBuilder._binaryOp(partRead, AllOps.INDEX, SLICE.from_py(slice(off + bitsToTake, off, -1)))
        
                    _w -= bitsToTake
                    parts.append(partRead)
                
                readRes = None
                for p in parts:
                    if readRes is None:
                        readRes = p
                    else:
                        # left must be latest, right the first
                        readRes = _exprBuilder._binaryOp(p, AllOps.CONCAT, readRes)
                readResults.append(readRes)
                memUpdater.writeVariable(currentOffsetVar, (), br, currentOffsetVar._dtype.from_py(end % DATA_WIDTH))

            # resolve a value which will represent the original read
            if len(possibleOffset) != 1:
                sequelBlock: SsaBasicBlock
                readRes = SsaPhi(sequelBlock.ctx, readResults[0]._dtype)
                for v, b in zip(readResults, offsetBranches):
                    readRes.appendOperand(v, b)
                sequelBlock.appendPhi(readRes)
            else:
                readRes = readResults[0]
    
            # replace original read of ADT with a result composed of word reads
            for u in tuple(read.users):
                u.replaceInput(read, readRes)
            read.block.body.remove(read)

        if read is None:
            memUpdater.sealBlock(startBlock)
        else:
            self._sealBlocksUntilStart(memUpdater, startBlock, sequelBlock if sequelBlock is not None else read.block)
        
        if len(possibleOffset) == 1 and (possibleOffset[0] + w) % DATA_WIDTH == 0:
            prevWordVars.clear()
        elif mayResultInDiffentNoOfWords:
            raise NotImplementedError("Need to create a mux from last 2 words to pass last word to a successor")
        else:
            # let only last word
            for _ in range(len(prevWordVars) - 1):
                prevWordVars.popleft()
        
        for suc in successors:
            self.rewriteAdtReadToReadOfWords(memUpdater, startBlock, suc, DATA_WIDTH,
                                             readCfg, prevWordVars, predecessorsSeen, currentOffsetVar)
    
    def _sealBlocksUntilStart(self, memUpdater: MemorySSAUpdater, startBlock: SsaBasicBlock, curBlock: SsaBasicBlock):
        if startBlock is curBlock:
            return

        memUpdater.sealBlock(curBlock)
        for pred in curBlock.predecessors:
            self._sealBlocksUntilStart(memUpdater, startBlock, pred)
        
    def _detectReads(self, startBlock: SsaBasicBlock):
        reads: UniqList[HlsStreamProcRead] = UniqList()
        for block in collect_all_blocks(startBlock, set()):
            for instr in block.body:
                if isinstance(instr, HlsStreamProcRead):
                    instr: HlsStreamProcRead
                    intf = instr._src
                    if isinstance(intf, AxiStream):
                        reads.append(instr)
        return reads

    def _collectAllPredecessors(self, b: SsaBasicBlock, seen: Set[SsaBasicBlock]):
        for pred in b.predecessors:
            if pred not in seen:
                seen.add(pred)
                self._collectAllPredecessors(pred, seen)

    def _findCommonPredecessorOfBlocks(self, blocks: List[SsaBasicBlock]):
        if len(blocks) == 1:
            return blocks[0]

        # find common predecessor
        preds = None
        for b in blocks:
            _preds: Set[SsaBasicBlock] = set((b,))
            self._collectAllPredecessors(b, _preds)
            if preds is None:
                preds = _preds
            else:
                preds = preds.union(_preds)
            
            assert preds, "Must have some common predecessor"
        # select the predecessors which does not have any predecessor as successor
        _preds = []
        for p in preds:
            p: SsaBasicBlock
            sucs = set(p.successors.iter_blocks()).difference(preds)
            if not sucs:
                _preds.append(p)
            elif len(sucs) == 1:
                sucs = tuple(sucs)
                if sucs[0] is p:
                    _preds.append(p)
        
        if len(_preds) > 1:
            raise NotImplementedError("Multiple undistinguishable predecessors", _preds)
        elif not _preds:
            raise NotImplementedError("No common predecessor for blocks", [b.label for b in blocks])
        else:
            return preds[0]

    def _findReadStartBlock(self, firstReadInstrs: List[HlsStreamProcRead]):
        startBlocks = [i.block for i in firstReadInstrs]
        if len(set(startBlocks)) == 1:
            return startBlocks[0]
        else:
            return self._findCommonPredecessorOfBlocks(startBlocks)
        
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
            readCfg = ReadCfg()
            allReads = readsForIntf[intf]
            self.detectReadGraphs(None, to_ssa.start, allReads, readCfg)
            readCfg.inStreamPos[None].append(0)
            readCfg.resolveFragmentAlignments(None)
            readCfg.resolvePredecessors()

            offsetVar = hls._ctx.sig(f"{intf._name}_offset", Bits(log2ceil(intf.DATA_WIDTH - 1)))
            memUpdater = MemorySSAUpdater(None, None)
            
            # convert all reads to reads of complete words only
            prevWordVars = deque()
            predecessorsSeen = {r: 0 for r in allReads}
            startBlock = self._findReadStartBlock(readCfg.cfg[None])
            self.rewriteAdtReadToReadOfWords(memUpdater, startBlock, None, intf.DATA_WIDTH, readCfg, prevWordVars,
                                             predecessorsSeen, offsetVar)
        
