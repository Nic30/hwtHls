from typing import Optional

from hwt.hdl.const import HConst
from hwt.pyUtils.setDeque import SetDeque
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimStateT
from hwtHls.netlist.nodes.ports import HlsNetNodeOut


class HlsNetlistSimHandler():

    def _updatePortValue(self, o: Optional[HlsNetNodeOut], newValue: HConst, state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"]):
        if o is None:
            return
        prev = state[o]
        if prev == newValue:
            return
        state[o] = newValue
        for user in o.obj.usedBy[o.out_i]:
            worklist.append(user.obj)

    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        """
        Initialize the state before simulation start.
        """
        for o in node._outputs:
            state[o] = o._dtype.from_py(None)

    def simCombStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        """
        Update combinational outputs from inputs and agent state.
        
        :note: if not overriden this method is never executed
        """
        pass

    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        """
        Finalize internal state update after all combinational signals in circuit are resolved.
        
        :attention: This should never update values of outputs (state), it should update only internal state of node
                    and add node to worklist if state changed to update values of outputs
        :note: if not overriden this method is never executed
        """
        pass

