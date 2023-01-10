from itertools import chain
from typing import Union, Dict, List, Tuple, Optional, Set, Literal

from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.dagQueries.dagQueries import ReachabilityIndexTOLButterfly
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.observableList import ObservableList, ObservableListRm


class HlsNetlistAnalysisReachability(HlsNetlistAnalysisPass):

    def __init__(self, netlist:"HlsNetlistCtx", removed: Optional[Set[HlsNetNode]]=None):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.reach = ReachabilityIndexTOLButterfly()
        self.directReach = ReachabilityIndexTOLButterfly()
        self.node2index: Dict[Union[HlsNetNodeIn, HlsNetNodeOut, HlsNetNode], int] = {}
        self.index2node: Dict[int, Union[HlsNetNodeIn, HlsNetNodeOut, HlsNetNode]] = {}
        self.removed = removed
        self.nodeCntr = 0
    
    def _beforeNodeAddedListener(self, _, parentList: ObservableList[HlsNetNode], index: Union[slice, int], val: Union[HlsNetNode, Literal[ObservableListRm]]):
        raise NotImplementedError()
    
    def _beforeInputDriveUpdate(self, n: HlsNetNode,
                                parentList: ObservableList[HlsNetNodeOut],
                                index: Union[slice, int],
                                val: Union[HlsNetNodeOut, Literal[ObservableListRm]]):
        reach = self.reach
        n2i = self.node2index
        if val is ObservableListRm or val is None:
            if isinstance(index, int):
                inp = n._inputs[index]
                nodeId = n2i.get(inp, None)
                if nodeId is None:
                    # case where port is disconnected before remove or initialized to unconnected before connection
                    return

                reach.deleteNode(nodeId)
                n2i.pop(inp)
                self.index2node.pop(nodeId)
                
                #print("deleted", inp)
            else:
                raise NotImplementedError(n, index, val)
        else:
            if isinstance(index, int):
                inp = n._inputs[index]
                inpId = n2i.get(inp, None)
                srcI = n2i[val]
                if inpId is None:
                    inpId = self.nodeCntr
                    self.nodeCntr += 1
                    nId = n2i[n]
                    reach.addNode(inpId, (srcI,), (nId,), True)
                    return

                reach.addEdge(srcI, inpId)
            else:
                raise NotImplementedError(n, index, val)

    def setupNetlistListeners(self):
        netlist = self.netlist
        for nodeList in (netlist.inputs, netlist.nodes, netlist.outputs):
            nodeList._setObserver(self._beforeNodeAddedListener, None)
        
        for n in netlist.iterAllNodes():
            if n in self.removed:
                continue
            n.dependsOn._setObserver(self._beforeInputDriveUpdate, n)
    
    def dropNetlistListeners(self):
        netlist = self.netlist
        for nodeList in (netlist.inputs, netlist.nodes, netlist.outputs):
            nodeList._setObserver(None, None)
        
        for n in netlist.iterAllNodes():
            n.dependsOn._setObserver(None, None)
    
    def run(self):
        node2index = self.node2index
        index2node = self.index2node
        removed = self.removed
        reach = self.reach

        nodeCntr = self.nodeCntr
        links: List[Tuple[int, int]] = []
        
        for n in self.netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for io in chain(n._inputs, n._outputs, (n,)):
                node2index[io] = nodeCntr
                index2node[nodeCntr] = io
                nodeCntr += 1
        
        for n in self.netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            nId = node2index[n]
            for i, dep in zip(n._inputs, n.dependsOn):
                iId = node2index[i]
                if dep is not None:
                    links.append((node2index[dep], iId))
                links.append((iId, nId))

            for o in n._outputs:
                # uses added by inputs
                links.append((nId, node2index[o]))
        
        reach.loadGraph(nodeCntr, links)
        reach.computeIndex(True)
        reach.buildBacklink()
        reach.computeOrder()
        self.nodeCntr = nodeCntr
