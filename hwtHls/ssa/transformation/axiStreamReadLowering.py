from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead
from hwt.pyUtils.uniqList import UniqList
from typing import Dict, Optional, List, Set, Tuple
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwt.hdl.types.bits import Bits
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import SLICE
from hwt.synthesizer.interface import Interface
from hwtLib.amba.axis import AxiStream


class SsaPassAxiStreamReadLowering(SsaPass):
    """
    Lower the read of abstract datatype from AMBA AXI-stream interfaces to a read of words.
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

    def detectReadGraphs(self, start: SsaBasicBlock, blocks: List[SsaBasicBlock]) -> Tuple[
            Dict[Interface, Dict[Optional[HlsStreamProcRead], UniqList[HlsStreamProcRead]]],
            Dict[Interface, List[HlsStreamProcRead]],
        ]:
        """
        :note: 1 read instance can actualy be readed multiple times e.g. in cycle
            however the thing what we care about are possible successor reads of a read
        """
        # Collect the reads and CFG for them so we know how are individual reads stacket upon each other
        # predecesor read to all possible successor reads, None represents the start
        readGraph: Dict[Interface, Dict[Optional[HlsStreamProcRead], UniqList[HlsStreamProcRead]]] = {}
        firstReadInBlock: Dict[Interface, Dict[SsaBasicBlock, HlsStreamProcRead]] = {}
        lastOpenReadInBlock: Dict[SsaBasicBlock, Dict[Interface, HlsStreamProcRead]] = {}
        allReads: Dict[Interface, List[HlsStreamProcRead]] = {}
        allInterfaces: UniqList[Interface] = UniqList()
        for b in blocks:
            prevRead: Dict[Interface, HlsStreamProcRead] = {}
            for instr in b.body:
                if isinstance(instr, HlsStreamProcRead):
                    instr: HlsStreamProcRead
                    intf = instr._src
                    if not isinstance(intf, AxiStream):
                        continue
                    
                    allInterfaces.append(intf)
                    allReads.setdefault(intf, []).append(instr)
                    _prevRead = prevRead.get(intf, None)
                    if _prevRead is None:
                        firstReadInBlock.setdefault(intf, {})[b] = instr
                    else:
                        readGraph.setdefault(intf, {})[_prevRead] = UniqList((instr,))

                    if instr._endOfStream:
                        # the frame ends there we do not need to look for successors to resolve word parts
                        prevRead.pop(intf, None)
                        readGraph.setdefault(intf, {})[instr] = UniqList()

            for intf, _prevRead in prevRead.items():
                if _prevRead is not None:
                    lastOpenReadInBlock[b][intf] = prevRead

        for b in blocks:
            blockLastReads = lastOpenReadInBlock.get(b, None)
            if blockLastReads is None:
                continue
            
            for intf in allInterfaces:
                openRead = blockLastReads.get(intf, None)
                if openRead is not None:
                    seen: Set[SsaBasicBlock] = set()
                    assert openRead not in readGraph[intf], openRead
                    readGraph[intf][openRead] = list(self.collectAllReachableReadsFromBlockEnd(b, seen, firstReadInBlock[intf]))

        for intf in allInterfaces:
            seen: Set[SsaBasicBlock] = set()
            readGraph[intf][None] = list(self.collectAllReachableReadsFromBlockEnd(start, seen, firstReadInBlock[intf]))

        return readGraph, allReads, allInterfaces
    
    def resolveFragmentAlignmentsWordPops(self,
                                          wordWidth: int,
                                          cur: Optional[HlsStreamProcRead],
                                          beginOffsets: UniqList[int],
                                          readGraph:Dict[Optional[HlsStreamProcRead], UniqList[HlsStreamProcRead]],
                                          offsetsOfRead: Dict[Optional[HlsStreamProcRead], UniqList[int]],
                                          ):
        """
        The new word from stream is required if there is not enough of bits in previous word.
        """
        curWidth = 0 if cur is None else cur._dtype.bit_length()
        for sucRead in readGraph[cur]:
            sucOffsets = offsetsOfRead.get(sucRead, None)
            if sucOffsets is None:
                sucOffsets = offsetsOfRead[sucRead] = UniqList()
            for off in beginOffsets:
                off = (off + curWidth) % wordWidth
                if off not in sucOffsets:
                    sucOffsets.append(off)
                    self.resolveFragmentAlignmentsWordPops(wordWidth, sucRead, sucOffsets, readGraph, offsetsOfRead)
        
    def rewriteAdtReadToReadOfWords(self, read: HlsStreamProcRead, possibleOffset: UniqList[int], prevWordVar: Optional[SsaValue]):
        if possibleOffset != [0, ]:
            raise NotImplementedError()
        if prevWordVar is not None:
            raise NotImplementedError()
        # [todo] do not rewrite if this is already a read of a full word

        off = 0
        DW = read._src.DATA_WIDTH
        w = read._dtype.bit_length()
        exprBuilder = SsaExprBuilder(read.block, read.block.body.index(read))
        parts = []
        while w:
            bitsToTake = min(off + w, DW - off)
            if off != 0:
                # take from previous word
                # [todo] potentially can be None if the start of stream is not aligned
                assert prevWordVar is not None
                partRead = exprBuilder._binaryOp(prevWordVar, AllOps.INDEX, SLICE.from_py(slice(off + bitsToTake, off, -1)))
                off = 0
            else:
                # read a new word
                endOfStream = read._endOfStream and w - bitsToTake == 0
                partRead = HlsStreamProcRead(read._parent, read._src, Bits(max(bitsToTake, DW)), endOfStream)
                exprBuilder._insertInstr(partRead)
                if bitsToTake != DW:
                    partRead = exprBuilder._binaryOp(partRead, AllOps.INDEX, SLICE.from_py(slice(off + bitsToTake, off, -1)))

            w -= bitsToTake
            parts.append(partRead)
        
        readRes = None
        for p in parts:
            if readRes is None:
                readRes = p
            else:
                # left must be latest, right the first
                readRes = exprBuilder._binaryOp(p, AllOps.CONCAT, readRes)
        
        for u in read.users:
            u.replaceInput(read, readRes)

        read.block.body.remove(read)

    def apply(self, hls: "HlsStreamProc", to_ssa: AstToSsa):
        blocks = list(collect_all_blocks(to_ssa.start, set()))
        readGraph, allReads, allIntfs = self.detectReadGraphs(to_ssa.start, blocks)

        # resolve format of state informations
        for intf in allIntfs:
            intf: AxiStream
            curOffsets = UniqList([0, ])
            offsetsOfRead: Dict[Optional[HlsStreamProcRead], Set[int]] = {}
            self.resolveFragmentAlignmentsWordPops(intf.DATA_WIDTH, None, curOffsets, readGraph[intf], offsetsOfRead)
        
            # convert all reads to reads of complete words only
            for r in allReads[intf]:
                prevWordVar = None
                self.rewriteAdtReadToReadOfWords(r, offsetsOfRead[r], prevWordVar)
        
