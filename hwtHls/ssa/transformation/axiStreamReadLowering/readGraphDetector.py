from _collections import defaultdict
from itertools import chain
from typing import DefaultDict, Tuple, List, Optional, Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead
from hwtHls.ssa.basicBlock import SsaBasicBlock


class ReadGraphDetector():
    """
    Detector of informations about stream read operations control flow graph

    :ivar cfg: the depndencies of reads as they appear in code
    :note: None represents the starting node
    :ivar DATA_WIDTH: number of bits of data in a single stream word
    :ivar allReads: list of all reads to keep all structures ordered in deterministic order
    """

    def __init__(self, DATA_WIDTH: int,
                         allReads: UniqList[HlsStreamProcRead]):
        self.DATA_WIDTH = DATA_WIDTH
        self.allReads = allReads
        self.cfg: DefaultDict[HlsStreamProcRead, UniqList[Tuple[int, HlsStreamProcRead]]] = defaultdict(UniqList)
        self.cfg[None] = UniqList()
        self.inWordOffset: DefaultDict[List[int]] = defaultdict(list)
        self.predecessors: DefaultDict[UniqList[Optional[HlsStreamProcRead]]] = defaultdict(UniqList)
    
    def addTransition(self, src: HlsStreamProcRead, dstInWordOffset: int, dst: HlsStreamProcRead):
        self.cfg[src].append((dstInWordOffset, dst))
        self.cfg[dst] = UniqList()
    
    def detectReadGraphs(self,
                         predecessor: Optional[HlsStreamProcRead],
                         predEndOffset: int,
                         block: SsaBasicBlock,
                         ):
        """
        DFS search all read sequences
        
        :note: 1 read instance can actualy be readed multiple times e.g. in cycle
            however the thing what we care about are possible successor reads of a read
        """

        for instr in block.body:
            if instr in self.allReads:
                if instr in self.cfg and (predEndOffset, instr) in self.cfg[predecessor]:
                    # already seen with this offset and already resolved
                    return
                instr: HlsStreamProcRead
                self.addTransition(predecessor, predEndOffset, instr)
                if instr is not None and instr._inStreamPos.isEnd():
                    predecessor = None
                    predEndOffset = 0
                else:
                    predecessor = instr
                    predEndOffset = (predEndOffset + instr._dtype.bit_length()) % self.DATA_WIDTH
        
        for suc in block.successors.iter_blocks():
            self.detectReadGraphs(predecessor, predEndOffset, suc)

    def resolvePossibleOffset(self):
        self.inWordOffset[None].append(0)
        for pred in chain(self.allReads, (None,)):
            successors = self.cfg[pred]
            for sucOffset, suc in successors:
                self.inWordOffset[suc].append(sucOffset)
                self.predecessors[suc].append(pred)
        
        for k, v in self.inWordOffset.items():
            self.inWordOffset[k] = sorted(set(v))
        
    def findReadStartBlock(self):
        return self._findReadStartBlock(self.cfg[None])

    def _findReadStartBlock(self, firstReadInstrs: List[HlsStreamProcRead]):
        startBlocks = [i.block for _, i in firstReadInstrs]
        if len(set(startBlocks)) == 1:
            return startBlocks[0]
        else:
            return self.findCommonPredecessorOfBlocks(startBlocks)

    def collectAllPredecessors(self, b: SsaBasicBlock, seen: Set[SsaBasicBlock]):
        for pred in b.predecessors:
            if pred not in seen:
                seen.add(pred)
                self.collectAllPredecessors(pred, seen)

    def findCommonPredecessorOfBlocks(self, blocks: List[SsaBasicBlock]):
        if len(blocks) == 1:
            return blocks[0]

        # find common predecessor
        preds = None
        for b in blocks:
            _preds: Set[SsaBasicBlock] = set((b,))
            self.collectAllPredecessors(b, _preds)
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
     
