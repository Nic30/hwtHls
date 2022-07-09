
from itertools import chain
from typing import Union, List, Dict, Tuple, Optional

from hwt.code import SwitchLogic
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsVal import BitsVal
from hwt.interfaces.std import HandshakeSync, Signal, Handshaked
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extract_control_sig_of_interface, SignalsOfStages, ExtraCondMemberList, \
    SkipWhenMemberList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync, \
    HlsNetNodeReadSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.handshaked.streamNode import StreamNode
from ipCorePackager.constants import INTF_DIRECTION


class AllocatorArchitecturalElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type
    It is used as context for allocator.

    :ivar netlist: parent HLS netlist context for this element
    :ivar namePrefix: name prefix for debug purposes
    :ivar netNodeToRtl: dictionary {hls node: rtl instance}
    :ivar connections: list of connections in individual stage in this arch. element, user for registration
        of products of nodes for sync generator
    :ivar allNodes: list in this arch element
    :ivar connections: list of rtl object allocated for each specific clock stage
    :ivar stageSignals: an object which makes connections list accessible by time
    :ivar interArchAnalysis: an object of inter architecture element sharing analysis which is set after allocation starts
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str,
                 allNodes: UniqList[HlsNetNode],
                 connections: List[ConnectionsOfStage],
                 stageSignals: SignalsOfStages):
        self.namePrefix = namePrefix
        self.netlist = netlist
        self.netNodeToRtl: Dict[
            Union[
                HlsNetNodeOut,  # any operation output
                Tuple[HlsNetNodeOut, Interface]  # write
            ],
            TimeIndependentRtlResource] = {}
        # function to create register/signal on RTL level
        self._reg = netlist.parentUnit._reg
        self._sig = netlist.parentUnit._sig
        self.connections = connections
        self.allNodes = allNodes
        assert isinstance(stageSignals, SignalsOfStages), stageSignals
        self.stageSignals = stageSignals
        self.interArchAnalysis: Optional["InterArchElementNodeSharingAnalysis"] = None

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        pass

    def _afterOutputUsed(self, o: HlsNetNode):
        clkPeriod = self.netlist.normalizedClkPeriod
        epsilon = self.netlist.scheduler.epsilon
        depRtl = self.netNodeToRtl.get(o, None)
        if depRtl is not None:
            depRtl: TimeIndependentRtlResource
            if depRtl.timeOffset is TimeIndependentRtlResource.INVARIANT_TIME:
                return
            # in in this arch. element
            # registers uses in new times
            t = depRtl.timeOffset + (len(depRtl.valuesInTime) - 1) * clkPeriod + epsilon
            # :note: done in reverse so we do not have to always iterater over registered prequel
            for _ in reversed(depRtl.valuesInTime):
                sigs = self.stageSignals.getForTime(t)
                if depRtl in sigs:
                    break
                sigs.append(depRtl)
                t -= clkPeriod

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        con = self.connections[clkI]
        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append(intf)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append(intf)

    def instantiateHlsNetNodeOut(self, o: HlsNetNodeOut) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            clkI = start_clk(o.obj.scheduledOut[o.out_i], self.netlist.normalizedClkPeriod)
            if len(self.stageSignals) <= clkI or self.stageSignals[clkI] is None:
                raise AssertionError("Asking for node output which should have forward declaration but it is missing", self, o, clkI)
            # new allocation, use registered automatically
            _o = o.obj.allocateRtlInstance(self)
            self._afterNodeInstantiated(o.obj, _o)
            if _o is None:
                # to support the return of the value directly to avoid lookup from dict
                try:
                    return self.netNodeToRtl[o]
                except KeyError:
                    # {v:k for k, v in o.obj.internOutToOut.items()}[o]
                    raise AssertionError(self, "Node did not instantiate its output", o.obj, o)
        else:
            # used and previously allocated
            # used_signals.getForTime(t).append(_o)
            pass

        return _o

    def instantiateHlsNetNodeOutInTime(self, o: HlsNetNodeOut, time:float,
                                       ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        _o = self.instantiateHlsNetNodeOut(o)
        if isinstance(_o, TimeIndependentRtlResource):
            return _o.get(time)
        else:
            return _o

    def _copyChannelSyncAll(self, node: Union[HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync],
                        res_skipWhen: Dict[Interface, SkipWhenMemberList],
                        res_extraCond: Dict[Interface, ExtraCondMemberList],
                        intf: Interface, sync_time: float):

        if node.skipWhen is not None:
            e = node.dependsOn[node.skipWhen.in_i]
            skipWhen = self.instantiateHlsNetNodeOutInTime(e, sync_time)
            curSkipWhen = res_skipWhen.get(intf, None)
            if curSkipWhen is not None:
                curSkipWhen.data.append(skipWhen)
            else:
                res_skipWhen[intf] = SkipWhenMemberList([skipWhen, ])
        else:
            skipWhen = None

        if node.extraCond is not None:
            e = node.dependsOn[node.extraCond.in_i]
            extraCond = self.instantiateHlsNetNodeOutInTime(e, sync_time)
            curExtraCond = res_extraCond.get(intf, None)
            if curExtraCond is not None:
                curExtraCond.data.append((skipWhen, extraCond))
            else:
                extraCond = ExtraCondMemberList([(skipWhen, extraCond), ])
                res_extraCond[intf] = extraCond

    def _copyChannelSync(self, intf: Interface,
                   node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                   res_skipWhen: Dict[Interface, SkipWhenMemberList],
                   res_extraCond: Dict[Interface, ExtraCondMemberList]):

        if isinstance(node, HlsNetNodeRead):
            node: HlsNetNodeRead
            sync_time = node.scheduledOut[0]
            # the node may have only HlsNetNodeReadSync and HlsNetNodeExplicitSync users
            # in this case we have to copy the sync from HlsNetNodeExplicitSync
            onlySuc = None
            for u in node.usedBy[0]:
                u: HlsNetNodeOut
                if not isinstance(u.obj, HlsNetNodeReadSync):
                    if onlySuc is None:
                        onlySuc = u.obj
                    else:
                        # we found out some other non HlsNetNodeReadSync user, we can not copy sync
                        onlySuc = None
                        break

            if isinstance(onlySuc, HlsNetNodeExplicitSync) and not isinstance(onlySuc, HlsNetNodeWrite):
                if onlySuc._outputs[0] not in self.netNodeToRtl:
                    _o = onlySuc.allocateRtlInstance(self)  # to assert that the sync signal is constructed
                    self._afterNodeInstantiated(onlySuc, _o)
                self._copyChannelSyncAll(onlySuc, res_skipWhen, res_extraCond, intf, sync_time)

        else:
            assert isinstance(node, (HlsNetNodeWrite, HlsNetNodeExplicitSync)), node
            sync_time = node.scheduledIn[0]

        self._copyChannelSyncAll(node, res_skipWhen, res_extraCond, intf, sync_time)

    def _collectChannelRtlSync(self,
                          sync_per_io: Dict[Interface, Union[SkipWhenMemberList, ExtraCondMemberList]],
                          defaultVal: int):
        sync: Dict[Interface, RtlSignal] = {}
        for intf, sync_source in sync_per_io.items():
            intf = extract_control_sig_of_interface(intf)
            if intf == (1, 1):
                # does not have any sync
                continue

            assert sync_source
            en = sync_source.resolve()
            if isinstance(en, BitsVal):
                # current block en=1
                assert int(en) == defaultVal, en
            else:
                assert isinstance(en, RtlSignal), en
                sync[intf] = en

        return sync

    def _makeSyncNode(self, con: ConnectionsOfStage) -> StreamNode:
        masters = [extract_control_sig_of_interface(intf) for intf in con.inputs]
        slaves = [extract_control_sig_of_interface(intf) for intf in con.outputs]
        if not masters and not slaves:
            extraConds = None
            skipWhen = None
        else:
            extraConds = self._collectChannelRtlSync(con.io_extraCond, 1)
            # skipWhen conditions may only be valid if all data in this stage are valid
            # this may not be the case because the data may come directly from interface itself.
            # Because of this we need to add additional condition to skipWhen expression which makes it 0
            # if there is some unsatisfied IO dependency in this stage. 
            _skipWhen = self._collectChannelRtlSync(con.io_skipWhen, 0)
            skipWhen = {}
            for intf in chain(masters, slaves):
                intfSkipWhen = _skipWhen.get(intf, None)
                #print(intf)
                #print("extraCond", extraConds.get(intf, None))
                #print("skipWhen", intfSkipWhen)
                #print("")
                
                if intfSkipWhen is None:
                    # this interface does not have skip when condition
                    continue
                # we have to extend intfSkipWhen condition
                #for otherIntfDir, otherIntf in chain(zip((INTF_DIRECTION.MASTER for _ in masters), masters),
                #                                     zip((INTF_DIRECTION.SLAVE for _ in slaves), slaves),
                #                       ):
                #    if otherIntf is intf:
                #        continue
                #    otherSkipWhen = _skipWhen.get(otherIntf, None)
                #    isM = otherIntfDir == INTF_DIRECTION.MASTER
                #    if isinstance(otherIntf, Axi_hs):
                #        if isM:
                #            ack = otherIntf.valid
                #        else:
                #            ack = otherIntf.ready
                #    
                #    elif isinstance(otherIntf, (Handshaked, HandshakeSync)):
                #        if isM:
                #            ack = otherIntf.vld
                #        else:
                #            ack = otherIntf.rd
                #    else:
                #        assert isinstance(otherIntf, tuple), otherIntf
                #        if isM:
                #            ack = otherIntf[0]
                #        else:
                #            ack = otherIntf[1]
                #    
                #    if isinstance(ack, int):
                #        # always valid no otherSkipWhen or otherSkipWhen with no effect -> no extra sync required
                #        assert ack == 1, ack
                #    else:
                #        if otherSkipWhen is None:
                #            intfSkipWhen = intfSkipWhen & ack
                #        else:
                #            intfSkipWhen = intfSkipWhen | (otherSkipWhen & ~ack)
                             
                skipWhen[intf] = intfSkipWhen        
                
        sync = StreamNode(
            masters,
            slaves,
            extraConds=extraConds,
            skipWhen=skipWhen,
        )
        con.sync_node = sync
        return sync

    def _allocateIo(self, intf: Interface, node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                    con: ConnectionsOfStage,
                    ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                    ioSeen: UniqList[Interface],
                    rtl: List[HdlStatement]):
        ioSeen.append(intf)
        ioMuxes.setdefault(intf, []).append((node, rtl))

        if not isinstance(intf, (Signal, RtlSignal)):
            # if it has some synchronization
            if isinstance(node, HlsNetNodeRead):
                con.inputs.append(intf)
            else:
                con.outputs.append(intf)

        self._copyChannelSync(intf, node, con.io_skipWhen, con.io_extraCond)

    def _allocateIoMux(self, ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                             ioSeen: UniqList[Interface]):
        for io in ioSeen:
            muxCases = ioMuxes[io]
            if len(muxCases) == 1:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    yield muxCases[0][1]
            else:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    # create a write mux
                    rtlMuxCases = []
                    for w, stms in muxCases:
                        t = w.scheduledOut[0]
                        caseCond = None
                        if w.extraCond is not None:
                            caseCond = self.instantiateHlsNetNodeOutInTime(w.dependsOn[w.extraCond.in_i], t).data

                        if w.skipWhen is not None:
                            _caseCond = ~self.instantiateHlsNetNodeOutInTime(w.dependsOn[w.skipWhen.in_i], t).data
                            if caseCond is None:
                                caseCond = _caseCond
                            else:
                                caseCond = caseCond & _caseCond

                        rtlMuxCases.append((caseCond, stms))
                    stms = rtlMuxCases[0][1]
                    if isinstance(stms, HdlAssignmentContainer):
                        defaultCase = stms.dst(None)
                    else:
                        defaultCase = [asig.dst(None) for asig in stms]
                    yield SwitchLogic(rtlMuxCases, default=defaultCase)
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    # no mux needen and we already merged the synchronization

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Allocate main RTL object which are required from HlsNetNode instances assigned to this element.
        """
        raise NotImplementedError("Implement in child class")

    def allocateSync(self):
        """
        Instantiate an additional RTL objects to implement the synchronization of the element
        which are not direclty present in input HlsNetNode instances.
        """
        raise NotImplementedError("Implement in child class")

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.namePrefix:s}>"

