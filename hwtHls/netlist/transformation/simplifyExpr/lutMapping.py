from hwtHls.netlist.nodes.node import HlsNetNode
from collections import deque
import math
from itertools import combinations

"""
Problem description:
There is given DAG, with max time for each output and clock window period. The task is to assign as late as possible (ALAP) time to each node
but satisfy constraints for a given delay for each nodes. The node delay causes node to overlap to previous clock window,
the node must be moved to previous cycle. The delay of node is computed using resolveSubnodeRealization function.
However this function requires the total number of unique inputs of the subgraph scheduled in this clock window.

The problem is is that we need to track number of unique primary inputs for each output.
The number of nodes can be potentially large (1e4+) thus we can not recursively collect the set of inputs in DFS manner.
Ant there is a problem that each output may be used anywhere in other primary output cones that implies
that for each node there are scheduling constraints derived from:
 * constraints of primary in/out ports
 * the number or input of currently selected tree
 * the timing constraints from scheduling for a different primary output

https://github.com/YosysHQ/yosys/blob/main/passes/techmap/flowmap.cc
https://people.eecs.berkeley.edu/~alanmi/publications/2011/iccad11_sop.pdf
https://ethz.ch/content/dam/ethz/special-interest/itet/efcl-dam/documents/Introduction%20to%20ABC.pdf
https://yosyshq.readthedocs.io/projects/yosys/en/stable/cmd/index_passes_techmap.html#flowmap-pack-luts-with-flowmap
https://limsk.ece.gatech.edu/course/ece6133/papers/flowmap.pdf
https://winternan.github.io/files/Lecture/07_Synthesis%20II/flowmap.pdf
https://github.com/yunchenlo/FlowMap_Tech_Mapping
https://gist.github.com/Ravenslofty/277fde6b43966f0a83b66c2c74efce92
AGDmap https://github.com/iahks/ICCAD2024_A
"""


class Lut:
    """
    :ivar input_nodes: nodes which are outside of this lut but their output is connected to this lut input
    """

    def __init__(self, lut_id: int,
                 outputs: list[HlsNetNode],
                 input_nodes: list[HlsNetNode]):
        self.lut_id = lut_id
        self.outputs = outputs
        self.input_nodes = input_nodes

    def __repr__(self):
        return f"{self.__class__.__name__}({self.lut_id}, {[n._id for n in self.input_nodes]}, {[n._id for n in self.outputs]})"


def flowmap(nodes: list[HlsNetNode], K: int=6) -> list[Lut]:
    """
    FlowMap for HlsNetNode DAG. Returns LUT mapping.
    :param K: number of inputs of LUT
    """
    # Topological order (PIs first)
    topo_order = topological_sort_in_first(nodes)
    rev_topo = topo_order[::-1]  # POs first for labeling

    # Phase 1: Labeling - compute min depth labels
    labels: dict[HlsNetNode, int] = {node: 0 for node in nodes}
    best_cuts = {}  # node -> (cut_inputs_indices, volume)

    for t in rev_topo:
        cut_depth, cut_inputs, volume = compute_k_feasible_cut(
            t, K, labels)
        labels[t] = cut_depth
        best_cuts[t] = (cut_inputs, volume)

    # Phase 2: Cut Selection
    lut_mapping = []
    covered_nodes = set()

    for t in rev_topo:
        if t in covered_nodes:
            continue

        cut_inputs, _ = best_cuts[t]

        assert len(cut_inputs) <= K
        lut = Lut(
            lut_id=len(lut_mapping),
            outputs=[t],
            input_nodes=cut_inputs
        )
        lut_mapping.append(lut)
        covered_nodes.add(t)
        covered_nodes.update(cut_inputs)

    return lut_mapping


def topological_sort_in_first(nodes: list[HlsNetNode]) -> list[HlsNetNode]:
    """Topo sort using indegrees from inputs"""
    indegree: dict[HlsNetNode, int] = {node: len(node.inputs) for node in nodes}
    # init search queue with primary inputs, sorted the earliest first
    queue: deque[HlsNetNode] = deque(sorted([n for n in nodes if indegree[n] == 0],
                                            key=lambda n: n.scheduledZero))
    order: list[HlsNetNode] = []

    while queue:
        # pop node which is known to have all inputs resolved
        node: HlsNetNode = queue.popleft()
        order.append(node)
        for fanout_node in node.iterOutUserNodes():
            indegree[fanout_node] -= 1
            if indegree[fanout_node] == 0:
                # once all inputs have been seen
                queue.append(fanout_node)
    return order


def topological_sort_out_first(nodes: list[HlsNetNode]) -> list[HlsNetNode]:
    """Topo sort using indegrees from inputs"""
    outdegree: dict[HlsNetNode, int] = {node: sum(len(uses) for uses in node.usedBy) for node in nodes}
    # init search queue with primary outputs, sorted the latest first
    queue: deque[HlsNetNode] = deque(sorted([n for n in nodes if outdegree[n] == 0],
                                            key=lambda n:-n.scheduledZero))
    order: list[HlsNetNode] = []

    while queue:
        # pop node which is known to have all inputs resolved
        node: HlsNetNode = queue.popleft()
        order.append(node)
        for fanin_node in node.iterInDepNodes():
            outdegree[fanin_node] -= 1
            if outdegree[fanin_node] == 0:
                # once all out users have been seen
                queue.append(fanin_node)
    return order


def compute_k_feasible_cut(t: HlsNetNode, K: int,
                               labels: dict[HlsNetNode, int]) -> tuple[int, list[HlsNetNode], int]:
    """
    Simplified K-feasible cut using dynamic programming.
    Returns (min_depth, input_node_indices, volume)
    """
    cone_inputs = get_transitive_fanin(t)

    # Try all subsets of inputs up to K
    min_depth = math.inf
    best_cut: list[HlsNetNode] = []
    max_volume = 0

    for subset_size in range(1, min(K + 1, len(cone_inputs) + 1)):
        for cut_subset in combinations(cone_inputs, subset_size):
            depth = max(labels.get(inp, 0) for inp in cut_subset)
            volume = len(cut_subset)

            if depth < min_depth or (depth == min_depth and volume > max_volume):
                min_depth = depth
                best_cut = list(cut_subset)
                max_volume = volume

    return min_depth, best_cut, max_volume


def get_transitive_fanin(node: HlsNetNode) -> set[HlsNetNode]:
    """Get all transitive fanin nodes using DFS with memoization"""
    visited = set()
    stack = [node]

    while stack:
        curr: HlsNetNode = stack.pop()
        if curr in visited:
            continue
        visited.add(curr)
        for inp in curr.iterInputDepNodes():
            inp: HlsNetNode
            stack.append(inp)

    visited.discard(node)  # Exclude self
    return visited

