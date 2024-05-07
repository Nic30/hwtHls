from typing import Optional, Tuple

from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod


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
    link_hls_nodes(dummyVal._outputs[0], sync._inputs[0])

    clkIndex = indexOfClkPeriod(time, netlist.normalizedClkPeriod)
    for n in (sync, dummyVal):
        parentElm._subNodes.append(n)
        parentElm.getStageForClock(clkIndex).append(n)
    return sync, dummyVal
