from typing import Type

from hwt.interfaces.std import VectSignal, Handshaked, VldSynced, RdSynced
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, \
    HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from hwt.synthesizer.hObjList import HObjList
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist


class ReadOrDefaultUnit(Unit):

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self) -> None:
        self.dataIn = VectSignal(self.DATA_WIDTH)
        self.dataOut = VectSignal(self.DATA_WIDTH)._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        d = dataIn.read()
        if not d.vld:
            d = 0
        dataOut.write(d)
        """
        b = netlist.builder
        r = HlsNetNodeRead(netlist, self.dataIn)
        netlist.inputs.append(r)
        r = r._outputs[0]
        rVld = b.buildReadSync(r)
        t = r._dtype
        
        mux = b.buildMux(r._dtype, (r, rVld, t.from_py(0)))
        w = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])

    def _impl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class ReadNonBlockingOrDefaultUnit(ReadOrDefaultUnit):

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        d = dataIn.read_nb()
        if not d.vld:
            d = 0
        dataOut.write(d)
        """
        b = netlist.builder
        r = HlsNetNodeRead(netlist, self.dataIn)
        netlist.inputs.append(r)
        r = r._outputs[0]
        rVld = b.buildReadSync(r)
        t = r._dtype
        sync = HlsNetNodeExplicitSync(netlist, t)
        sync.add_control_skipWhen(b.buildNot(rVld))
        netlist.nodes.append(sync)
        link_hls_nodes(r, sync._inputs[0])
        
        mux = b.buildMux(r._dtype, (sync._outputs[0], rVld, t.from_py(0)))
        w = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])


class ReadOrDefaultUnitHs(ReadOrDefaultUnit):

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.dataIn = Handshaked()
            self.dataOut = Handshaked()._m()


class ReadNonBlockingOrDefaultUnitHs(ReadNonBlockingOrDefaultUnit):

    def _declr(self) -> None:
        ReadOrDefaultUnitHs._declr(self)


class ReadAnyHsUnit(ReadOrDefaultUnit):

    def _config(self) -> None:
        ReadOrDefaultUnit._config(self)
        self.INPUT_CNT = Param(3)

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.dataIn = HObjList(Handshaked() for _ in range(self.INPUT_CNT))
            self.dataOut = Handshaked()._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        d = None
        for i in dataIn
            if i.valid:
                d = i.read()
                break
        if d is not None:
            dataOut.write(d)
        """
        b = netlist.builder
        inputs = []
        for i in self.dataIn:
            r = HlsNetNodeRead(netlist, i)
            netlist.inputs.append(r)
            r = r._outputs[0]
            rVld = b.buildReadSync(r)
        
            t = r._dtype
            rSync = HlsNetNodeExplicitSync(netlist, t)
            netlist.nodes.append(rSync)
            link_hls_nodes(r, rSync._inputs[0])
        
            inputs.append((r, rSync, rVld))
        HlsNetlistAnalysisPassMirToNetlist._createSyncForAnyInputSelector(
            b, [(rSync, []) for (_, rSync, _) in inputs], b.buildConstBit(1), b.buildConstBit(0))

        # output mux
        muxOps = []
        for _, sync, c in  inputs:
            muxOps.append(sync._outputs[0])
            muxOps.append(c)

        muxOps.append(t.from_py(0))
        mux = b.buildMux(r._dtype, tuple(muxOps))
        w = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])


class HlsNetlistReadSyncTC(SimTestCase):

    def test_ReadOrDefaultUnit(self, cls=ReadOrDefaultUnit, dataIn=range(4), dataOut=list(range(4))):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.dataIn._ag.data.extend(dataIn)
        clkPeriod = freq_to_period(u.CLK_FREQ)

        self.runSim(int(len(dataIn) * clkPeriod))

        res = u.dataOut._ag.data
        self.assertValSequenceEqual(res, dataOut)

    def test_ReadOrDefaultUnitHs(self, cls=ReadOrDefaultUnitHs, dataIn=range(8), dataOut=list(range(8))):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.dataIn._ag.data.extend(dataIn)
        clkPeriod = freq_to_period(u.CLK_FREQ)
        
        self.randomize(u.dataIn)
        self.randomize(u.dataOut)
        
        self.runSim(int((len(dataIn) * 6) * clkPeriod))

        res = u.dataOut._ag.data
        self.assertValSequenceEqual(res, dataOut)

    def test_ReadNonBlockingOrDefaultUnitHs(self,
                                                      cls=ReadNonBlockingOrDefaultUnitHs,
                                                      dataIn=range(8),
                                                      dataOut=[0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 0, 5, 6, 0, 7, 0, 0, 0, 0, 0]):
        self.test_ReadOrDefaultUnitHs(cls, dataIn, dataOut)

    def test_ReadNonBlockingOrDefaultUnit(self):
        self.test_ReadOrDefaultUnit(ReadNonBlockingOrDefaultUnit, dataIn=range(4), dataOut=list(range(4)))

    def test_ReadAnyHsUnit(self, N=4):
        u = ReadAnyHsUnit()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        
        for i, intf in enumerate(u.dataIn):
            self.randomize(intf)
            intf._ag.data.extend(range(i * N, (i + 1) * N))
        self.randomize(u.dataOut)
        
        clkPeriod = freq_to_period(u.CLK_FREQ)
        self.runSim(int((N * u.INPUT_CNT * 3) * clkPeriod))

        res = u.dataOut._ag.data
        self.assertValSequenceEqual(res, [8, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11])


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = ReadAnyHsUnit()
    u.DATA_WIDTH = 32
    u.CLK_FREQ = int(40e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    # suite.addTest(HlsNetlistReadSyncTC('test_NetlistWireUnitRdSynced'))
    suite.addTest(unittest.makeSuite(HlsNetlistReadSyncTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
