from collections import defaultdict
from itertools import chain
from typing import Tuple, List, Set, Dict, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.frontend.ast.statementsRead import HlsRead, HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.statementsWrite import HlsWrite, \
    HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame
from hwtHls.ssa.basicBlock import SsaBasicBlock


HlsReadOrWrite = Union[HlsRead, HlsWrite]
class StreamReadWriteGraphDetector():
    """
    Detector of informations about stream read/write operations for control flow graph

    :ivar cfg: the dependencies of reads/writes as they appear in code
    :note: None represents the starting node
    :ivar DATA_WIDTH: number of bits of data in a single stream word
    :ivar allStms: list of all reads/writes to keep all structures ordered in deterministic order
    """

    def __init__(self, DATA_WIDTH: int, allStms: UniqList[HlsReadOrWrite]):
        self.DATA_WIDTH = DATA_WIDTH
        self.allStms = allStms
        self.cfg: Dict[HlsReadOrWrite, UniqList[Tuple[int, HlsReadOrWrite]]] = {}
        self.cfg[None] = UniqList()
        self.inWordOffset: Dict[HlsReadOrWrite, List[int]] = defaultdict(list)
        self.predecessors: Dict[HlsReadOrWrite, UniqList[Union[HlsRead, HlsWrite, None]]] = defaultdict(UniqList)

    def _addTransition(self, src: HlsReadOrWrite, dstInWordOffset: int, dst: HlsReadOrWrite):
        assert isinstance(src, (HlsRead, HlsWrite)) or src is None, src
        assert isinstance(dst, (HlsRead, HlsWrite)) or dst is None, dst

        sucs = self.cfg.get(src, None)
        if sucs is None:
            sucs = self.cfg[src] = []
        sucs.append((dstInWordOffset, dst))
        if dst not in self.cfg:
            self.cfg[dst] = UniqList()

    def finalize(self):
        # convert defaultdict to dict
        self.inWordOffset = {k: v for k, v in self.inWordOffset.items()}
        self.predecessors = {k: v for k, v in self.predecessors.items()}

    def detectIoAccessGraphs(self,
                             predecessor: Union[HlsRead, HlsWrite, None],
                             predEndOffset: int,
                             block: SsaBasicBlock,
                             seenBlocks: Set[Tuple[int, SsaBasicBlock]]):
        """
        DFS search all read/write sequences
        
        :param seenBlocks: set of blocks which were seen for this specific position in packet
        :note: 1 read/write instance can actually be read/write multiple times e.g. in cycle
            however the thing what we care about are possible successor reads/writes of a read/write
        """
        
        wasAlreadySeen = (predEndOffset, block) in seenBlocks
        if not wasAlreadySeen:
            seenBlocks.add((predEndOffset, block))
        # endWasModified = False
        for instr in block.body:
            if instr in self.allStms:
                if instr in self.cfg and (predEndOffset, instr) in self.cfg[predecessor]:
                    # already seen with this offset and already resolved
                    return

                instr: HlsReadOrWrite
                self._addTransition(predecessor, predEndOffset, instr)
                if wasAlreadySeen:
                    # if wasAlreadySeen we just added the transition to a first io in the block and do not follow others
                    # because the block was already analized with this offset
                    return
                if isinstance(instr, (HlsStmReadEndOfFrame, HlsStmWriteEndOfFrame)):
                    predecessor = None
                    predEndOffset = 0
                    # endWasModified = True
                else:
                    predecessor = instr
                    if isinstance(instr, (HlsStmReadStartOfFrame, HlsStmWriteStartOfFrame)):
                        w = 0
                    else:
                        if isinstance(instr, HlsRead):
                            w = instr._dtypeOrig.bit_length()
                        else:
                            w = instr.operands[0]._dtype.bit_length()
                        # endWasModified = True

                    predEndOffset = (predEndOffset + w) % self.DATA_WIDTH
                # endWasModified = True

        for suc in block.successors.iterBlocks():
            self.detectIoAccessGraphs(predecessor, predEndOffset, suc, seenBlocks)

    def resolvePossibleOffset(self):
        self.inWordOffset[None].append(0)
        for pred in chain(self.allStms, (None,)):
            successors = self.cfg[pred]
            for sucOffset, suc in successors:
                self.inWordOffset[suc].append(sucOffset)
                self.predecessors[suc].append(pred)

        for k, v in self.inWordOffset.items():
            self.inWordOffset[k] = sorted(set(v))

    def findStartBlock(self):
        return self._findStartBlock(self.cfg[None])

    def _findStartBlock(self, firstReadInstrs: List[HlsReadOrWrite]):
        startBlocks = [i.block for _, i in firstReadInstrs]
        if len(set(startBlocks)) == 1:
            return startBlocks[0]
        else:
            return self._findCommonPredecessorOfBlocks(startBlocks)

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
            sucs = set(p.successors.iterBlocks()).difference(preds)
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

