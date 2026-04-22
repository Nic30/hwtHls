from typing import Optional

from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.analysis.fsmStateTransition import HlsAndRtlNetlistAnalysisPassFsmStateTransition, \
    FsmTransitionTable
from hwtHls.architecture.transformation.dce import ArchElementDCE
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import clkWindowEnd
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsAndRtlNetlistPassFsmStateNextWriteConstruction(HlsAndRtlNetlistPass):
    """
    Construct :class:`HlsNetNodeFsmStateWrite` in each state of FSM.
    """

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
            for stateTableItemIndex, (nextClkI, stJumpEn) in enumerate(stateTransitionTable):
                if stJumpEn is None or isinstance(stJumpEn, HlsNetNodeOut):
                    pass
                else:
                    assert isinstance(stJumpEn, list), stJumpEn
                    stJumpEn = HlsAndRtlNetlistAnalysisPassFsmStateTransition.materializeTransitionCondition(builder, stJumpEn)
                    stateTransitionTable[stateTableItemIndex] = stJumpEn

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
        changed = False
        stateEncoding: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        transitionTables: HlsAndRtlNetlistAnalysisPassFsmStateTransition = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassFsmStateTransition)
        for fsmElm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if not isinstance(fsmElm, ArchElementFsm):
                continue

            usedStates = stateEncoding.usedStates[fsmElm]
            transitionTable = transitionTables.fsmTransitionTables[fsmElm]
            # [todo] use state transitions to prune values used in states
            self._buildHlsNetNodeFsmStateWrites(usedStates, fsmElm, transitionTable)
            changed = True

        netlist.flagHasStageControlLowered = True
        if changed:
            ArchElementDCE(netlist, netlist.subNodes, None)
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            pa.add(HlsAndRtlNetlistAnalysisPassFsmStateTransition)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()

    @override
    def invalidate(self, netlist: HlsNetlistCtx):
        netlist.flagHasStageControlLowered = False

