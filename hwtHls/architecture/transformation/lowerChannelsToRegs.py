from typing import Optional

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.analysis.fsmStateTransition import HlsAndRtlNetlistAnalysisPassFsmStateTransition
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData, HdlType_isVoid
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitRegisterAccess import HlsNetNodeExplicitRegisterLoad, \
    RtlRegisterMeta, HlsNetNodeExplicitRegisterStore
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import HlsNetNodeOut_getMaxUseTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import clkWindowEnd, clkWindowBegin, \
    clkWindowIndex, SchedTime
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic


class HlsAndRtlNetlistPassLowerChannelsToRegs(HlsAndRtlNetlistPass):
    """
    The channels (implemented using :class:`HlsNetNodeRead`, :class:`HlsNetNodeWrite`) and are handled as other regs in FSM
    but have set/reset condition explicitly specified using "extraCond" input port.

    :note: This also lowers the :class:`HlsProgramStarter`

    There are several things which has to be handled for channels:
    1. The channel data/ready/valid/full/extraCond has to be reimplemented using registers.
    2. If the values from read live after write they have to be stored in a different registers
       as the original registers may be overwritten by the write node.
   
    """

    @staticmethod
    def _createCopyForRegsIfUsedAfterW(r: HlsNetNodeRead, w: HlsNetNodeWrite, clkPeriod: SchedTime, wClkI: int):
        for rPort in (r._validNB, r._portDataOut):
            if rPort is None or HdlType_isNonData(rPort._dtype):
                continue
            maxUseTime = HlsNetNodeOut_getMaxUseTime(rPort)
            if maxUseTime is not None and clkWindowIndex(maxUseTime, clkPeriod) > wClkI:
                # :note: this may happen for example if the value computed in the loop 
                #        is a live in of the loop and also the livout on some edge
                #        and uses on that edge are scheduled in clk window after loop end.
                #        However under normal conditions there should be already a forward edge
                #        on replacing this dependency. Because that is how llvmMirToNetlist works.
                raise NotImplementedError(rPort, clkWindowIndex(maxUseTime, clkPeriod), wClkI)

    @classmethod
    def _lowerValidNBUse(cls, netlist: HlsNetlistCtx, r: HlsNetNodeRead, requiresVld: bool,
                          builder: HlsNetlistBuilder,
                          fullRegMeta: RtlRegisterMeta,
                          vldRegMeta: RtlRegisterMeta,
                          elm: ArchElementFsm,
                          rClkI: int) -> tuple[HlsNetNodeOut, HlsNetNodeOut]:
        clkPeriod = netlist.normalizedClkPeriod
        vldLdInR: Optional[HlsNetNodeOut] = None
        fullLdInR: Optional[HlsNetNodeOut] = None
        if requiresVld:
            # r._validNB=stEn ? full : vld in rClkI where r is
            # :attention: the _validNB can be potentially wired to logic
            #             which is not private to parent FSM state
            #             that is why we have to add MUX
            clkPeriod = netlist.normalizedClkPeriod
            validNB = r._validNB

            def inputIsInRClkI(i: HlsNetNodeIn) -> bool:
                return i.obj.scheduledIn[i.in_i] // clkPeriod == rClkI

            hasAnyUseInRClkI = any(inputIsInRClkI(i) for i in r.usedBy[r._validNB.out_i])
            if r.usedBy[r._validNB.out_i]:
                vldLdInR = HlsNetNodeExplicitRegisterLoad.createInTime(
                    netlist, vldRegMeta, elm, clkWindowBegin(rClkI, clkPeriod))._outputs[0]
                fullLdInR = HlsNetNodeExplicitRegisterLoad.createInTime(
                    netlist, fullRegMeta, elm, clkWindowBegin(rClkI, clkPeriod))._outputs[0]
                # vldSt for rClkI + 1, vld=full
                HlsNetNodeExplicitRegisterStore.createAsCondSet(
                    netlist, vldRegMeta, elm, clkWindowEnd(rClkI, clkPeriod), vldLdInR, None)

                if hasAnyUseInRClkI:
                    stateEn = elm.getStageEnable(rClkI)[0]
                    vldInR = builder.buildMux(BIT, (fullLdInR, stateEn, vldLdInR))
                    scheduleUnscheduledControlLogic((elm, rClkI), vldInR)
                    assert vldInR.obj.scheduledOut[vldInR.out_i] == clkWindowBegin(rClkI, clkPeriod), (
                        vldInR, vldInR.obj.scheduledOut[vldInR.out_i], rClkI, clkPeriod)
                    builder.replaceOutputIf(validNB, vldInR, inputIsInRClkI)

                if r.usedBy[r._validNB.out_i]:
                    # :note: if there are some uses in later clock windows
                    afterRTime = clkWindowBegin(rClkI + 1, clkPeriod)
                    for i in r.usedBy[r._validNB.out_i]:
                        i: HlsNetNodeIn
                        assert i.obj.scheduledIn[i.in_i] >= afterRTime, i

                    builder.replaceOutput(r._validNB, vldLdInR, True)
        else:
            vldLdInR = HlsNetNodeExplicitRegisterLoad.createInTime(
                netlist, fullRegMeta, elm, clkWindowBegin(rClkI, clkPeriod))._outputs[0]

        return vldLdInR, fullLdInR

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        dbgTracer = DebugTracer(None)
        clkPeriod = netlist.normalizedClkPeriod
        changed = False
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            _changed = False
            if isinstance(elm, ArchElementFsm):
                elm: ArchElementFsm
                for w in elm.subNodes:
                    if isinstance(w, HlsProgramStarter):
                        fullRegMeta = RtlRegisterMeta(f"programStarter_n{w._id}_full", False, BIT, True)
                        vldRegMeta = RtlRegisterMeta(f"programStarter_n{w._id}_vld", False, BIT, True)
                        builder: HlsNetlistBuilder = w.getHlsNetlistBuilder()
                        rClkI = w.getSchedResourceClkI()
                        self._lowerValidNBUse(netlist, w, True, builder, fullRegMeta, vldRegMeta, elm, rClkI)
                        HlsNetNodeExplicitRegisterStore.createAsCondConstSet(netlist, builder, fullRegMeta, elm, rClkI, b0, None)
                        continue

                    if not isinstance(w, HlsNetNodeWrite):
                        continue

                    w: HlsNetNodeWrite
                    r = w.associatedRead
                    if r is None or w.allocationType != CHANNEL_ALLOCATION_TYPE.REG or r not in elm.subNodes:
                        # this is not a 1-item channel buffer inside of single FSM
                        continue

                    if w._getBufferCapacity() == 0:
                        # this channel does not have state which would require lowering
                        continue

                    r: HlsNetNodeRead
                    # lower to pairs of HlsNetNodeExplicitRegisterLoad, HlsNetNodeExplicitRegisterStore
                    # for data and controll

                    builder: HlsNetlistBuilder = r.getHlsNetlistBuilder()

                    isBackedge = w.isBackedge()
                    assert w._getBufferCapacity() == 1, ("if the capacity was larger this should not have CHANNEL_ALLOCATION_TYPE.REG", w, w._getBufferCapacity())
                    assert r.skipWhen is None, ("This should have been lowered", r)
                    assert w.skipWhen is None, ("This should have been lowered", w)
                    rEn = r.getExtraCondDriver()
                    wEn = w.getExtraCondDriver()
                    rClkI = r.getSchedResourceClkI()
                    wClkI = w.getSchedResourceClkI()
                    endOfWClk = clkWindowEnd(wClkI, clkPeriod)
                    endOfRClk = clkWindowEnd(rClkI, clkPeriod)
                    r_out = r._portDataOut
                    hasData = r.usedBy[r_out.out_i] and not HdlType_isVoid(r_out._dtype)
                    assert r._valid is None, ("valid should have been lowered to validNB", r)
                    requiresVld = r._validNB is not None
                    assert w._ready is None, ("ready should have been lowered to full port", w)
                    assert w._readyNB is None, ("readyNB should have been lowered to full port", w)
                    requiresFull = requiresVld or w._fullPort is not None
                    hadInit = int(bool(r.channelInitValues))
                    namePrefix = RtlRegisterMeta.resolveName(w, r)

                    if isBackedge:
                        self._createCopyForRegsIfUsedAfterW(r, w, clkPeriod, wClkI)

                    if requiresFull:
                        fullRegMeta = RtlRegisterMeta(namePrefix + "_full", isBackedge, BIT, hadInit)
                        if requiresVld:
                            vldRegMeta = RtlRegisterMeta(namePrefix + "_vld" , isBackedge, BIT, hadInit)

                    if hasData:
                        if hadInit:
                            assert len(r.channelInitValues) == 1, (r, r.channelInitValues)
                            assert len(r.channelInitValues[0]) == 1, (r, r.channelInitValues[0])
                        dataRegMeta = RtlRegisterMeta(namePrefix + "_data", isBackedge, r._portDataOut._dtype,
                                                   r.channelInitValues[0][0] if hadInit else None)

                    if requiresFull:
                        _, fullInR = self._lowerValidNBUse(netlist, r, requiresVld, builder, fullRegMeta, vldRegMeta, elm, rClkI)

                        if w._fullPort is not None:
                            if rClkI <= wClkI:
                                # reuse already read "full" in the time of r
                                latestFull = fullInR
                            else:
                                # need to read "full" in the time of w
                                fullLdInW = HlsNetNodeExplicitRegisterLoad.createInTime(
                                    netlist, fullRegMeta, elm, clkWindowBegin(wClkI, clkPeriod))
                                latestFull = fullLdInW._outputs[0]

                            builder.replaceOutput(w._fullPort, latestFull, True, False)

                        if rClkI == wClkI:
                            # full = wEn | (full & ~rEn)
                            vldAndNREn = builder.buildAndOptional(fullInR, builder.buildNot(rEn))
                            fullNext = builder.buildOrOptional(wEn, vldAndNREn,
                                   name=namePrefix + "_fullNext")
                            # full st
                            HlsNetNodeExplicitRegisterStore.createAsCondSet(
                                netlist, fullRegMeta, elm, endOfWClk, fullNext, None)
                        else:
                            # in r
                            HlsNetNodeExplicitRegisterStore.createAsCondConstSet(
                                netlist, builder, fullRegMeta, elm, endOfRClk, b0, rEn)

                            # in w
                            HlsNetNodeExplicitRegisterStore.createAsCondConstSet(
                                netlist, builder, fullRegMeta, elm, endOfWClk, b1, wEn)

                    if hasData:
                        # dataLd
                        HlsNetNodeExplicitRegisterLoad.createAsOutSubstitution(
                            netlist, builder, dataRegMeta, r._portDataOut)
                        # dataSt
                        HlsNetNodeExplicitRegisterStore.createAsInSubstitution(
                            netlist, builder, dataRegMeta, w._portSrc, wEn)

                    if rEn:
                        r.extraCond.disconnectFromHlsOut(rEn)
                    if wEn:
                        w.extraCond.disconnectFromHlsOut(wEn)

                    if not hasData and w._portSrc is not None:
                        w._portSrc.disconnectFromHlsOut(w.dependsOn[w._portSrc.in_i])

                    netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, r, None)
                    assert not any(r.usedBy), (r, r.usedBy)
                    assert all(d is None for d in r.dependsOn), (r, r.dependsOn)
                    r.markAsRemoved()
                    netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, w, None)
                    assert not any(w.usedBy), (w, w.usedBy)
                    assert all(d is None for d in w.dependsOn), (w, w.dependsOn)
                    w.markAsRemoved()
                    _changed = True
                if _changed:
                    elm.filterNodesUsingRemovedSet(recursive=False)
                    changed = True

        if changed:
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateTransition)
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()