from typing import Dict, List, Set, Tuple

from hwtHls.ssa.basicBlock import SsaBasicBlock


class DiscoverScc():
    """
    Discover strongly connected components

    Implements Path-based depth-first search for strong and biconnected components https://doi.org/10.1016/S0020-0190(00)00051-X
    :see: https://github.com/jdiehl/path-scc
    """

    def __init__(self, starts: List[SsaBasicBlock],
                 ignored_nodes: Set[SsaBasicBlock],
                 ignored_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
        """
        :param starts: at lesast all entry points into DFG, may contain also other nodes
        """
        self.done: Set[SsaBasicBlock] = set()
        self.preOrder: Dict[SsaBasicBlock, int] = {}
        self.S: List[SsaBasicBlock] = []
        self.P: List[SsaBasicBlock] = []
        self.C = 0
        self.components: List[List[SsaBasicBlock]] = []
        self.ignored_nodes = ignored_nodes
        self.ignored_edges = ignored_edges
        self.starts = starts

    def discover(self) -> List[List[SsaBasicBlock]]:
        assert self.C == 0, "This object can be used only once"
        ignored_nodes = self.ignored_nodes
        preOrder = self.preOrder
        for n in self.starts:
            if n not in ignored_nodes and n not in preOrder:
                self._process(n)

        return self.components

    def _process(self, v: SsaBasicBlock):
        # 1. Set the preorder number of v to C, and increment C.
        self.preOrder[v] = self.C
        self.C += 1
        # 2. Push v onto S and also onto P.
        S = self.S
        P = self.P
        preOrder = self.preOrder
        done = self.done

        S.append(v)
        P.append(v)

        ignored_nodes = self.ignored_nodes
        ignored_edges = self.ignored_edges
        # 3. For each edge from v to a neighboring vertex w:
        for w in v.successors.iter_blocks():
            # If the preorder number of w has not yet been assigned, recursively search w;
            if w in ignored_nodes or (v, w) in ignored_edges:
                continue
            _preOrder = preOrder.get(w, None)
            if _preOrder is None:
                self._process(w)

            # Otherwise, if w has not yet been assigned to a strongly connected component:
            # Repeatedly pop vertices from P until the top element of P has a preorder number
            # less than or equal to the preorder number of w.
            if w not in done:
                while preOrder[P[-1]] > preOrder[w]:
                    P.pop()

        # 4. If v is the top element of P:
        if v is P[-1]:
            # Pop vertices from S until v has been popped, and assign the popped vertices to a new component.
            component: List[SsaBasicBlock] = []
            first = True
            while first or component[-1] is not v:
                x = S.pop()
                done.add(x)
                component.append(x)
                first = False

            # to have entry point to component on first place
            component.sort(key=lambda x: self.preOrder[x])
            self.components.append(component)
            P.pop()

