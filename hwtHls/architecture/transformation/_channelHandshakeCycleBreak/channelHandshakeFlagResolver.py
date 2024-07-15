from copy import copy
from itertools import chain
from typing import List, Dict, Tuple, Union, Optional, Set

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeIoDict, \
    ArchSyncChannelToParentDict
from hwtHls.architecture.analysis.handshakeSCCs import TimeOffsetOrderedIoItem, \
    ReadOrWriteType, AllIOsOfSyncNode
from hwtHls.architecture.analysis.syncNodeGraph import ArchSyncNeighborDict, \
    ArchSyncNodeTy_stringFormat_short
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchSyncNodeTy, \
    ArchElementTermPropagationCtx
from hwtHls.netlist.abc.abcCpp import Abc_Frame_t, Abc_Ntk_t, Abc_NtkType_t, \
    Abc_NtkFunc_t, Abc_Aig_t, Abc_Obj_t, Abc_NtkExpandExternalCombLoops, MapAbc_Obj_tToAbc_Obj_t, \
    Io_FileType_t
from hwtHls.netlist.abc.hlsNetlistToAbcAig import HlsNetlistToAbcAig
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElementNoSync import ArchElementNoSync
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import beginOfClk, beginOfNextClk, \
    indexOfClkPeriod
from ipCorePackager.constants import DIRECTION
from pyMathBitPrecise.bit_utils import ValidityError


# def _collectHlsNetNodeUseToDefUntilTime(i: HlsNetNodeIn, res: SetList[HlsNetNode],
#                                        beginTime: SchedTime, endTime: SchedTime):
#    obj = i.obj
#    d = obj.dependsOn[i.in_i]
#    depObj: HlsNetNode = d.obj
#    if depObj in res or depObj.scheduledOut[d.out_i] < beginTime:
#        return
#    for depIn, depInTime in zip(depObj._inputs, depObj.scheduledIn):
#        if depInTime < beginTime:
#            continue
#        elif depInTime >= endTime:
#            continue
#        _collectHlsNetNodeUseToDefUntilTime(depIn, res, beginTime, endTime)
#
#
# def _collectHlsNetNodeUseToDefUntilTime_forInputList(ioInputFlags: List[HlsNetNodeIn]):
#    nodesDrivingSpecifiedInputs: SetList[HlsNetNode] = SetList()
#    netlist = ioInputFlags[0].obj.netlist
#    clkPeriod = netlist.normalizedClkPeriod
#    for i in ioInputFlags:
#        inTime = i.obj.scheduledIn[i.in_i]
#        _collectHlsNetNodeUseToDefUntilTime(i, nodesDrivingSpecifiedInputs,
#                                            beginOfClk(inTime, clkPeriod),
#                                            beginOfNextClk(inTime, clkPeriod))
#
#    return nodesDrivingSpecifiedInputs
def _collectHlsNtNodeDefToUseUntilTimeNotCrossingChannelControl(o: HlsNetNodeOut, res: SetList[HlsNetNode],
                                       beginTime: SchedTime, endTime: SchedTime,
                                       channelControls: SetList[HlsNetNodeIn]):
    for use in o.obj.usedBy[o.out_i]:
        if use in channelControls:
            continue
        useObj: HlsNetNode = use.obj
        if useObj in res:
            continue
        useTime = useObj.scheduledIn[use.in_i]
        if useTime < beginTime or useTime >= endTime:
            continue

        res.append(useObj)
        for useOutPort, useOutTime in zip(useObj._outputs, useObj.scheduledOut):
            if useOutTime < beginTime or useOutTime >= endTime:
                continue
            _collectHlsNtNodeDefToUseUntilTimeNotCrossingChannelControl(useOutPort, res, beginTime, endTime, channelControls)


def _collectHlsNtNodeDefToUseUntilTimeNotCrossingChannelControlForMany(
        outputs: List[Tuple[HlsNetNodeOut, int, Abc_Obj_t]],
        channelControls: SetList[HlsNetNodeIn]) -> SetList[HlsNetNode]:
    res: SetList[HlsNetNode] = SetList()

    netlist = outputs[0][0].obj.netlist
    clkPeriod = netlist.normalizedClkPeriod

    for o, _, _ in outputs:
        outTime = o.obj.scheduledOut[o.out_i]
        _collectHlsNtNodeDefToUseUntilTimeNotCrossingChannelControl(
            o, res,
            beginOfClk(outTime, clkPeriod),
            beginOfNextClk(outTime, clkPeriod),
            channelControls)
    return res


class ChannelHandshakeFlagResolver(HlsNetlistToAbcAig):
    """
    This class take handshake SCC as an input and builds a handshake synchronization logic in ABC
    then removes combinational loops then updates all synchronization flags to be remove cycles.
    

    All channel IO which are not part of SCC are treated as a regular IO
    Channel IO in SCC will have :code:`_rtlUseReady=_rtlUseValid=False` and all flags updated.

    Input flags (extraCond, skipWhen, mayFlush, forceWrite) will have input drive replaced
    with an enriched variant generated from handshake cycle breaking.

    Output flags uses (write.ready, read.valid) will also be replaced with enriched variant.

    Output flags driven from internal state of the buffer (isFlushed, full) will remain
    untouched.

    Ready/valid used in internal signaling is computed as:
    .. code:: Python
        
        write.ready = read.ready | ~write.full
        write.valid = parentNode.ack & write.extraCond & ~write.skipWhen

        read.ready = parentNode.ack & read.extraCond & ~read.skipWhen
        read.valid = write.valid | (~write.empty if write.capacity > 0 else write.mayFlush)

    Sync logic collection:
    * for io node collect input flag expressions (extraCond, skipWhen, mayFlush, forceWrite)
      * consume expression until some non ABC compatible node is reached or clock boundary is reached.
      * :note: 1b "and", "or", "xor", "==", "!=", "mux" are abc compatible
      * :note: search must stop at clock window boundary because logic is driven from register
        on that boundary, before that boundary it is a different value.
    * add all ready, valid, readyNB, validNB if it is not guaranteed to be driven from register
    * collect all user abc compatible nodes for every expression and follow expression in both sides
      to collect whole cluster of ABC compatible nodes
    * build expressions for:
      * enable of sync nodes
      * enable of io node
      * mayFlush, forceWrite of io nodes if required
    
    :note: extraCond is altered to emulate write.ready and read.valid behavior after :code:`_rtlUseReady=_rtlUseValid=False`
        which causes state of the other channel port to be ignored.
    :attention: All skipWhen are removed, and all io nodes (except for write node implementing nodes stall)
        are converted into non-blocking. This is because extra cond is already enriched with
        ack of all other related nodes. And when resolving sync we do not need ready/valid
        of this node, because it is already in extraCond of others.
    :note: When translating from HlsNetlist the clock window must be taken in account because
        same HlsNetNodeOut within different clock window is likely a different register.
    
    :ivar outputsFromAbcNet: a subset of abc primary outputs which are true
        outputs of optimized network and not just some tmp output
    """

    def __init__(self, clkPeriod: SchedTime):
        HlsNetlistToAbcAig.__init__(self)
        # flags which are primary inputs to handshake logic, e.g. buffer.full
        self.prinaryInputs: SetList[Tuple[HlsNetNodeOut, int]] = SetList()
        self.clkPeriod = clkPeriod
        self.net: Optional[Abc_Ntk_t] = None
        self.nodesDrivenFromIoState: SetList[HlsNetNode] = SetList()
        # :note: we can not store Abc_Obj_t because the object could be discarded after first operation with network
        #        we can not use index because IO may reorder and we can not use Id because it also changes
        self.ioMap: Dict[str, Union[Tuple[DIRECTION, ArchSyncNodeTy], HlsNetNodeOut]] = {}
        self.inToOutConnections = MapAbc_Obj_tToAbc_Obj_t()
        self.outputsFromAbcNet: Set[Abc_Obj_t] = set()

    def _translate(self, aig: Abc_Aig_t, item: Union[Tuple[HlsNetNodeOut, int],
                                                     ArchSyncNodeTy]):
        try:
            return self.translationCache[item]
        except KeyError:
            pass

        o, clkI = item
        d = o.obj
        # if item definition is coming from previous clock cycle
        # or driving node was not marked as handshake logic, this will be new primary input
        defTime = d.scheduledOut[o.out_i]
        beginOfClkWindow = clkI * self.clkPeriod
        if defTime < beginOfClkWindow or d not in self.nodesDrivenFromIoState:
            return self._addPrimaryInput(o, clkI)
        else:
            # else this is some logic in this clock window

            if isinstance(d, HlsNetNodeConst):
                try:
                    v = int(d.val)
                except ValidityError:
                    v = 0
                if v == 1:
                    res = self.c1
                else:
                    res = aig.Not(self.c1)

            else:
                # [todo] check if this operator is supported or we should make this a primary input
                assert isinstance(d, HlsNetNodeOperator), (d, o)
                d: HlsNetNodeOperator
                op = d.operator
                inCnt = len(d._inputs)
                if inCnt == 1:
                    assert d.operator == HwtOps.NOT, d
                    res = aig.Not(self._translate(aig, (d.dependsOn[0], clkI)))

                elif inCnt == 2:
                    lhs, rhs = (self._translate(aig, (i, clkI)) for i in d.dependsOn)
                    if op == HwtOps.AND:
                        res = aig.And(lhs, rhs)
                    elif op == HwtOps.OR:
                        res = aig.Or(lhs, rhs)
                    elif op == HwtOps.XOR:
                        res = aig.Xor(lhs, rhs)
                    elif op == HwtOps.EQ:
                        res = aig.Eq(lhs, rhs)
                    elif op == HwtOps.NE:
                        res = aig.Ne(lhs, rhs)
                    else:
                        raise NotImplementedError(d)

                elif inCnt >= 3:
                    assert d.operator == HwtOps.TERNARY
                    if inCnt == 3:
                        o0, c, o1 = (self._translate(aig, (i, clkI)) for i in d.dependsOn)
                        res = aig.Mux(c, o0, o1)  # ABC notation is in in this order, p1, p0 means if c=1 or c=0
                    else:
                        assert inCnt % 2 == 1, d
                        prevVal = None
                        # mux must be build from end so first condition ends up at the top of expression (bottom of code)
                        for v, c in reversed(tuple(d._iterValueConditionDriverPairs())):
                            v = self._translate(aig, (v, clkI))
                            if c is not None:
                                c = self._translate(aig, (c, clkI))

                            if prevVal is None:
                                assert c is None
                                prevVal = v
                            else:
                                prevVal = aig.Mux(c, v, prevVal)

                        res = prevVal
                else:
                    raise NotImplementedError(d)

        assert item not in self.translationCache, o
        self.translationCache[item] = res
        return res

    @staticmethod
    def _buildAndOptional(aig: Abc_Aig_t, a:Optional[Abc_Obj_t], b:Optional[Abc_Obj_t]) -> Optional[Abc_Obj_t]:
        if a is None:
            return b
        if b is None:
            return a
        return aig.And(a, b)

    def _translateDriveOfOptionalIn(self, aig: Abc_Aig_t, clkI: int, inPort: Optional[HlsNetNodeIn]):
        if inPort is None:
            return None
        return self._translate(aig, (inPort.obj.dependsOn[inPort.in_i], clkI))

    def _translateIOAckExpr(self,
                            aig: Abc_Aig_t,
                            clkI: int,
                            io: Union[HlsNetNodeRead, HlsNetNodeWrite],
                            rltAck: Optional[Abc_Obj_t]):
        ec = self._translateDriveOfOptionalIn(aig, clkI, io.extraCond)
        sw = self._translateDriveOfOptionalIn(aig, clkI, io.skipWhen)

        ack = self._buildAndOptional(aig, rltAck, ec)
        if ack is not None and sw is not None:
            ack = aig.Or(ack, sw)
        return ack

    def _translateIOEnExpr(self, aig: Abc_Aig_t, parentSyncNode: ArchSyncNodeTy, ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite]):
        clkI = parentSyncNode[1]
        # :note: this is en flag which will be expanded differently for each sync node
        #  the expansion puts en of current syncNode=1 and
        en = self.translationCache[parentSyncNode]
        if isinstance(ioNode, HlsNetNodeWrite) and ioNode._isFlushable:
            mayFlush = ioNode.dependsOn[ioNode._mayFlushPort.out_i]
            en = aig.Or(en, self._translate(aig, (mayFlush, clkI)))

        ec = ioNode.getExtraCondDriver()
        if ec is not None:
            en = aig.And(en, self._translate(aig, (ec, clkI)))

        sw = ioNode.getSkipWhenDriver()
        if sw is not None:
            en = aig.And(en, self._translate(aig, (sw, clkI)))
        return en

    def _buildArchSyncNodeExpr(self,
                               scc: SetList[ArchSyncNodeTy],
                               aig: Abc_Aig_t,
                               nodeIo: ArchSyncNodeIoDict,
                               neighborDict: ArchSyncNeighborDict,
                               syncNode: ArchSyncNodeTy):
        _, clkI = syncNode
        # all inputs (ready & extraCond) | skipWhen and all outputs (valid & extraCond) | skipWhen
        ack = self.c1
        reads, writes = nodeIo[syncNode]
        reads = copy(reads)
        writes = copy(writes)

        _neighborDict = neighborDict.get(syncNode, None)
        if _neighborDict:
            for otherNode, sucChannels in _neighborDict.items():
                if otherNode in scc:
                    otherNodeAck = self._translate(aig, otherNode)
                    for c in sucChannels:
                        # build channel out valid, in ready expressions
                        # build output valid, input ready, expressions

                        if isinstance(c, HlsNetNodeRead):
                            storageCapacity = c.associatedWrite._getBufferCapacity()
                            if storageCapacity > 0:
                                # ack if there is data in the buffer
                                wAck = self._translate(aig, (c.getValidNB(), clkI))
                            else:
                                # ack if the write can perform its function
                                w = c.associatedWrite
                                wAck = self._translateIOAckExpr(aig, clkI, w, None)
                                if wAck is None:
                                    wAck = otherNodeAck
                                else:
                                    wAck = aig.And(wAck, otherNodeAck)
                                if w._isFlushable:
                                    raise NotImplementedError()

                            rAck = self._translateIOAckExpr(aig, clkI, c, wAck)
                            ack = self._buildAndOptional(aig, ack, rAck)

                        else:
                            assert isinstance(c, HlsNetNodeWrite), c
                            storageCapacity = c._getBufferCapacity()
                            rAck = self._translateIOAckExpr(aig, clkI, c.associatedRead, otherNodeAck)
                            wAck = self._translateIOAckExpr(aig, clkI, c, rAck)

                            if storageCapacity > 0:
                                full = self._translate(aig, (c.getFullPort(), clkI))
                                wAck = aig.Or(wAck, aig.Not(full))

                            ack = self._buildAndOptional(aig, ack, wAck)
                else:
                    # successor is not in the same HsSCC this means that
                    # the normal RTL valid/ready signaling could be used
                    for c in sucChannels:
                        if isinstance(c, HlsNetNodeRead):
                            reads.append(c)
                        else:
                            writes.append(c)

        for r in reads:
            r: HlsNetNodeRead
            if r._rtlUseValid:
                rVld = self._translate(aig, (r.getValidNB(), clkI))
            else:
                rVld = None
            rAck = self._translateIOAckExpr(aig, clkI, r, rVld)
            ack = self._buildAndOptional(aig, ack, rAck)

        for w in writes:
            if w._rtlUseReady:
                wRd = self._translate(aig, (w.getReadyNB(), clkI))
            else:
                wRd = None

            wAck = self._translateIOAckExpr(aig, clkI, w, wRd)

            if wAck is not None:
                if w._isFlushable:
                    raise NotImplementedError("mayFlush")
                    isFlushed = self._translate(aig, (w.getIsFlushedPort(), clkI))
                    wAck = aig.Or(wAck, isFlushed)
            ack = self._buildAndOptional(aig, ack, wAck)
        return ack

    def _addPrimaryInput(self, outPort: HlsNetNodeOut, clkI: int):
        key = (outPort, clkI)
        self.prinaryInputs.append(key)
        abcI = self.net.CreatePi()
        name = outPort.getPrettyName(useParentName=False)
        abcI.AssignName(f"{name}_clk{clkI:d}", "")
        self.ioMap[abcI.Name()] = outPort
        self.translationCache[key] = abcI
        return abcI

    def _collectFlagDefsFromIONodes(self, allSccIOs: AllIOsOfSyncNode):
        # flags of IO ports which are used to control it
        # it may be propagated to other sync node or it is just output of handshake logic
        ioInputFlags: SetList[HlsNetNodeIn] = SetList()
        # control outputs of IO nodes which will be rewritten and may be used to control logic in ArchSyncNode
        # potentially also driving something in ioInputFlags
        ioOutputFlagsToRewriteLater: List[Tuple[HlsNetNodeOut, int, Abc_Obj_t]] = []
        # for each io add placeholder Pi for every flag
        for (_, ioNode, syncNode, ioTy) in allSccIOs:
            print(ioNode, syncNode, ioTy)
            ioNode: HlsNetNodeExplicitSync
            syncNode: ArchSyncNodeTy
            ioTy: ReadOrWriteType
            clkI = syncNode[1]

            for flag in [ioNode.extraCond, ioNode.skipWhen]:
                if flag is not None:
                    ioInputFlags.append(flag)

            if ioTy == ReadOrWriteType.CHANNEL_W:
                if ioNode._isFlushable:
                    mayFlush = ioNode.mayFlushPort
                    assert mayFlush is not None
                    ioInputFlags.append(mayFlush)

                    self._addPrimaryInput(ioNode.isFlushed, clkI)

                if ioNode._getBufferCapacity() > 0:
                    forceWritePort = ioNode._forceWritePort
                    if forceWritePort is not None:
                        ioInputFlags.append(forceWritePort)

                    self._addPrimaryInput(ioNode.getFullPort(), clkI)

            isChannel = ioTy.isChannel()
            # if this is a channel we add this as a primary input and we also create a primary output
            # with an expression which will replace this later
            # if this is not channel the ready/valid will not be rewritten as is a primary input
            # of this handshake logic
            if ioTy.isRead():
                if ioNode._rtlUseValid:
                    vldNB = ioNode.getValidNB()
                    _vldNB = self._addPrimaryInput(vldNB, clkI)
                    vld = ioNode._valid
                    if vld is not None:
                        self.translationCache[(vld, clkI)] = _vldNB
                    if isChannel and ioNode.associatedWrite._getBufferCapacity() == 0:
                        ioOutputFlagsToRewriteLater.append((vldNB, clkI, _vldNB))
            else:
                if ioNode._rtlUseReady:
                    rdNB = ioNode.getReadyNB()
                    _rdNB = self._addPrimaryInput(rdNB, clkI)
                    rd = ioNode._ready
                    if rd is not None:
                        self.translationCache[(rd, clkI)] = _rdNB
                    if isChannel:
                        ioOutputFlagsToRewriteLater.append((rdNB, clkI, _rdNB))

        return ioInputFlags, ioOutputFlagsToRewriteLater

    def _createForwardDeclarationsInABC(self, scc: SetList[ArchSyncNodeTy],
                                        ioInputFlags: SetList[HlsNetNodeIn],
                                        ioOutputFlagsToRewriteLater: List[Tuple[HlsNetNodeOut, int, Abc_Obj_t]]):
        """
        :param ioInputFlags: input ports of IO nodes which are for flags used in sync logic
        :param ioOutputFlagsToRewriteLater: tuples (HlsNetlistOut, clock index, ABC primary input) of outputs
            in netlist which may be used internally in sync logic and may be output of sync logic
            (if used by something else than nodes of sync logic, which we do not know yet)
        """
        net = self.net
        # :note: we can not store Abc_Obj_t because the object could be discarded after first operation with network
        #        we can not use index because IO may reorder and we can not use Id because it also changes
        ioMap: Dict[str, Union[Tuple[DIRECTION, ArchSyncNodeTy], HlsNetNodeOut]] = {}

        # primary input is needed because the signal may be used in other expression
        # primary output is needed because the signal may drive other nodes
        aigExternallyConnectedInputOuputTuples: List[Tuple[Abc_Obj_t, Abc_Obj_t, Union[HlsNetNodeOut, HlsNetNodeIn]]] = []
        # forward declaration of all signals used in handshake logic
        for port in ioInputFlags:
            # for each flag create an input and output "variable"
            port: HlsNetNodeOut
            name = port.getPrettyName(useParentName=False)
            assert name not in ioMap, (name, ioMap[name], port)
            #print("declare in/out port", name)
            abcI = net.CreatePi()
            abcI.AssignName(name, "_i")
            # :note: this is tmp primary output
            # we use it for construction of tmp expression which will hold
            # current expression for condition and then we use it during
            # expansion of expressions during combination loop solving
            abcO = net.CreatePo()
            abcO.AssignName(name, "")
            ioMap[abcO.Name()] = port
            self.translationCache[port] = abcI
            aigExternallyConnectedInputOuputTuples.append((abcI, abcO, port))
            self.inToOutConnections[abcI] = abcO

        for port, _, abcI in ioOutputFlagsToRewriteLater:
            port: HlsNetNodeOut
            abcI: Abc_Obj_t
            name = port.getPrettyName(useParentName=False)
            assert name not in ioMap, (name, ioMap[name], port)
            abcO = net.CreatePo()
            abcO.AssignName(name, "")
            ioMap[abcO.Name()] = port
            self.translationCache[port] = abcI
            aigExternallyConnectedInputOuputTuples.append((abcI, abcO, port))
            self.inToOutConnections[abcI] = abcO

        # forward declaration of all ArchSyncNode flags
        syncNodeEn = []
        for c in scc:
            c: ArchSyncNodeTy
            abcI = net.CreatePi()
            abcO = net.CreatePo()
            syncNodeEn.append(abcO)
            name = f"hsSccEn_{ArchSyncNodeTy_stringFormat_short(c)}"
            abcI.AssignName(name, "_i")
            abcO.AssignName(name, "")
            ioMap[abcO.Name()] = (DIRECTION.OUT, c)
            self.translationCache[c] = abcI
            self.inToOutConnections[abcI] = abcO

        return syncNodeEn, aigExternallyConnectedInputOuputTuples

    def translate(self,
                scc: SetList[ArchSyncNodeTy],
                sccIndex: int,
                nodeIo: ArchSyncNodeIoDict,
                neighborDict: ArchSyncNeighborDict,
                allSccIOs: AllIOsOfSyncNode,
                ioNodeToParentSyncNode: ArchSyncChannelToParentDict,
        ):
        """
        Translate HsSCC handshake logic to ABC AIG
        Handshake logic is composed of:
        * io flags (extraCond, skipWhen, mayFlush, isFlushed, ready, readyNB, valid, validNB, full)
            * including any logic connecting them together
        * enable for each stage of pipeline/state of FSM
        """
        f = Abc_Frame_t.GetGlobalFrame()
        net = Abc_Ntk_t(Abc_NtkType_t.ABC_NTK_STRASH, Abc_NtkFunc_t.ABC_FUNC_AIG, 64)
        net.setName(f"hsscc{sccIndex}")
        self.net = net
        f.SetCurrentNetwork(net)
        aig: Abc_Aig_t = net.pManFunc
        self.c1 = net.Const1()

        ioInputFlags, ioOutputFlagsToRewriteLater = self._collectFlagDefsFromIONodes(allSccIOs)
        # collect which nodes are driving channel control so we now what is part
        # of control logic and what should be translated to ABC AIG for further processing
        self.nodesDrivenFromIoState = _collectHlsNtNodeDefToUseUntilTimeNotCrossingChannelControlForMany(
            ioOutputFlagsToRewriteLater, ioInputFlags)

        netlist: HlsNetlistCtx = scc[0][0].netlist
        clkPeriod = netlist.normalizedClkPeriod
        syncNodeEn, aigExternallyConnectedInputOuputTuples = self._createForwardDeclarationsInABC(
            scc, ioInputFlags, ioOutputFlagsToRewriteLater)

        outputsFromAbcNet = self.outputsFromAbcNet = set(syncNodeEn)
        for _, _, abcI in ioOutputFlagsToRewriteLater:
            abcI: Abc_Obj_t
            outputsFromAbcNet.add(abcI)

        # build extraCond, skipWhen, maySkip expressions
        for (_, abcO, port) in aigExternallyConnectedInputOuputTuples:
            port: HlsNetNodeOut
            n = port.obj
            if isinstance(port, HlsNetNodeIn):
                clkI = indexOfClkPeriod(n.scheduledIn[port.in_i], clkPeriod)
                v = self._translate(aig, (n.dependsOn[port.in_i], clkI))
            else:
                clkI = indexOfClkPeriod(n.scheduledOut[port.out_i], clkPeriod)
                # build readyNB/validNB expressions
                # :see: doc of this class

                if isinstance(n, HlsNetNodeRead):
                    assert port == n._validNB, port
                    r: HlsNetNodeRead = n
                    w: HlsNetNodeWrite = r.associatedWrite
                    assert w._getBufferCapacity() == 0, (w, "Capacity must be 0, otherwise valid is not causing handshake loop because it comes from register")
                    wSyncNode = ioNodeToParentSyncNode[w]
                    # write.valid = parentNode.ack & write.extraCond & ~write.skipWhen
                    # read.valid = write.valid | (~write.empty if write.capacity > 0 else write.mayFlush)
                    v = self._translateIOEnExpr(aig, wSyncNode, w)

                else:
                    assert isinstance(n, HlsNetNodeWrite), n
                    assert port == n._readyNB
                    w: HlsNetNodeWrite = n
                    r: HlsNetNodeRead = w.associatedRead
                    rSyncNode = ioNodeToParentSyncNode[r]
                    rClkI: int = rSyncNode[1]
                    # write.ready = read.ready | ~write.full
                    # read.ready = parentNode.ack & read.extraCond & ~read.skipWhen

                    rReady = self._translateIOEnExpr(aig, rSyncNode, r)
                    if w._getBufferCapacity() > 0:
                        rReady = aig.Or(rReady, aig.Not(self._translate(aig, (w.getFullPort(), rClkI))))
                    v = rReady

            abcO.AddFanin(v)

        # build ArchSyncNode enable expressions
        for abcO, syncNode in zip(syncNodeEn, scc):
            ack = self._buildArchSyncNodeExpr(scc, aig, nodeIo, neighborDict, syncNode)
            abcO.AddFanin(ack)
        
        
        aig.Cleanup()  # removes dangling nodes
        net.Check()
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)
        return f, net, aig

    def expandExprToRmCombinationalLoops(self):
        # for each term completely expand all non primary inputs of handshake logic
        net = self.net
        aig: Abc_Aig_t = net.pManFunc
        self.net.Io_Write("ChannelHandshakeFlagResolver.abc.0.dot", Io_FileType_t.IO_FILE_DOT)
        self.net.Io_Write("ChannelHandshakeFlagResolver.abc.0.v", Io_FileType_t.IO_FILE_VERILOG)
        Abc_NtkExpandExternalCombLoops(net, aig, self.inToOutConnections, self.outputsFromAbcNet)
        aig.Cleanup()  # removes dangling nodes
        net.Check()
        for _ in range(2):
            net = abcCmd_resyn2(net)
            net = abcCmd_compress2(net)
            aig.Cleanup()  # removes dangling nodes
            net.Check()
        self.net.Io_Write("ChannelHandshakeFlagResolver.abc.1.dot", Io_FileType_t.IO_FILE_DOT)
        self.net.Io_Write("ChannelHandshakeFlagResolver.abc.1.v", Io_FileType_t.IO_FILE_VERILOG)

    def translateFromAbcToHlsNetlist(self, parent: ArchElementNoSync, termPropagationCtx: ArchElementTermPropagationCtx):
        # replace all outputs of handshake logic in original circuit with
        # new acyclic replacement
        raise NotImplementedError()
