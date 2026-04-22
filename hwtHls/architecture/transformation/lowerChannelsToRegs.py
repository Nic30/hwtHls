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
    3. Some jumps in parent FSM cause state of channel to be restarted.
       Jumps before read will apply the data consumption from the channe.
       Read/write nodes will channel state registers based on its extraCond
    
    Implicit register update rules:
    
    * For normal register set to X if jumping before def
        
    * For forward edges the vld flag has to be cleared if the jump is performed before position of write.
        
        jmp src ? write  jmp dst ? read  vld change
        ================ =============== ==========
                ==               <=      vld=full=extraCond 
                >                <=      vld=full
                else             else    preserve vld
        
        st  nodes 
        === ========
        0   
        --- --------
        1   v0.f.w
        --- --------
        2   v0.f.r
        --- --------
        3   
        
        jump     update
        ======= =========================================
        2->0|1   v0.vld = v0.full = from v0.f.w.extraCond  
        3->0|1   v0.vld = v0.full 
      
    * For backedges - if jumping before read vld=full, if jumping from from write vld=full=extraCond
    
    * The write sets full=wEn, read sets vld=full, full=0 if rEn,  if ~full set data=Undef (sanitization)
      Jump to dst <= read sets vld=0
    * "vld" in the clkWindow where read is replaced by "full", rest is using "vld" directly
    """

    @staticmethod
    def _createCopyForRegsIfUsedAfterW(r: HlsNetNodeRead, w: HlsNetNodeWrite, clkPeriod: SchedTime, wClkI: int):
        for rPort in (r._validNB, r._portDataOut):
            if rPort is None or HdlType_isNonData(rPort._dtype):
                continue
            maxUseTime = HlsNetNodeOut_getMaxUseTime(rPort)
            if maxUseTime is not None and clkWindowIndex(maxUseTime, clkPeriod) > wClkI:
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
        # stateEncoding: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        # assert stateEncoding is not None, "HlsAndRtlNetlistAnalysisPassFsmStateEncoding should not be invalidated"
        # transitionTables: HlsAndRtlNetlistAnalysisPassFsmStateTransition = netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateTransition)
        # assert transitionTables is not None, "HlsAndRtlNetlistAnalysisPassFsmStateTransition should not be invalidated"
        dbgTracer = DebugTracer(None)
        clkPeriod = netlist.normalizedClkPeriod

        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if isinstance(elm, ArchElementFsm):
                elm: ArchElementFsm
                # usedStates = stateEncoding.usedStates[elm]
                # stateEncoding: FsmStateEncoding = stateEncoding.stateEncoding[elm]
                # transitionTable: FsmTransitionTable = transitionTables.fsmTransitionTables[elm]
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
                    # if isBackedge:
                    #    requiresFull = rEn is not None and rEn is not wEn
                    #    #
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

                    # if requiresFull:
                    #    fullLd = createLdForOut(netlist, builder, fullRegMeta, w._fullPort)
                    #    # ready = None
                    #    # for readyPort in (w._ready, w._readyNB):
                    #    #    if readyPort is None:
                    #    #        continue
                    #    #    if ready is None:
                    #    #        ready = builder.buildNot(fullLd._outputs[0])
                    #    #    builder.replaceOutput(readyPort, ready, True)
                    #
                    #    if wClkI == rClkI:
                    #
                    #    else:
                    #        # set full on write
                    #        fullStInW = createConstSet(
                    #            netlist, fullRegMeta, elm, endOfWClk, wEn, None,
                    #            name=namePrefix + "_full_inW")
                    #        # clear full on read
                    #        fullStInR = HlsNetNodeExplicitRegisterStore.createAsCondConstSet(
                    #            netlist, builder, fullRegMeta, elm, endOfRClk, b0, rEn,
                    #            name=namePrefix + "_full_inR")
                    #

                    # if isBackedge:
                    #    # backedge:
                    #    # w or jump over w: set data to what is written, if data/vld/full used after w, create a new copy and update it
                    #
                    #    assert rClkI <= wClkI, (rClkI, wClkI, r, w)
                    #    for srcSt in usedStates:
                    #        if srcSt < rClkI:
                    #            # states before r are irelevant, because register is not writen or read
                    #            continue
                    #
                    #        # for states >= read (exclude already handled wClkI), if jumping <= r set vld=full
                    #        for c, dstSt in transitionTable[srcSt]:
                    #            if srcSt == rClkI or srcSt == wClkI:
                    #                continue  # already handled
                    #            elif dstSt <= rClkI:
                    #                if dstSt <= wClkI:
                    #                    raise NotImplementedError()
                    #                else:
                    #                    raise NotImplementedError()
                    #            else:
                    #                raise NotImplementedError()
                    # else:
                    #    assert rClkI >= wClkI, (rClkI, wClkI, r, w)
                    #    # forward edge:
                    #    # delete the data, vld=0 if not full on jump >= w to <= r
                    #    #
                    #    # |st  nodes|    |st  nodes|
                    #    # |=== =====|    |=== =====|
                    #    # |0        |    |0        |
                    #    # |--- -----|    |--- -----|
                    #    # |1   w, r |    |1   w    |
                    #    # |--- -----|    |--- -----|
                    #    # |2        |    |2        |
                    #    #                |--- -----|
                    #    #                |3   r    |
                    #    #                |--- -----|
                    #    #                |4        |
                    #    #
                    #    for srcSt in usedStates:
                    #        if srcSt < wClkI:
                    #            # states before w are irelevant, because register is not writen or read
                    #            continue
                    #
                    #        elif srcSt == rClkI and rClkI == wClkI:
                    #            for c, dstSt in transitionTable[srcSt]:
                    #                # full = vld = wEn | (full & ~rEn)
                    #                # jumping before r/w, does not change vld/full/data logic
                    #                # The channel must hold value even if jumping before parent loop
                    #                # If value is not read for forwardedge in the loop it is likely to
                    #                # hang but that is the correct behavior as it behaves as original circuit
                    #
                    #                # |st  nodes src  dst |
                    #                # |=== ===== ==== ====|
                    #                # |0                * |
                    #                # |--- ----- ---- ----|
                    #                # |1   w, r    *    * |
                    #                # |--- ----- ---- ----|
                    #                # |2                * |
                    #                #
                    #                raise NotImplementedError(w)
                    #
                    #        elif srcSt >= wClkI and srcSt < rClkI:
                    #            # if jumping from region <w, r)
                    #            #  * jumps to (w, r) region do not affect this reg
                    #            #  * jumps to (begin, w): set vld=full= ~rEn
                    #            #  * jumps from w : full = vld = wEn | full
                    #            #
                    #            #
                    #            #   |st  nodes src dst|
                    #            #   |=== ===== === ===|
                    #            #   |0                |
                    #            #   |--- ----- --- ---|
                    #            #   |1     w    *     |
                    #            #   |--- ----- --- ---|
                    #            #   |2          *     |
                    #            #   |--- ----- --- ---|
                    #            #   |3   r            |
                    #            #   |--- ----- --- ---|
                    #            #   |4                |
                    #            #
                    #            #
                    #            for c, dstSt in transitionTable[srcSt]:
                    #                # src  dst before
                    #                raise NotImplementedError()
                    #
                    #        elif srcSt == rClkI:
                    #            # at the end of the read
                    #            # :note: if valid/full/data is used after r, we have to create
                    #            #        a new register for states > r
                    #            #  vld=full= full & ~rEn
                    #            #
                    #            #   |st  nodes src dst|
                    #            #   |=== ===== === ===|
                    #            #   |0                |
                    #            #   |--- ----- --- ---|
                    #            #   |1   w            |
                    #            #   |--- ----- --- ---|
                    #            #   |2                |
                    #            #   |--- ----- --- ---|
                    #            #   |3   r      *     |
                    #            #   |--- ----- --- ---|
                    #            #   |4                |
                    #            #
                    #            #
                    #            raise NotImplementedError()
                    #        else:
                    #            # srcSt >= rClkI
                    #            raise NotImplementedError()
                    #
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

        pa = PreservedAnalysisSet.preserveScheduling()
        pa.add(HlsAndRtlNetlistAnalysisPassFsmStateTransition)
        pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        return pa
