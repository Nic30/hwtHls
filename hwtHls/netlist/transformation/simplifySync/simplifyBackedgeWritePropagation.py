from typing import Set, List

from hwt.hdl.types.bitsVal import BitsVal
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge, HlsNetNodeReadControlBackwardEdge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import _VoidValue, HOrderingVoidT,\
    HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, unlink_hls_nodes, \
    link_hls_nodes
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf


def netlistBackedgeWritePropagation(
        dbgTracer: DebugTracer,
        writeNode: HlsNetNodeWriteBackwardEdge,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        syncDeps: HlsNetlistAnalysisPassSyncDependency) -> bool:
    """
    Propagate a constant write to channel to a value of the read. The channel itself is not removed
    because the presence of data must be somehow notified although the value is known.
    
    :attention: This expect that HlsNetNodeExplicitSync instances are not present in data connections
    """

    d = getConstDriverOf(writeNode._inputs[0])
    if d is None or HdlType_isNonData(d._dtype):
        # in order to apply this input data must be const
        return False
        
    r: HlsNetNodeReadBackwardEdge = writeNode.associated_read
    if r is None:
        return False
    with dbgTracer.scoped(netlistBackedgeWritePropagation, writeNode):
        init = writeNode.channel_init_values
        if init:
            if len(init) == 1:
                # if write value is same as init allow propagation
                if isinstance(d, BitsVal) and len(init[0]) == 1 and int(d) == int(init[0][0]):
                    dbgTracer.log("reduce init values")
                    writeNode.channel_init_values = ((),)
                elif isinstance(d, _VoidValue) and len(init[0]) == 1  and len(init[0]) == 0:
                    # channel_init_values already in correct format
                    pass
                else:
                    return False
            else:
                # there is an init value different than written value, we can not reduce
                return False
    
        # replace data out of read with this const
        # reduce data of this backedge channel to void
        builder: HlsNetlistBuilder = writeNode.netlist.builder
        isControl = isinstance(r, HlsNetNodeReadControlBackwardEdge)
        if isControl:
            assert isinstance(d, _VoidValue) or int(d) == 1, d
        
        # sync which is using the value coming from "r"
        # dependentSync: UniqList[HlsNetNodeIn] = UniqList()
        directDataSuccessors = tuple(syncDeps.getDirectDataSuccessors(r))
        # for user in directDataSuccessors:
        #    if user.__class__ is HlsNetNodeExplicitSync and syncDeps.doesReachTo(r._outputs[0], user._inputs[0]):
        #        dependentSync.append(user._inputs[0])
    
        if isControl:
            dataReplacement = r.getValid()
        else:
            dataReplacement = writeNode.dependsOn[0]
    
        # replace every use of data, except for sync nodes which will be converted to void data type later
        builder.replaceOutput(r._outputs[0], dataReplacement, True)
    
        # if dependentSync:
        #    # propagate constant behind sync
        #    for depSync in dependentSync:
        #        for u in depSync.obj.usedBy[0]:
        #            worklist.append(u.obj)
        #        builder.replaceOutput(
        #            depSync.obj._outputs[0], dataReplacement, True)
        #        depSync.obj._outputs[0]._dtype = HOrderingVoidT
        #        modified = True
    
        # if modified:
        for user in directDataSuccessors:
            worklist.append(user)
        worklist.append(dataReplacement.obj)
        worklist.extend(u.obj for u in dataReplacement.obj.usedBy[dataReplacement.out_i])
        dbgTracer.log(("convert ", r._id, "to void and propagate const"))
        writeNode.dst = Interface_without_registration(writeNode.dst._parent,
                                                        HandshakeSync(),
                                                        writeNode.dst._name)
        r.src = Interface_without_registration(r.src._parent,
                                               HandshakeSync(),
                                               r.src._name)
        r._outputs[0]._dtype = HOrderingVoidT
        worklist.append(writeNode.dependsOn[0].obj)
        worklist.append(r)
        unlink_hls_nodes(writeNode.dependsOn[0], writeNode._inputs[0])
        c = builder.buildConst(HOrderingVoidT.from_py(None))
        link_hls_nodes(c, writeNode._inputs[0])
    
        return True
