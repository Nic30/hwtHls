from typing import Union, Set, List, Tuple

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeIoDict, \
    ArchSyncNeighborDict
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.architecture.analysis.syncNodeGraph import ArchSyncSuccDiGraphDict
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, MapAbc_Obj_tToSetOfAbc_Obj_t, \
    MapAbc_Obj_tToAbc_Obj_t, Abc_Obj_t
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import beginOfClk


def hasNotAnySyncOrFlag(n: Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel]):
    return not n._rtlUseValid and not n._rtlUseReady and n.extraCond is None and n.skipWhen is None


def _moveNonSccChannelPortsToIO(neighbors: ArchSyncNeighborDict,
                                successors: ArchSyncSuccDiGraphDict,
                                scc: SetList[ArchSyncNodeTy],
                                nodeIo: ArchSyncNodeIoDict):
    """
    Channel read/write which is not part of handshake SCC is a normal IO and will not be rewritten.
    Thus we move it to nodeIo as normal IO.
    """
    for n in scc:
        n: ArchSyncNodeTy
        inputList, outputList = nodeIo[n]
        _neighbors = neighbors.get(n, None)
        if not _neighbors:
            continue
        toRm = set()
        # move suc channel to nodeIo if the suc is not in the same scc
        for suc , sucChannelIo in _neighbors.items():
            if suc not in scc:
                toRm.add(suc)
                for ch in sucChannelIo:
                    assert ch in n[0].subNodes, ch
                    if isinstance(ch, HlsNetNodeWrite):
                        outputList.append(ch)
                    else:
                        assert isinstance(ch, HlsNetNodeRead), ch
                        inputList.append(ch)

        _successors = successors.get(n, None)
        if not _successors:
            continue
        # rm suc which channels were converted to IO
        for suc in toRm:
            _successors.pop(suc, None)

# def collectHlsNetlistExprTreeInputsSingleHierarchy(out: HlsNetNodeOut, exclude: HlsNetNodeOut):
#    seen = set()
#    inputs = SetList()
#    toSearch = [out]
#    while toSearch:
#        o = toSearch.pop()
#        if o is exclude or o in seen:
#            continue
#
#        seen.add(o)
#        if isinstance(o.obj, (HlsNetNodeOperator, HlsNetNodeConst)):
#            for dep in o.obj.dependsOn:
#                toSearch.append(dep)
#        else:
#            inputs.append(o)
#
#    return inputs
#


def ioDataIsMixedInControlInThisClk(ioNode: HlsNetNodeExplicitSync, ackPort: HlsNetNodeOut):
    """
    For nodes which 
    """

    seen: Set[HlsNetNode] = set()
    clkPeriod = ioNode.netlist.normalizedClkPeriod
    timeLimit = beginOfClk(ioNode.scheduledZero, clkPeriod)
    toSearch: List[Tuple[HlsNetNode, SchedTime, SchedTime]] = [(ioNode, timeLimit, timeLimit + clkPeriod), ]  # stack of nodes to search in DFS
    while toSearch:
        # def -> use DFS for extraCond, skipWhen, _forceEnPort
        n, timeLimitBegin, timeLimitEnd = toSearch.pop()
        if n in seen:
            continue
        else:
            seen.add(n)

        for outPort, uses in zip(n._outputs, n.usedBy):
            if outPort is ackPort or HdlType_isNonData(outPort._dtype):
                continue

            for u in uses:
                u: HlsNetNodeIn
                uObj: HlsNetNode = u.obj
                if uObj.scheduledIn[u.in_i] > timeLimitEnd:
                    continue
                if isinstance(uObj, HlsNetNodeExplicitSync):
                    if u in (uObj.extraCond, uObj.skipWhen, uObj._forceEnPort):
                        return True

                toSearch.append((uObj, timeLimitBegin, timeLimitEnd))

        if isinstance(n, HlsNetNodeAggregatePortOut):
            for u in uses:
                u: HlsNetNodeIn
                uObj: HlsNetNodeAggregate = u.obj
                assert isinstance(uObj, HlsNetNodeAggregate)
                uTime = uObj.scheduledIn[u.in_i]
                # Connections between arch elements are allowed to cross clock boundaries
                # freely without any register
                # For this type of connections time boundaries must be update to clock window where
                # the value arrived.
                if uTime < timeLimitBegin or uTime >= timeLimitEnd:
                    _timeLimitBegin = beginOfClk(uTime, clkPeriod)
                    _timeLimitEnd = _timeLimitBegin + clkPeriod
                else:
                    _timeLimitBegin = timeLimitBegin
                    _timeLimitEnd = timeLimitEnd

                toSearch.append((uObj._inputsInside[u.in_i], _timeLimitBegin, _timeLimitEnd))

        elif isinstance(n, HlsNetNodeWriteBackedge) and n.associatedRead is not None and n._getBufferCapacity() == 0:
            # if channel has 0 capacity and is crossing clock window boundaries the time must be updated
            # when following value to read port of channel
            r = n.associatedRead
            uTime = r.scheduledZero
            if uTime < timeLimitBegin or uTime >= timeLimitEnd:
                _timeLimitBegin = beginOfClk(uTime, clkPeriod)
                _timeLimitEnd = _timeLimitBegin + clkPeriod
            else:
                _timeLimitBegin = timeLimitBegin
                _timeLimitEnd = timeLimitEnd

            toSearch.append((r, _timeLimitBegin, _timeLimitEnd))

    return False


def updateAbcObjRefsForNewNet(_impliedValues: MapAbc_Obj_tToSetOfAbc_Obj_t,
                              _inToOutConnections: MapAbc_Obj_tToAbc_Obj_t,
                              _outputsFromAbcNet: Set[Abc_Obj_t],
                              net: Abc_Ntk_t):
    """
    After any ABC optimization the net is a new net and object are new as well,
    this functions lookups new objects form old objects by its name
    """
    inputs = {}
    outputs = {}
    for pi in net.IterPi():
        name = pi.Name()
        assert name not in inputs, ("port name must be unique", name, inputs[name], pi)
        inputs[name] = pi

    for po in net.IterPo():
        name = po.Name()
        assert name not in outputs, ("port name must be unique", name, outputs[name], po)
        outputs[name] = po

    # after net was optimized it is a new net and port object are new objects
    # that is why the argument collections for Abc_NtkExpandExternalCombLoops must be also updated

    impliedValues = MapAbc_Obj_tToSetOfAbc_Obj_t()
    for k, values in _impliedValues.items():
        impliedValues[outputs[k.Name()]] = {inputs[v.Name()] for v in values}

    inToOutConnections = MapAbc_Obj_tToAbc_Obj_t()
    for k, v in _inToOutConnections.items():
        inToOutConnections[inputs[k.Name()]] = outputs[v.Name()]
    outputsFromAbcNet = set(outputs[o.Name()] for o in _outputsFromAbcNet)

    return impliedValues, inToOutConnections, outputsFromAbcNet

