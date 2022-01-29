from typing import List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode


def asap(nodes: List[HlsNetNode], clk_period: float):
    """
    As Soon As Possible scheduler
    * The graph must not contain cycles.
    * DFS from outputs, decorate nodes with asap_start,asap_end time.
    """
    try:
        # normal run without checking for cycles
        for o in nodes:
            o.scheduleAsap(clk_period, None)
        return
    except RecursionError:
        pass

    # debug run which will raise an exception containing cycle node ids
    path = UniqList()
    for o in nodes:
        o.scheduleAsap(clk_period, path)

