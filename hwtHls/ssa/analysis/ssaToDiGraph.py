from networkx.classes.digraph import DiGraph

from hwtHls.frontend.pyBytecode.loopsDetect import PyBytecodeLoop
from hwtHls.ssa.basicBlock import SsaBasicBlock


class SsaLoop(PyBytecodeLoop[SsaBasicBlock]):

    @classmethod
    def _getLoopLabel(cls, entry: SsaBasicBlock, loopIndex:int):
        if loopIndex == 0:
            return f"L<{entry.label:s}>"
        else:
            return f"L<{entry.label:s}>subL{loopIndex:d}"

def ssaToDiGraph(ssaStart: SsaBasicBlock) -> DiGraph:
    g = DiGraph()
    worklist = [ssaStart]
    seen = set()
    while worklist:
        n: SsaBasicBlock = worklist.pop()
        if n in seen:
            continue
        seen.add(n)
        g.add_node(n)
        for suc in n.successors.iterBlocks():
            g.add_edge(n, suc)
            if suc not in seen:
                worklist.append(suc)
    return g
