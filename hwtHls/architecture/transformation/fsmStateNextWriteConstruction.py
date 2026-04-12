from math import inf
from typing import Union, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic, \
    scheduledUnscheduedDummyAsap
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel, LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import  HlsNetNodeRead
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, clkWindowEnd
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.architecture.transformation.dce import ArchElementDCE
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


FsmTransitionTable = dict[int, dict[int, Optional[HlsNetNodeOut]]]


class HlsAndRtlNetlistPassFsmStateNextWriteConstruction(HlsAndRtlNetlistPass):
    """
    Recognize FSM transitions from control channels and other nodes placed in :class:`ArchElementFsm`
    and construct :class:`HlsNetNodeFsmStateWrite` in each state of FSM.
    """

    @classmethod
    def _detectStateTransitions(cls, fsmElm: ArchElementFsm, usedStates:list[int]):
        """
        Detect the state propagation logic and resolve how to replace it with a state bit
        * state bit will be just stored as a register in this FSM
        * read will just read this bit
        * write will set this bit to a value specified in write src if all write conditions are meet
        * if the value written to channel is 1 it means that FSM jump to state where associated read is
          There could be multiple channels written but the 1 should be written to just single one
        * All control channel registers which are not written but do have scheduled potential write in this state must be set to 0
        * Because the control channel is just local it is safe to replace it with register.
          However we must keep it in allNodes list so the node is still registered for this element

        :note: This must be called before construction of data-path because we need to resolve how control channels will be realized
        :note: The state transition can not be extracted if there is communication with some other FSM
            which already have some communication with this FSM. (In order to prevent deadlock.)
        """
        localControlReads, controlToStateI = cls._collectLoops(fsmElm)
        nonSkipableStateI = cls._collectStatesWhichCanNotBeSkipped(fsmElm)
        return cls._resolveTranstitionTableFromLoopControlChannels(
            localControlReads, controlToStateI, nonSkipableStateI, fsmElm, usedStates)

    @classmethod
    def _collectLoops(cls, fsmElm: ArchElementFsm):
        localControlReads: SetList[HlsNetNodeReadAnyChannel] = SetList()
        controlToStateI: dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel], int] = {}
        clkPeriod = fsmElm.netlist.normalizedClkPeriod
        for stI, nodes in fsmElm.iterStages():
            for node in nodes:
                node: HlsNetNode
                assert not isinstance(node, HlsNetNodeLoopStatus), ("HlsNetNodeLoopStatus should be already lowered", node)
                if isinstance(node, HlsNetNodeRead) and node.associatedWrite is not None:
                    node: HlsNetNodeRead
                    wr: HlsNetNodeWrite = node.associatedWrite
                    if wr not in fsmElm.subNodes:
                        continue
                    channelGroup = wr._loopChannelGroup
                    if channelGroup is None or channelGroup.getChannelUsedAsControl() is not wr:
                        continue
                    # :note: now we know that this is the read of a channel which implementes some sort of CFG jump
                    for _, role in channelGroup.connectedLoopsAndBlocks:
                        role: LOOP_CHANEL_GROUP_ROLE
                        if role not in (LOOP_CHANEL_GROUP_ROLE.ENTER,
                                        LOOP_CHANEL_GROUP_ROLE.REENTER,
                                        LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR):
                            continue
                        # :note: initial condition asserts that the "enter" port read and write are in this FSM
                        # print("_collectLoops", node, stI)
                        localControlReads.append(node)
                        controlToStateI[node] = stI
                        wrTime = max(wr.scheduledIn, default=wr.scheduledZero)
                        controlToStateI[wr] = clkWindowIndex(wrTime, clkPeriod)

                # elif isinstance(node, HlsNetNodeLoopStatus):
                #    for g in node.fromReenter:
                #        e = g.getChannelUsedAsControl().associatedRead
                #        assert isinstance(e, HlsNetNodeReadBackedge), e
                #        assert e in fsmElm.subNodes, e
                #        if e.associatedWrite in fsmElm.subNodes:
                #            localControlReads.append(e)
                #            controlToStateI[e] = stI
                #            wr = e.associatedWrite
                #            wrTime = max(wr.scheduledIn, default=wr.scheduledZero)
                #            controlToStateI[e.associatedWrite] = clkWindowIndex(wrTime, clkPeriod)
                #
                    # for g in node.fromExitToHeaderNotify:
                    #    w = g.getChannelUsedAsControl()
                    #    r = w.associatedRead
                    #    if isinstance(r, HlsNetNodeReadBackedge):
                    #        assert r in fsmElm.subNodes, e
                    #        if w in fsmElm.subNodes:
                    #            raise NotImplementedError("Convert loop to FSM transitions")
                    #        # dstI =
        return localControlReads, controlToStateI

    @classmethod
    def _collectStatesWhichCanNotBeSkipped(cls, fsmElm: ArchElementFsm) -> set[int]:
        clkPeriod = fsmElm.netlist.normalizedClkPeriod
        nonSkipableStateI: set[int] = set()
        # element: clockTickIndex
        otherElmConnectionFirstTimeSeen: dict[ArchElement, int] = {}
        for o, uses, outTime in zip(fsmElm._outputs, fsmElm.usedBy, fsmElm.scheduledOut):
            o: HlsNetNodeOut
            clkI = clkWindowIndex(outTime, clkPeriod)
            if not fsmElm.hasUsedStateForClkI(clkI):
                raise AssertionError("fsmElm is missing state for time where node is scheduled", o, clkI)

            for i in uses:
                otherElm: ArchElement = i.obj
                curFistCommunicationStI = otherElmConnectionFirstTimeSeen.get(otherElm, None)
                if curFistCommunicationStI is None:
                    otherElmConnectionFirstTimeSeen[otherElm] = clkI
                elif curFistCommunicationStI == clkI:
                    continue
                elif curFistCommunicationStI > clkI:
                    otherElmConnectionFirstTimeSeen[otherElm] = clkI
                    nonSkipableStateI.add(curFistCommunicationStI)
                else:
                    nonSkipableStateI.add(clkI)

        return nonSkipableStateI

    @staticmethod
    def _insertIntoFsmTransitionTable(builder: HlsNetlistBuilder,
                                      transitionTable: FsmTransitionTable,
                                      predecessors: dict[int, int],
                                      srcStI: int, dstStI: int,
                                      _transEn: HlsNetNodeOut):
        curTransEn = transitionTable[srcStI].get(dstStI, None)
        transEn = builder.buildOrOptional(curTransEn, _transEn)
        if transEn is not None:
            scheduledUnscheduedDummyAsap(transEn, 0)
        transitionTable[srcStI][dstStI] = transEn
        predecessors[dstStI].append(srcStI)

    @staticmethod
    def _iterSortedStateTransitions(stateTransitionTable: dict[int, Optional[HlsNetNodeOut]]):
        # sort and keep default transition at end
        return sorted(stateTransitionTable.items(), key=lambda x: inf if x[1] is None else x[0])

    @classmethod
    def _loadFsmTransitionsFromControllChannels(cls,
                localControlReads: SetList[HlsNetNodeRead],
                controlToStateI: dict[Union[HlsNetNodeRead, HlsNetNodeWrite], int],
                nonSkipableStateI: set[int],
                fsmElm: ArchElementFsm,
                transitionTable: FsmTransitionTable,
                predecessors: dict[int, int]):
        builder = fsmElm.builder
        # for every loop reenter backedge create a jump back to state where loop header is
        for r in localControlReads:
            r: HlsNetNodeRead
            w: HlsNetNodeWrite = r.associatedWrite
            assert w in fsmElm.subNodes, r
            srcStI = controlToStateI[w]
            dstStI = controlToStateI[r]
            # :note: existence of channel is a guidance for this algorithm
            #     the jump may not be possible if there is something
            #     which needs to be checked if it is executed between src and dst of the jump
            # :note: jumping should only affect latency, it should never
            #   affect functionality as the functional state is stored in state of channels
            possible = True
            if dstStI >= srcStI:
                # check if there is any state between these two which can not be skipped
                for i in range(srcStI, dstStI):
                    if i in nonSkipableStateI:
                        possible = False
                        break
            else:
                # check that there is no non optional state behind this state
                for i in range(srcStI, len(fsmElm.stages)):
                    if i in nonSkipableStateI:
                        possible = False
                        break

            if not possible:
                continue

            wStEn, _ = fsmElm.getStageEnable(srcStI)
            _transEn = builder.buildIoNodeEnExpr(w.getExtraCondDriver(), w.getSkipWhenDriver(), wStEn)
            cls._insertIntoFsmTransitionTable(builder, transitionTable, predecessors, srcStI, dstStI, _transEn)

    @classmethod
    def _loadFsmTransitionsFromSkipableStates(cls,
                fsmElm: ArchElementFsm,
                transitionTable: FsmTransitionTable,
                predecessors: dict[int, int],
                usedStates:list[int]):
        # iterating states from back, create a transition if which will skip to next
        # state if the state would hot have any effect
        if len(usedStates) <= 1:
            return

        builder = fsmElm.builder
        clkPeriod = fsmElm.netlist.normalizedClkPeriod
        # stateSkipCondition: dict[int, Optional[HlsNetNodeOut]] = {}
        for clkI in reversed(usedStates):
            # state can be skipped if all nodes with side effect are known to be be disabled or
            # there are not any and the outputs of nodes defined in this state are not used later
            # (or later use is skipped as well)
            nodes = fsmElm.stages[clkI]
            _clkWindowEnd = clkWindowEnd(clkI, clkPeriod)
            hasUseAfter = False
            for n in nodes:
                if isinstance(n, HlsNetNodeExplicitSync) and n.skipWhen is None:
                    hasUseAfter = True
                    break

                for o, uses in zip(n._outputs, n.usedBy):
                    if HdlType_isVoid(o._dtype):
                        continue
                    for u in uses:
                        u: HlsNetNodeIn
                        useTime = u.obj.scheduledIn[u.in_i]
                        if useTime > _clkWindowEnd:
                            hasUseAfter = True
                            break
                if hasUseAfter:
                    break

            if not hasUseAfter:
                andOfAllSkipWhens = None
                for n in nodes:
                    if isinstance(n, HlsNetNodeExplicitSync):
                        sw = n.getSkipWhenDriver()
                        assert sw is not None, n
                        andOfAllSkipWhens = builder.buildAndOptional(andOfAllSkipWhens, sw)
                if andOfAllSkipWhens is None:
                    thisStSkipKnownWhen = 0
                else:
                    scheduledUnscheduedDummyAsap(andOfAllSkipWhens, 0)
                    thisStSkipKnownWhen = andOfAllSkipWhens.obj.scheduledOut[andOfAllSkipWhens.out_i] // clkPeriod

                # propagate all exiting transitions to all predecessor if transition conditions allow it
                for predClkI in sorted(predecessors[clkI], key=lambda clkI:-1 if clkI is None else clkI):
                    if predClkI is None:
                        continue
                    predClkI: int
                    if predClkI < thisStSkipKnownWhen:
                        # can not propagate transition because the value is not resolved in predClkI yet
                        continue

                    for sucClkI, toSucJumpEn in sorted(transitionTable[clkI].items(), key=lambda x: x[0]):
                        if toSucJumpEn is not None and predClkI < toSucJumpEn.obj.scheduledOut[toSucJumpEn.out_i] // clkPeriod:
                            # can not propagate transition because the value is not resolved in predClkI yet
                            continue
                        toSucJumpEnForPred = builder.buildAndOptional(andOfAllSkipWhens, toSucJumpEn)
                        if toSucJumpEnForPred is not None:
                            scheduledUnscheduedDummyAsap(toSucJumpEnForPred, 0)

                        cls._insertIntoFsmTransitionTable(builder, transitionTable, predecessors, predClkI, sucClkI, toSucJumpEnForPred)

    @classmethod
    def _resolveTranstitionTableFromLoopControlChannels(cls,
                localControlReads: SetList[HlsNetNodeRead],
                controlToStateI: dict[Union[HlsNetNodeRead, HlsNetNodeWrite], int],
                nonSkipableStateI: set[int],
                fsmElm: ArchElementFsm,
                usedStates:list[int]):
        """
        Extract FSM transition table from loop control channel conditions
        """

        transitionTable: FsmTransitionTable = {}

        # initialize transition table to always jump to next state
        predecessors: dict[int, int] = {dstClkI: SetList() for dstClkI in usedStates}
        prev = None
        for isLast, clkI in iter_with_last(usedStates):
            transitionTable[prev] = {clkI: None}  # jump to next by default
            predecessors[clkI].append(prev)
            if isLast:
                transitionTable[clkI] = {usedStates[0]: None}  # jump back to start by default
                predecessors[usedStates[0]].append(clkI)

            prev = clkI

        cls._loadFsmTransitionsFromControllChannels(localControlReads, controlToStateI, nonSkipableStateI,
                                                     fsmElm, transitionTable, predecessors)
        cls._loadFsmTransitionsFromSkipableStates(fsmElm, transitionTable, predecessors, usedStates)
        # [todo] use state transitions to prune values used in states
        cls._buildHlsNetNodeFsmStateWrites(usedStates, fsmElm, transitionTable)

    @classmethod
    def _buildHlsNetNodeFsmStateWrites(cls, usedStates: list[int],
                                      fsmElm: ArchElementFsm, transitionTable: FsmTransitionTable):
        builder = fsmElm.builder
        clkPeriod = fsmElm.netlist.normalizedClkPeriod

        for clkI in usedStates:
            stateTransitionTable = transitionTable[clkI]
            stNextWrite = HlsNetNodeFsmStateWrite(fsmElm.netlist)
            t = clkWindowEnd(clkI, clkPeriod)
            stNextWrite.assignRealization(EMPTY_OP_REALIZATION)
            stNextWrite._setScheduleZeroTimeSingleClock(t)
            fsmElm._addNodeIntoScheduled(clkI, stNextWrite)
            defaultJumpSeen = False
            syncNode = (fsmElm, clkI)
            for nextClkI, stJumpEn in cls._iterSortedStateTransitions(stateTransitionTable):
                stJumpEn: Optional[HlsNetNodeOut]
                stJumpEnInPort = stNextWrite._addInput(f"clk{nextClkI:d}", addDefaultScheduling=True)
                stNextWrite.portToNextStateId[stJumpEnInPort] = nextClkI
                if stJumpEn is None:
                    assert not defaultJumpSeen, ("FSM may contain only a single unconditional jump from each state",
                                                 fsmElm, clkI, stateTransitionTable)
                    defaultJumpSeen = True
                    stJumpEn = builder.buildConstBit(1)

                scheduleUnscheduledControlLogic(syncNode, stJumpEn)
                stJumpEn.connectHlsIn(stJumpEnInPort)

    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx) -> PreservedAnalysisSet:
        stateEncoding: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        changed = False
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if isinstance(elm, ArchElementFsm):
                self._detectStateTransitions(elm, stateEncoding.usedStates[elm])
                changed = True

        if changed:
            ArchElementDCE(netlist, netlist.subNodes, None)
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()

