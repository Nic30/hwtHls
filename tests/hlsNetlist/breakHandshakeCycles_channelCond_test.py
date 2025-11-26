#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.threadFromNetlist import HlsThreadFromNetlist
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.explicitSync import createOrderingLink
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.hlsNetlist.wire_test import HlsNetlistWireTC


def createPredSucPair(netlist: HlsNetlistCtx,
                                 parentForWrite:ArchElement,
                                 parentForRead: ArchElement,
                                 name: str, srcV: HlsNetNodeOut)\
        ->tuple[HlsNetNodeWrite, HlsNetNodeRead, HlsNetNodeOut]:
    ioProxy = IoProxyScalar(None, None, dtype=srcV._dtype)
    r = HlsNetNodeRead(netlist, ioProxy, ioProxy.interface, srcV._dtype, name=name + "_dst")
    w = HlsNetNodeWrite(netlist, ioProxy, ioProxy.interface, name=name + "_src")
    parentForRead.addNode(r)
    parentForWrite.addNode(w)
    srcV.connectHlsIn(w._portSrc)
    w.associateRead(r)
    createOrderingLink(w, r)

    return w, r, r._portDataOut


class ReadSplitCntrlAndDataTo2ChannelsWriteOutHwModule(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        with self._hwParamsShared():
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()

    def main(self, netlist: HlsNetlistCtx):
        """
        read dataIn, split it to validNB and data, pass it trough separate channels
        and write it to dataOut if original validNB
        """
        elm = ArchElementPipeline(netlist, "p0", "p0_")
        netlist.addNode(elm)
        builder: HlsNetlistBuilder = elm.builder
        r = HlsNetNodeRead(netlist, IoProxyScalar(None, self.dataIn), self.dataIn)
        elm.addNode(r)
        cW, cR, cRout = createPredSucPair(netlist, elm, elm, "c", r.getValidNB())
        dW, dR, dRout = createPredSucPair(netlist, elm, elm, "d", r._portDataOut)
        dW.addControlSerialSkipWhen

        w = HlsNetNodeWrite(netlist, IoProxyScalar(None, self.dataOut), self.dataOut)
        elm.addNode(w)

        dRout.connectHlsIn(w._portSrc)
        nC = builder.buildNot(cR.getValidNB())
        w.addControlSerialSkipWhen(nC)
        dR.addControlSerialSkipWhen(nC)

    def hwImpl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.main))
        hls.compile()


class BreakHandshakeCycles_channelCond_TC(SimTestCase):

    def test_ReadSplitCntrlAndDataTo2ChannelsWriteOutHwModule(self):
        HlsNetlistWireTC.test_HlsNetlistWireHwModule(self, ReadSplitCntrlAndDataTo2ChannelsWriteOutHwModule, extraTime=1)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = ReadSplitCntrlAndDataTo2ChannelsWriteOutHwModule()
    m.DATA_WIDTH = 32
    m.CLK_FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BreakHandshakeCycles_channelCond_TC("test_NetlistWireHwModuleRdSynced")])
    suite = testLoader.loadTestsFromTestCase(BreakHandshakeCycles_channelCond_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
