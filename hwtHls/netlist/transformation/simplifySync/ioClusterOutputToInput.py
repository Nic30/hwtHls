from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.transformation.simplifySync.orderingUtils import _dependsOnNonOrderingData


def netlistReduceIoClusterCoreOutputToInput(
        dbgTracer: DebugTracer,
        n: HlsNetNodeIoClusterCore,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb:HlsNetlistAnalysisPassReachabilility):
    """
    If output does not have any non ordering dependencies on inputs it means that
    if can be converted to input if ordering connections would not create a cycle.

    :attention: input/output is related to position in IO cluster, it does not correspond
        to a read/write.
    """
    inputs = [dep.obj for dep in n.usedBy[n.inputNodePort.out_i]]
    outputs = [use.obj for use in n.usedBy[n.outputNodePort.out_i]]
    modified = False
    with dbgTracer.scoped(netlistReduceIoClusterCoreOutputToInput, n):
        # while some output port was converted to input
        while True:
            _modified = False
            
            # for each input of an output node
            for o in tuple(outputs):
                o: HlsNetNodeExplicitSync
                assert n is o.dependsOn[o._outputOfCluster.in_i].obj
                # if this an input in any other non trivial cluster, extraction can not be performed
                sucCluster: HlsNetNodeIoClusterCore = o.dependsOn[o._inputOfCluster.in_i].obj
                if sum(len(uses) for uses in sucCluster.usedBy) > 1:
                    continue
                
                if n is sucCluster:
                    continue
                
                # if every data input does not depend on any other input
                if _dependsOnNonOrderingData(o, inputs, reachDb):
                    continue
                # is is reachable from any output this would result in cycle and thus it can not be performed
                anyOtherOutputReachesToO = False
                for _o in outputs:
                    if _o is o:
                        # skip self
                        continue
    
                    if reachDb.doesReachTo(_o, o):
                        anyOtherOutputReachesToO = True
                        break
    
                if anyOtherOutputReachesToO:
                    continue
                
                dbgTracer.log(("convert output to input", o._id, "and merge ", sucCluster._id, " to ", n._id))
                
                # :note: update of ordering should not be required as IoClusterCore does not modify reachability on ordering links
                unlink_hls_nodes(o.dependsOn[o._inputOfCluster.in_i], o._inputOfCluster)
                removed.add(sucCluster)
    
                # sync node o is now input and output of the cluster n
                link_hls_nodes(n.inputNodePort, o._inputOfCluster)

                # update tmp lists
                outputs.remove(o)
                inputs.append(o)
                _modified = True

            if _modified:
                modified = True
            else:
                break

    if modified:
        worklist.extend(inputs)
        worklist.extend(outputs)
        worklist.append(n)

    return modified
