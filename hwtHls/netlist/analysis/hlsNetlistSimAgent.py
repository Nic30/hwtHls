from typing import Sequence

from hwt.pyUtils.setDeque import SetDeque
from hwtHls.netlist.analysis.hlsNetlistSimHandler import HlsNetlistSimHandler
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimScalarInputOrOutputWords, \
    HlsNetlistSimStateT
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class HlsNetlistSimAgent(HlsNetlistSimHandler):
    """
    HlsNetlist simulation agent (UVM-like) which manages data flow between simulation
    and rest of the test code.
    
    :note: This object typically manages multiple HlsNetNodes because it is build for IO port,
        and io port may be accessed by multiple HlsNetNodes.
    :param _enabled: specifies if the agent should pass data to/from simulation. Note _enabled=False
                     means that some output values still may be updated to notify circuit
                     about the fact that the no data is transferred.
    """

    def __init__(self,
                 ioProxy: "IoProxyScalar",
                 data: HlsNetlistSimScalarInputOrOutputWords):
        self.ioProxy = ioProxy
        self.data = data
        self._enabled = True

    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        HlsNetlistSimHandler.simInit(self, sim, state, worklist, node)
        worklist.append(node)

    def _checkNodePortsSupported(self, node: HlsNetNode, supportedInputs: tuple[HlsNetNodeIn], supportedOutputs: Sequence[HlsNetNodeOut]):
        implementedInPortCnt = sum(int(p is not None and not HdlType_isVoid(p.obj.dependsOn[p.in_i]._dtype))
                                   for p in supportedInputs)
        voidInPortCnt = sum(HdlType_isVoid(d._dtype) for d in node.dependsOn)
        assert len(node._inputs) - voidInPortCnt == implementedInPortCnt, node._inputs
        implementedOutPortCnt = sum(int(p is not None and not HdlType_isVoid(p._dtype)) for p in supportedOutputs)
        voidOutPortCnt = sum(HdlType_isVoid(o._dtype) for o in node._outputs)
        assert len(node._outputs) - voidOutPortCnt == implementedOutPortCnt, node._outputs
