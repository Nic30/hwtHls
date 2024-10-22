from typing import Optional, Tuple

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, beginOfClkWindow


def insertDummyWriteToImplementSync(parentElm: ArchElement,
                                    time: SchedTime,
                                    name:Optional[str]=None,
                                    writeCls=HlsNetNodeWrite) -> Tuple[HlsNetNodeWrite, HlsNetNodeConst]:
    netlist = parentElm.netlist
    sync = writeCls(netlist, None, name)
    sync.resolveRealization()
    sync._setScheduleZeroTimeSingleClock(time)
    sync._rtlUseReady = sync._rtlUseValid = False

    dummyVal = HlsNetNodeConst(netlist, HVoidOrdering.from_py(None))
    dummyVal.resolveRealization()
    dummyVal._setScheduleZeroTimeSingleClock(time)
    dummyVal._outputs[0].connectHlsIn(sync._inputs[0])

    clkIndex = indexOfClkPeriod(time, netlist.normalizedClkPeriod)
    for n in (sync, dummyVal):
        parentElm.subNodes.append(n)
        parentElm.getStageForClock(clkIndex).append(n)
    return sync, dummyVal


def createBackedgeInClkWindow(parent: ArchElement, clkIndex: int, name: str, dtype: HdlType, channelInitValue=NOT_SPECIFIED)\
        -> Tuple[HlsNetNodeReadBackedge, HlsNetNodeWriteBackedge]:
    netlist = parent.netlist
    # busy if is executed at 0 time
    if channelInitValue is NOT_SPECIFIED:
        channelInitValues = ()
    else:
        channelInitValues = (channelInitValue,)
    regR = HlsNetNodeReadBackedge(netlist, dtype, name=name + "_dst", channelInitValues=channelInitValues)

    regW = HlsNetNodeWriteBackedge(netlist, name=name + "_src")
    clkPeriod = netlist.normalizedClkPeriod
    clkBegin = beginOfClkWindow(clkIndex, clkPeriod)
    clkEnd = clkBegin + clkPeriod - 1
    for c, time in [(regR, clkBegin),
                    (regW, clkEnd)]:
        c: HlsNetNodeReadOrWriteToAnyChannel
        c._isBlocking = False
        c.resolveRealization()
        c._setScheduleZeroTimeSingleClock(time)
        parent._addNodeIntoScheduled(clkIndex, c, allowNewClockWindow=True)

    regW.associateRead(regR)
    regR.getOrderingOutPort().connectHlsIn(
                   regW._addInput("orderingIn", addDefaultScheduling=True))

    if HdlType_isVoid(dtype):
        # create a dummy constant for void data
        c1 = netlist.builder.buildScheduledConstPy(parent, clkIndex, dtype, None)
        c1.connectHlsIn(regW._portSrc)

    return regR, regW
