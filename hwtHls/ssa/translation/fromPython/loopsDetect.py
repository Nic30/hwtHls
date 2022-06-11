from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, NamedTuple, Dict, List

from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockLabel


class PyBytecodeLoop():
    """
    :note: Integers represents offset of instruction where block starts.
    """

    def __init__(self, label: str, entryPoint: BlockLabel, allBlocks: Set[BlockLabel], backedges: Set[BlockLabel]):
        self.label = label
        self.entryPoint = entryPoint
        self.allBlocks = allBlocks
        self.backedges = backedges

    @staticmethod
    def detectBackedges(cfg: DiGraph, loop: Set[BlockLabel], entryPoint: BlockLabel) -> Set[BlockLabel]:
        "Detect edges which are jumping to loop entrypoint from the loop body"
        res = set()
        for pred in cfg.predecessors(entryPoint):
            if pred in loop:
                res.add(pred)

        return res
        
    @staticmethod
    def detectLoops(cfg: DiGraph, loopCntPerBlock: Dict[int, 'PyBytecodeLoop']):
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

                if entry is None and (0,) in loop:
                    entry = (0,)
                else:
                    assert entry is not None, loop
                
                loopIndex = loopCntPerBlock.get(entry, 0)
                loopCntPerBlock[entry] = loopIndex + 1
                if loopIndex == 0:
                    label = f"L{entry[-1]:d}"
                else:
                    label = f"L{entry[-1]:d}subL{loopIndex:d}"
                yield PyBytecodeLoop(label, entry, loop, PyBytecodeLoop.detectBackedges(cfg, loop, entry))
                # search nested loops
                loopCfg: DiGraph = cfg.subgraph(loop).copy(as_view=False)
                for pred in tuple(loopCfg.predecessors(entry)):
                    loopCfg.remove_edge(pred, entry)

                yield from PyBytecodeLoop.detectLoops(loopCfg, loopCntPerBlock)

    @staticmethod
    def collectLoopsPerBlock(cfg: DiGraph) ->  Dict[int, List["PyBytecodeLoop"]]:
        loops: Dict[int, List[PyBytecodeLoop]] = {}
        for loop in PyBytecodeLoop.detectLoops(cfg, {}):
            entryOffset: int = loop.entryPoint[0]
            loopsPerBlock = loops.get(entryOffset, None)
            if loopsPerBlock is None:
                loopsPerBlock = loops[entryOffset] = []
            loopsPerBlock.append(loop)
        return loops

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.entryPoint[-1]}>"


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
