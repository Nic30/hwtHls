from typing import Sequence
import unittest

from hwt.hdl.types.hdlType import HdlType
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform


class AbstractHlsNetlistTC(unittest.TestCase):

    def getTestNetlist(self, freq=int(1e6)) -> HlsNetlistCtx:
        return HlsNetlistCtx(VirtualHlsPlatform(), None, freq, "test", "test", {}, "")

    def generateTestNetlistInputsFromCnt(self, netlist: HlsNetlistCtx, cnt: int, t: HdlType) -> list[HlsNetNodeOut]:
        ioProxy = IoProxyScalar(None, None)
        inputs = [
            HlsNetNodeRead(netlist, ioProxy, ioProxy.interface, t, name=f"i{i:d}")._portDataOut
            for i in range(cnt)
        ]
        netlist.addNodes([i.obj for i in inputs])
        return inputs

    def generateTestNetlistInputsFromTypes(self, netlist: HlsNetlistCtx, types: list[HdlType]) -> list[HlsNetNodeOut]:
        ioProxy = IoProxyScalar(None, None)
        inputs = [
            HlsNetNodeRead(netlist, ioProxy, ioProxy.interface, t, f"i{i:d}")._portDataOut
            for i, t in enumerate(types)
        ]
        netlist.addNodes([i.obj for i in inputs])
        return inputs

    def generateTestNetlistOutputs(self, netlist, outputPorts: Sequence[HlsNetNodeOut]) -> list[HlsNetNodeWrite]:
        ioProxy = IoProxyScalar(None, None)
        outputNodes: list[HlsNetNodeWrite] = []
        for oI, op in enumerate(outputPorts):
            o = HlsNetNodeWrite(netlist, ioProxy, ioProxy.interface, name=f"o{oI}")
            netlist.subNodes.append(o)
            op.connectHlsIn(o._portSrc)
            outputNodes.append(o)
        return outputNodes
