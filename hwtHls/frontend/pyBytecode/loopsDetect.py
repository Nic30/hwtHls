from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, NamedTuple, Dict, List, Tuple, TypeVar, Generic

from hwtHls.frontend.pyBytecode.blockPredecessorTracker import BlockLabel


BlockT = TypeVar("T")


class PyBytecodeLoop(Generic[BlockT]):
    """
    :note: Integers represents offset of instruction where block starts.
    """

    def __init__(self, label: str, entryPoint: BlockT, allBlocks: Set[BlockT], allEdges: Tuple[Tuple[BlockT, BlockT], ...]):  # , backedges: Set[int]
        self.label = label
        self.entryPoint = entryPoint
        self.allBlocks = allBlocks
        self.allEdges = allEdges
        # self.backedges = backedges

    # @staticmethod
    # def detectBackedges(cfg: DiGraph, loop: Set[int], entryPoint: int) -> Set[int]:
    #    "Detect edges which are jumping to loop entrypoint from the loop body"
    #    res: Set[int] = set()
    #    for pred in cfg.predecessors(entryPoint):
    #        if pred in loop:
    #            res.add(pred)
    #
    #    return res
    @classmethod
    def _getLoopLabel(cls, entry: BlockT, loopIndex:int):
        if loopIndex == 0:
            return f"L{entry:d}"
        else:
            return f"L{entry:d}subL{loopIndex:d}"

    @classmethod
    def detectLoops(cls, cfg: DiGraph, loopCntPerBlock: Dict[BlockT, 'PyBytecodeLoop']):
        """
        :attention: cfg is destroyed in process 
        """
        for loop in strongly_connected_components(cfg):
            loop: Set[BlockLabel]
            isLoop = len(loop) > 1
            if not isLoop:
                b = tuple(loop)[0]
                if cfg.has_predecessor(b, b):
                    # 1 node loop
                    isLoop = True

            if isLoop:
                entry = None
                for b in loop:
                    for pred in cfg.predecessors(b):
                        if pred not in loop:
                            assert entry is None, ("Loop is supposed to have just a single entry point", entry, pred, loop)
                            entry = b

                if entry is None and 0 in loop:
                    entry = 0
                else:
                    assert entry is not None, loop

                loopIndex = loopCntPerBlock.get(entry, 0)
                loopCntPerBlock[entry] = loopIndex + 1
                label = cls._getLoopLabel(entry, loopIndex)
                # PyBytecodeLoop.detectBackedges(cfg, loop, entry)
                yield cls(label, entry, loop, tuple(cfg.subgraph(loop).edges()))
                # search nested loops
                loopCfg: DiGraph = cfg.subgraph(loop).copy(as_view=False)
                for pred in tuple(loopCfg.predecessors(entry)):
                    loopCfg.remove_edge(pred, entry)

                yield from cls.detectLoops(loopCfg, loopCntPerBlock)

    @classmethod
    def collectLoopsPerBlock(cls, cfg: DiGraph) -> Dict[BlockT, List["PyBytecodeLoop"]]:
        loops: Dict[BlockT, List[PyBytecodeLoop]] = {}
        for loop in cls.detectLoops(DiGraph(cfg), {}):
            entryOffset: BlockT = loop.entryPoint
            loopsPerBlock = loops.get(entryOffset, None)
            if loopsPerBlock is None:
                loopsPerBlock = loops[entryOffset] = []
            loopsPerBlock.append(loop)
        return loops

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.entryPoint}>"


class PreprocLoopScope(NamedTuple("PreprocLoopScope", [("loop", PyBytecodeLoop),
                                                       ("iterationIndex", int)])):
    """
    Non-mutable label of preproc loop body segment.
    """

    def __new__(cls, loop: PyBytecodeLoop, iterationIndex: int):
        return super().__new__(cls, loop, iterationIndex)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.loop.label:s}i{self.iterationIndex}"
