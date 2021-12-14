from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from networkx.classes.function import selfloop_edges
from typing import List, Set, Tuple, Dict

from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from ipCorePackager.constants import DIRECTION

# https://github.com/baharev/sdopt-tearing/blob/master/heap_md.py
# https://github.com/zhenv5/breaking_cycles_in_noisy_hierarchies
Node = int


def rm_non_sccs(g: DiGraph):
    sccs = [c for c in strongly_connected_components(g) if len(c) > 1]
    sccs_nodes = set()
    for c in sccs:
        sccs_nodes.update(c)

    for n in tuple(g.nodes()):
        if n not in sccs_nodes:
            g.remove_node(n)  # edges removed automatically
    return sccs, sccs_nodes


def get_nodes_degree_dict(g: DiGraph, nodes: List[Node]) -> Dict[Node, Tuple[float, DIRECTION]]:
    in_degrees = g.in_degree(nodes)
    out_degrees = g.out_degree(nodes)
    degree_dict = {}
    for node in nodes:
        in_d = in_degrees[node]
        out_d = out_degrees[node]
        if in_d >= out_d:
            value = in_d / out_d
            f = DIRECTION.IN
        else:
            value = out_d / in_d
            f = DIRECTION.OUT
        degree_dict[node] = (value, f)

    return degree_dict


def greedy_local_heuristic(g: DiGraph, sccs: List[Set[Node]], degree_dict: Dict[int, int], edges_to_be_removed):
    while sccs:
        scc = sccs.pop()

        max_value, max_node = max(((degree_dict[node][0], node)
                                    for node in scc),
                                    key=lambda x: x[0])

        # degrees = [(node,degree_dict[node]) for node in list(graph.nodes())]
        # max_node,max_value = max(degrees,key = lambda x: x[1][0])
        if max_value == DIRECTION.IN:
            # indegree > outdegree, remove out-edges
            edges = ((max_node, o) for o in g.succ[max_node])
        else:
            # outdegree > indegree, remove in-edges
            edges = ((i, max_node) for i in g.pred[max_node])
        edges_to_be_removed.extend(edges)

        g.remove_edges_from(edges_to_be_removed)
        sccs.extend(c for c in strongly_connected_components(g) if len(c) > 1)


def remove_cycle_edges_by_mfas(g: DiGraph):
    backedges = list(selfloop_edges(g))
    g.remove_edges_from(backedges)
    sccs, sccs_nodes = rm_non_sccs(g)
    # scc_nodes, _, _, _ = scc_nodes_edges(g)
    degree_dict = get_nodes_degree_dict(g, sccs_nodes)
    # import timeit
    # t1 = timeit.default_timer()
    greedy_local_heuristic(g, sccs, degree_dict, backedges)
    # t2 = timeit.default_timer()
    # print("mfas time usage: %0.4f s" % (t2 - t1))
    # edges_to_be_removed = list(set(edges_to_be_removed))
    # g.remove_edges_from(edges_to_be_removed)
    # edges_to_be_removed.extend(self_loops)
    # edges_to_be_removed_file = graph_file[:len(graph_file) - 6] + "_removed_by_mfas.edges"
    # write_pairs_to_file(edges_to_be_removed, edges_to_be_removed_file)
    return backedges


class PipelineExtractor():
    """
    Cut the circuit graph to individual independent pipelines and mark some edges as backward
    to linearize the circuit for scheduling.

    :note: The edge is backward

    In this class we solve the feedback arc set problem (which is NP-complete), more info:
    * https://doi.org/10.1016/0020-0190(93)90079-O
    * https://www.mat.univie.ac.at/~neum/ms/minimum_feedback_arc_set.pdf

    """

    # def _split_to_pipelines_from_component(self,
    #                        nodes_to_handle: List[SsaBasicBlock],
    #                        used_nodes: Set[SsaBasicBlock],
    #                        backward_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
    #    if len(nodes_to_handle) == 1:
    #        # single node pipeline
    #        for n in nodes_to_handle:
    #            assert n not in used_nodes, (n, used_nodes)
    #        used_nodes.update(nodes_to_handle)
    #        yield nodes_to_handle
    #
    #    sc = DiscoverScc(nodes_to_handle, used_nodes, backward_edges).discover()
    #    if len(sc) == len(nodes_to_handle):
    #        # all nodes as separate component => no cycle, the pipeline we are looking for
    #        for n in nodes_to_handle:
    #            assert n not in used_nodes, (n, used_nodes)
    #        used_nodes.update(nodes_to_handle)
    #        yield nodes_to_handle
    #    else:
    #        yield from self._split_to_pipelines_from_components(sc, used_nodes, backward_edges)

    # def _split_to_pipelines_from_components(self,
    #                        components: List[List[SsaBasicBlock]],
    #                        used_nodes: Set[SsaBasicBlock],
    #                        backward_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
    #    # current_pipeline = []
    #    for c in components:
    #        # collect all single node components to a current pipeline
    #        # plus add entry points to other components
    #        for i0, c0 in enumerate(c):
    #            c0:SsaBasicBlock
    #
    #            for pred in c0.successors.iter_blocks():
    #                try:
    #                    i1 = c.index(pred)
    #                except ValueError:
    #                    i1 = math.inf
    #                if i1 <= i0:
    #                    backward_edges.add((pred, c0))
    #            # current_pipeline.append(node)
    #
    #    # used_nodes.update(current_pipeline)
    #    for c in components:
    #        # build pipeline from rest of the blocks (without the entry point which was added into parent pipeline)
    #        yield from self._split_to_pipelines_from_component(c, used_nodes, backward_edges)
    #
    #    # yield current_pipeline

    def collect_pipelines(self, ssa: SsaBasicBlock):
        """
        The pipeline is a DAG of SsaBasicBlocks which should share the synchronization or a single node
        The goal is to extract as long as possible pipelines from ssa graph and detect places
        where these pipelines connect to each other and where some sort of extra synchronization is required.
        """
        # used_nodes: Set[SsaBasicBlock] = set()
        allBlocksSet: Set[SsaBasicBlock] = set()
        blocks: List[SsaBasicBlock] = list(collect_all_blocks(ssa, allBlocksSet))
        block_to_id = {b: i for i, b in enumerate(blocks)}
        dg = DiGraph()
        for b0_i, b0 in enumerate(blocks):
            b0: SsaBasicBlock
            for b1 in b0.successors.iter_blocks():
                b1_i = block_to_id[b1]
                dg.add_edge(b0_i, b1_i)

        back_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]] = set()
        for b0_i, b1_i in set(remove_cycle_edges_by_mfas(dg)):
            back_edges.add((blocks[b0_i], blocks[b1_i]))
        # components = DiscoverScc((ssa,), (), ()).discover()
        self.backward_edges = back_edges
        return blocks
        # for component in self._split_to_pipelines_from_components(components, used_nodes, self.backward_edges):
        #    yield component

