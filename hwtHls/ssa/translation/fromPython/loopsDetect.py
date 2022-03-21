from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, NamedTuple

from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockLabel


class PyBytecodeLoop():
    """
    :note: Integers represents offset of instruction where block starts.
    """

    def __init__(self, entryPoint: BlockLabel, allBlocks: Set[BlockLabel], backedges: Set[BlockLabel]):
        self.entryPoint = entryPoint
        self.allBlocks = allBlocks
        self.backedges = backedges

    @staticmethod
    def detectBackedges(cfg: DiGraph, loop: Set[BlockLabel], entryPoint: BlockLabel) -> Set[BlockLabel]:
        "Detect edges which are jumping to loop entrypoint from the loop body"
        res = set()
        for pred in cfg.predecessors(entryPoint):
            if pred not in loop:
                res.add(pred)

        return res
        
    @staticmethod
    def detectLoops(cfg: DiGraph):
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
                yield PyBytecodeLoop(entry, loop, PyBytecodeLoop.detectBackedges(cfg, loop, entry))
                # search nested loops
                loopCfg: DiGraph = cfg.subgraph(loop).copy(as_view=False)
                for pred in tuple(loopCfg.predecessors(entry)):
                    loopCfg.remove_edge(pred, entry)

                yield from PyBytecodeLoop.detectLoops(loopCfg)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.entryPoint[-1]}>"


class PreprocLoopScope(NamedTuple("PreprocLoopScope", [("loop", PyBytecodeLoop),
                                                       ("iterationIndex", int)])):
    """
    Non-mutable label of preproc loop body segment.
    """

    def __new__(cls, loop: PyBytecodeLoop, iterationIndex: int):
        return super().__new__(cls, loop, iterationIndex)
    
    def __repr__(self, *args, **kwargs):
        return str(self)

    def __str__(self):
        return f"{self.loop.entryPoint[-1]:d}i{self.iterationIndex:d}"
