from typing import List, Set, Tuple

from hwtHls.hlsStreamProc.ssa.analysis.sccSearch import DiscoverScc
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock


class PipelineExtractor():
    """
    Cut the circuit graph to individual independent pipelines and mark some edges as backward
    to linearize the circuit for scheduling.


    In this class we solve the feedback arc set problem (which is NP-complete), more info:
    * https://doi.org/10.1016/0020-0190(93)90079-O
    * https://www.mat.univie.ac.at/~neum/ms/minimum_feedback_arc_set.pdf

    """

    def _split_to_pipelines_from_component(self,
                            nodes_to_handle: List[SsaBasicBlock],
                            used_nodes: Set[SsaBasicBlock],
                            backward_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
        if len(nodes_to_handle) == 1:
            # single node pipeline
            for n in nodes_to_handle:
                assert n not in used_nodes, (n, used_nodes)
            used_nodes.update(nodes_to_handle)
            yield nodes_to_handle

        sc = DiscoverScc(nodes_to_handle, used_nodes, backward_edges).discover()
        if len(sc) == len(nodes_to_handle):
            # all nodes as separate component => no cycle, the pipeline we are looking for
            for n in nodes_to_handle:
                assert n not in used_nodes, (n, used_nodes)
            used_nodes.update(nodes_to_handle)
            yield nodes_to_handle
        else:
            yield from self._split_to_pipelines_from_components(sc, used_nodes, backward_edges)

    def _split_to_pipelines_from_components(self,
                            components: List[List[SsaBasicBlock]],
                            used_nodes: Set[SsaBasicBlock],
                            backward_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
        # current_pipeline = []
        for c in components:
            # collect all single node components to a current pipeline
            # plus add entry points to other components
            cycle_entry_node = c[0]
            for pred in cycle_entry_node.predecessors:
                if pred in c:
                    backward_edges.add((pred, cycle_entry_node))
            # current_pipeline.append(node)

        # used_nodes.update(current_pipeline)
        for c in components:
            # build pipeline from rest of the blocks (without the entry point which was added into parent pipeline)
            yield from self._split_to_pipelines_from_component(c, used_nodes, backward_edges)

        # yield current_pipeline

    def collect_pipelines(self, ssa: SsaBasicBlock):
        """
        The pipeline is a DAG of SsaBasicBlocks which should share the synchronization or a single node
        The goal is to extract as long as possible pipelines from ssa graph and detect places
        where these pipelines connect to each other and where some sort of extra synchronization is required.
        """
        used_nodes: Set[SsaBasicBlock] = set()
        components = DiscoverScc((ssa,), (), ()).discover()
        self.backward_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]] = set()
        for component in self._split_to_pipelines_from_components(components, used_nodes, self.backward_edges):
            yield component

