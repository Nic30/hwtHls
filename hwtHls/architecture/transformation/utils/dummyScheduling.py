from hwt.hdl.operatorDefs import HwtOps
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.scheduler.scheduler import asapSchedulePartlyScheduled, \
    alapSchedulePartlyScheduled
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


def setUnscheduledNodeRealizationToCombForSyncLogic(n: HlsNetNode):
    """
    This function is called for newly generated synchronization logic nodes.
    It performs an initialization required for scheduling.
    """
    assert isinstance(n, HlsNetNodeConst) or (
    isinstance(n, HlsNetNodeOperator) and n.operator in (
    HwtOps.AND, HwtOps.OR, HwtOps.XOR, HwtOps.EQ, HwtOps.NE, HwtOps.NOT, HwtOps.TERNARY, HwtOps.INDEX, HwtOps.CONCAT)), n
    n.assignRealization(OpRealizationMeta(mayBeInFFStoreTime=True))
    return True


def scheduleUnscheduledControlLogic(syncNode: ArchSyncNodeTy, out: HlsNetNodeOut) -> SchedTime:
    """
    Apply default scheduling for newly generated nodes.
    """
    assert out is not None
    elm, clkI = syncNode
    clkPeriod = elm.netlist.normalizedClkPeriod
    beginOfFirstClk = clkI * clkPeriod

    newlyScheduledNodes = asapSchedulePartlyScheduled(
        out, setUnscheduledNodeRealizationToCombForSyncLogic, beginOfFirstClk=beginOfFirstClk)
    for n in newlyScheduledNodes:
        _clkI = indexOfClkPeriod(n.scheduledZero, clkPeriod)
        # assert clkI == _clkI, ("all nodes must be in the same clk window", clkI, _clkI, n, n.scheduledZero)
        elm._addNodeIntoScheduled(clkI, n, allowNewClockWindow=True)

    return out.obj.scheduledOut[out.out_i]


def scheduleUncheduledDummyAlap(out: HlsNetNodeOut, alapTime: SchedTime, allowNewClockWindow:bool=False):
    """
    :param alapTime: end of last clk window
    """
    schedOut = out.obj.scheduledOut
    if schedOut is None:
        alapSchedulePartlyScheduled(out, setUnscheduledNodeRealizationToCombForSyncLogic, alapTime, allowNewClockWindow)

def scheduledUnscheduedDummyAsap(out: HlsNetNodeOut, beginOfFirstClk: SchedTime):
    schedOut = out.obj.scheduledOut
    if schedOut is None:
        clkPeriod = out.obj.netlist.normalizedClkPeriod
        newlyScheduledNodes = asapSchedulePartlyScheduled(out, setUnscheduledNodeRealizationToCombForSyncLogic, beginOfFirstClk)
        for n in newlyScheduledNodes:
            _clkI = indexOfClkPeriod(n.scheduledZero, clkPeriod)
            # assert clkI == _clkI, ("all nodes must be in the same clk window", clkI, _clkI, n, n.scheduledZero)
            n.parent._addNodeIntoScheduled(_clkI, n, allowNewClockWindow=True)

