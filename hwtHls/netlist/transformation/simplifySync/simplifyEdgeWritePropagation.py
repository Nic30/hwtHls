from typing import Set

from hwt.hdl.types.bitsVal import BitsVal
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel, LoopChanelGroup
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import _HVoidValue, HVoidOrdering, \
    HdlType_isNonData, HdlType_isVoid
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, \
    link_hls_nodes, unlink_hls_node_input_if_exists,\
    unlink_hls_node_input_if_exists_with_worklist
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
from hwtHls.netlist.transformation.simplifySync.reduceChannelGroup import netlistTryRemoveChannelGroup


def netlistEdgeWritePropagation(
        dbgTracer: DebugTracer,
        writeNode: HlsNetNodeWriteAnyChannel,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb: HlsNetlistAnalysisPassReachability) -> bool:
    """
    Propagate a constant write to channel to a value of the read. The channel itself is not removed
    because the presence of data must be somehow notified although the value is known.

    :attention: This expect that HlsNetNodeExplicitSync instances are not present in data connections
    """

    d = getConstDriverOf(writeNode._inputs[0])
    if d is None or HdlType_isNonData(d._dtype):
        # in order to apply this input data must be const
        return False

    r: HlsNetNodeReadAnyChannel = writeNode.associatedRead
    if r is None or HdlType_isVoid(r._outputs[0]._dtype):
        return False

    # g = writeNode._loopChannelGroup
    # if g is not None and g.getChannelWhichIsUsedToImplementControl() is writeNode:
    #    # can not remove because it has control flow purpose
    #    return False

    with dbgTracer.scoped(netlistEdgeWritePropagation, writeNode):
        init = writeNode.channelInitValues
        if init:
            if len(init) == 1:
                # if write value is same as init allow propagation
                if isinstance(d, BitsVal) and len(init[0]) == 1 and int(d) == int(init[0][0]):
                    dbgTracer.log("reduce init values")
                    writeNode.channelInitValues = ((),)
                elif isinstance(d, _HVoidValue) and len(init[0]) == 1  and len(init[0]) == 0:
                    # channelInitValues already in correct format
                    pass
                else:
                    return False
            else:
                # there is an init value different than written value, we can not reduce
                return False

        # replace data out of read with this const
        # reduce data of this backedge channel to void
        builder: HlsNetlistBuilder = writeNode.netlist.builder

        # sync which is using the value coming from "r"
        # dependentSync: UniqList[HlsNetNodeIn] = UniqList()
        directDataSuccessors = tuple(reachDb.getDirectDataSuccessors(r))
        # for user in directDataSuccessors:
        #    if user.__class__ is HlsNetNodeExplicitSync and reachDb.doesReachTo(r._outputs[0], user._inputs[0]):
        #        dependentSync.append(user._inputs[0])

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
        #        depSync.obj._outputs[0]._dtype = HVoidOrdering
        #        modified = True

        # if modified:
        for user in directDataSuccessors:
            worklist.append(user)

        worklist.append(dataReplacement.obj)
        worklist.extend(u.obj for u in dataReplacement.obj.usedBy[dataReplacement.out_i])
        dbgTracer.log(("convert ", r._id, "to void and propagate const"))
        origRSrc = r.src
        if r.src is not None:
            assert r.src._ctx is None, ("Interface must not be instantiated yet", r)
            r.src = HandshakeSync()

        if writeNode.dst is not None:
            assert writeNode.dst._ctx is None, (
                "Interface must not be instantiated yet", r)
            if writeNode.dst is origRSrc:
                writeNode.dst = r.src
            else:
                writeNode.dst = HandshakeSync()

        r._outputs[0]._dtype = HVoidOrdering
        worklist.append(writeNode.dependsOn[0].obj)
        worklist.append(r)
        unlink_hls_nodes(writeNode.dependsOn[0], writeNode._inputs[0])
        c = builder.buildConst(HVoidOrdering.from_py(None))
        link_hls_nodes(c, writeNode._inputs[0])

        return True


def netlistEdgeWriteVoidWithoudDeps(
        dbgTracer: DebugTracer,
        writeNode: HlsNetNodeWriteAnyChannel,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode]) -> bool:
    if len(writeNode._inputs) != 1:
        return False
    if isinstance(writeNode, HlsNetNodeWriteBackedge) and writeNode.channelInitValues:
        return False
    d = getConstDriverOf(writeNode._inputs[0])
    if d is None:
        # driver is not constant, do not try to optimize
        return None
    if not HdlType_isVoid(d._dtype):
        # driver is not of void type, wait on  :func:`~.netlistEdgeWritePropagation`
        return False

    g = writeNode._loopChannelGroup
    isControlOfG = g is not None and g.getChannelWhichIsUsedToImplementControl() is writeNode
    if isControlOfG and not netlistTryRemoveChannelGroup(g, worklist):
        # can not remove because it has control flow purpose
        return False

    g: LoopChanelGroup
    with dbgTracer.scoped(netlistEdgeWriteVoidWithoudDeps, writeNode):
        builder: HlsNetlistBuilder = writeNode.netlist.builder
        netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, writeNode, worklist)

        dConst = writeNode.dependsOn[0]
        worklist.append(dConst.obj)
        unlink_hls_nodes(dConst, writeNode._inputs[0])
        readNode = writeNode.associatedRead
        if readNode.usedBy[0]:
            dOut = readNode._output[0]
            assert HdlType_isVoid(dOut._dtype), (dOut, dOut._dtype)
            builder.replaceOutput(readNode._output, dConst, True)

        for valid in (readNode._valid, readNode._validNB):
            if valid is not None and readNode.usedBy[valid.out_i]:
                builder.replaceOutput(valid, builder.buildConstBit(1), True)
        if readNode._rawValue is not None and readNode.usedBy[readNode._rawValue]:
            raise NotImplementedError()
        dVoid = readNode._dataVoidOut
        if dVoid is not None and readNode.usedBy[dVoid.out_i]:
            dVoidReplace = builder.buildConstPy(dVoid._dtype, None)
            builder.replaceOutput(dVoid, dVoidReplace, True)
            worklist.append(dVoidReplace.obj)

        netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, readNode, worklist)
        unlink_hls_node_input_if_exists_with_worklist(readNode.skipWhen, worklist, False)
        unlink_hls_node_input_if_exists_with_worklist(readNode.extraCond, worklist, False)
        removed.add(writeNode)
        removed.add(readNode)
        if g is not None and not isControlOfG:
            g.members.remove(writeNode)

