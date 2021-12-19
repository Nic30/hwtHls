from typing import List, Optional

from hwtHls.clk_math import start_of_next_clk_period
from hwtHls.netlist.nodes.io import HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwt.pyUtils.uniqList import UniqList





def asap(outputs: List[HlsWrite], clk_period: float):
    """
    As Soon As Possible scheduler
    * The graph must not contain cycles.
    * DFS from outputs, decorate nodes with asap_start,asap_end time.
    """
    try:
        # normal run without checking for cycles
        for o in outputs:
            o.scheduleAsap(clk_period, None)
        return
    except RecursionError:
        pass

    # debug run which will raise an exception containing cycle node ids
    path = UniqList()
    for o in outputs:
        o.scheduleAsap(clk_period, path)

