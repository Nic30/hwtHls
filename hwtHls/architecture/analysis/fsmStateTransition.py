from itertools import islice
from math import inf
from typing import Union, Optional, Literal

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.analysis.hlsAndRtlNetlistAnalysisPass import HlsAndRtlNetlistAnalysisPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduledUnscheduedDummyAsap
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel, LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, clkWindowEnd, \
    SchedTime

# items are Ored to obtain final condition
FsmTransitionEnCondItem = Union[
        HlsNetNodeOut,
        tuple[Literal[HwtOps.AND, HlsNetNodeOut, ...]],
        # args for builder.buildIoNodeEnExpr(extraCond, skipWhen, En)
        tuple[Optional[HlsNetNodeOut], Optional[HlsNetNodeOut], Optional[HlsNetNodeOut]],
    ]
FsmTransitionEnCond = SetList[FsmTransitionEnCondItem]

# :note: after HlsAndRtlNetlistPassFsmStateNextWriteConstruction the FsmTransitionEnCond is converted to HlsNetNodeOut
FsmTransitionTable = dict[int,  # src clk index of state
                          list[tuple[int,  # dst clk index of state
                                     Union[None,  # None represens always enabled transition
                                           HlsNetNodeOut,
                                           FsmTransitionEnCond]]]]


class HlsAndRtlNetlistAnalysisPassFsmStateTransition(HlsAndRtlNetlistAnalysisPass):
    """
    Recognize ArchElementFsm states and resolve its encoding to minimize number of bits used
    for the state.
    """

    def __init__(self) -> None:
        HlsAndRtlNetlistAnalysisPass.__init__(self)
        # :note: None represents the default jump if any other jump was not taken
        #   the jump conditions should be one-hot encoded, but for convidient we sort them lower to higher dst
        #   before further processing
        self.fsmTransitionTables: dict["ArchElementFsm", FsmTransitionTable] = {}

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
    def _insertIntoFsmTransitionTable(transitionTable: FsmTransitionTable,
                                      predecessors: dict[int, int],
                                      srcStI: int, dstStI: int,
                                      _transEn: Optional[HlsNetNodeOut]):
        if _transEn is None:
            transitionTable[srcStI][dstStI] = None
        else:
            curTransEn = transitionTable[srcStI].get(dstStI, NOT_SPECIFIED)
            if curTransEn is None:
                # already unconditional transition
                return
            elif curTransEn is NOT_SPECIFIED:
                curTransEn = transitionTable[srcStI][dstStI] = SetList()

            curTransEn.append(_transEn)
            predecessors[dstStI].append(srcStI)

    @classmethod
    def materializeTransitionCondition(cls, builder: HlsNetlistBuilder, condition: FsmTransitionEnCond) -> Optional[HlsNetNodeOut]:
        if isinstance(condition, tuple):
            if condition[0] is HwtOps.AND:
                c = tuple(cls.materializeTransitionCondition(builder, _c) for _c in islice(condition, 1, None))
                return builder.buildAndVariadic(c)
            else:
                assert len(condition) == 3
                ec, sw, en = condition
                return builder.buildIoNodeEnExpr(ec, sw, en)
        elif isinstance(condition, HlsNetNodeOut):
            return condition
        else:
            transEn = None
            for c in condition:
                _transEn = cls.materializeTransitionCondition(builder, c)
                transEn = builder.buildOrOptional(transEn, _transEn)
                if transEn is not None:
                    scheduledUnscheduedDummyAsap(transEn, 0)
            return transEn

    @staticmethod
    def _sortedStateTransitions(stateTransitionTable: dict[int, Optional[HlsNetNodeOut]]):
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
            _transEn = (w.getExtraCondDriver(), w.getSkipWhenDriver(), wStEn)
            cls._insertIntoFsmTransitionTable(transitionTable, predecessors, srcStI, dstStI, _transEn)

    @classmethod
    def _getMaxDefTime(cls, v: list[FsmTransitionEnCondItem]) -> Optional[SchedTime]:
        if v is None or isinstance(v, HOperatorDef):
            return None
        elif isinstance(v, HlsNetNodeOut):
            v: HlsNetNodeOut
            return v.obj.scheduledOut[v.out_i]
        else:
            t: Optional[SchedTime] = None
            for o in v:
                newT = cls._getMaxDefTime(o)
                if t is None:
                    t = newT
                elif newT is not None:
                    t = max(t, newT)
            return t

    @classmethod
    def _loadFsmTransitionsFromSkipableStates(cls,
                fsmElm: ArchElementFsm,
                transitionTable: FsmTransitionTable,
                predecessors: dict[int, int],
                usedStates:list[int]):
        # iterating states from back, create a transition condition which will skip the next
        # state if the state would not have any effect and jump directly to successor
        if len(usedStates) <= 1:
            return

        clkPeriod = fsmElm.netlist.normalizedClkPeriod
        # stateSkipCondition: dict[int, Optional[HlsNetNodeOut]] = {}
        for clkI in reversed(usedStates):
            # state can be skipped if all nodes with side effect are known to be be disabled or
            # there are not any and the outputs of nodes defined in this state are not used later
            # (or later use is skipped as well)
            inStateNodes = fsmElm.stages[clkI]
            _clkWindowEnd = clkWindowEnd(clkI, clkPeriod)
            hasUseAfter = False
            for n in inStateNodes:
                if isinstance(n, HlsNetNodeExplicitSync) and n.skipWhen is None:
                    hasUseAfter = True
                    break

                # check for implicit registers after this clock window
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
                    # can not skip because there is some implicit register which must be loaded
                    break

            if hasUseAfter:
                continue
            
            # resolve condition to skip this state
            andOfAllSkipWhens: list[FsmTransitionEnCondItem] = []
            for n in inStateNodes:
                if isinstance(n, HlsNetNodeExplicitSync):
                    sw = n.getSkipWhenDriver()
                    assert sw is not None, n
                    if sw not in andOfAllSkipWhens:
                        andOfAllSkipWhens.append(sw)

            if andOfAllSkipWhens:
                thisStSkipKnownWhen = cls._getMaxDefTime(andOfAllSkipWhens) // clkPeriod
            else:
                thisStSkipKnownWhen = 0

            # propagate all exiting transitions to all predecessor if transition conditions allow it
            for predClkI in sorted(predecessors[clkI], key=lambda clkI:-1 if clkI is None else clkI):
                if predClkI is None:
                    continue
                predClkI: int
                if predClkI < thisStSkipKnownWhen:
                    # can not propagate transition because the value is not resolved in predClkI yet
                    continue

                for sucClkI, toSucJumpEn in sorted(transitionTable[clkI].items(), key=lambda x: x[0]):
                    if toSucJumpEn and predClkI < cls._getMaxDefTime(toSucJumpEn) // clkPeriod:
                        # can not propagate transition because the value is not resolved in predClkI yet
                        continue

                    # toSucJumpEnForPred = builder.buildAndOptional(andOfAllSkipWhens, toSucJumpEn)
                    if toSucJumpEn is None:
                        _andOfAllSkipWhens = andOfAllSkipWhens
                    else:
                        _andOfAllSkipWhens = andOfAllSkipWhens + [toSucJumpEn, ]

                    if _andOfAllSkipWhens:
                        if len(_andOfAllSkipWhens) == 1:
                            toSucJumpEnForPred = _andOfAllSkipWhens[0]
                        else:
                            toSucJumpEnForPred = (HwtOps.AND, *_andOfAllSkipWhens)
                    else:
                        toSucJumpEnForPred = None

                    cls._insertIntoFsmTransitionTable(transitionTable, predecessors, predClkI, sucClkI, toSucJumpEnForPred)

    @classmethod
    def _resolveTranstitionTableFromLoopControlChannels(cls,
                localControlReads: SetList[HlsNetNodeRead],
                controlToStateI: dict[Union[HlsNetNodeRead, HlsNetNodeWrite], int],
                nonSkipableStateI: set[int],
                fsmElm: ArchElementFsm,
                usedStates:list[int]) -> FsmTransitionTable:
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
        return transitionTable
    
    @classmethod
    def _pruneRedundantDefaultJumps(cls, transitionTable: FsmTransitionTable):
        """
        if state have multiple default jumps use only the latest one and assert that dst states are continuous sequence
        """
        for transitions in transitionTable.values():
            defaults = sorted(dstI for dstI, cond in transitions.items() if cond is None)
            if len(defaults) > 1:
                for dstI in defaults[:-1]:
                    transitions.pop(dstI)

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        """
        Recognize FSM transitions from control channels and other nodes placed in :class:`ArchElementFsm`
        
        Detect the state propagation logic and resolve how to replace it with a state bit
        * state bit will be stored as a register in this FSM
        * read will read this bit
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
        stateEncoding: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        fsmTransitionTables = self.fsmTransitionTables
        for fsmElm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if not isinstance(fsmElm, ArchElementFsm):
                continue

            usedStates = stateEncoding.usedStates[fsmElm]
            localControlReads, controlToStateI = self._collectLoops(fsmElm)
            nonSkipableStateI = self._collectStatesWhichCanNotBeSkipped(fsmElm)
            transTable = self._resolveTranstitionTableFromLoopControlChannels(
                localControlReads, controlToStateI, nonSkipableStateI, fsmElm, usedStates)
            self._pruneRedundantDefaultJumps(transTable)
            assert fsmElm not in fsmTransitionTables, fsmElm
            fsmTransitionTables[fsmElm] = {
                srcSt: self._sortedStateTransitions(stateTransitionTable)
                for srcSt, stateTransitionTable in transTable.items()}

