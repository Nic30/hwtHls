#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.interfaces.std import VectSignal, Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class ReadOrDefaultUnit(Unit):

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self) -> None:
        self.dataIn = VectSignal(self.DATA_WIDTH)
        self.dataOut = VectSignal(self.DATA_WIDTH)._m()

    @hlsBytecode
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

    @hlsBytecode
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
        sync.addControlSerialSkipWhen(b.buildNot(rVld))
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

    @hlsBytecode
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
        anyPrevVld = None
        for last, i in iter_with_last(self.dataIn):
            r = HlsNetNodeRead(netlist, i)
            netlist.inputs.append(r)
            if not last:
                r.setNonBlocking()
            if anyPrevVld:
                r.addControlSerialExtraCond(b.buildNot(anyPrevVld))
                r.addControlSerialSkipWhen(anyPrevVld)

            r = r._outputs[0]
            rVld = b.buildReadSync(r)
            if anyPrevVld is None:
                anyPrevVld = rVld
            else:
                _rVld = b.buildAnd(b.buildNot(anyPrevVld), rVld)
                anyPrevVld = b.buildOr(anyPrevVld, rVld)
                rVld = _rVld
            inputs.append((rVld, r))

        # output mux
        muxOps = []
        for c, v in  inputs:
            muxOps.append(v)
            muxOps.append(c)

        t = inputs[0][1]._dtype
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
    from hwtHls.platform.platform import HlsDebugBundle
    u = ReadAnyHsUnit()
    # u.DATA_WIDTH = 32
    u.CLK_FREQ = int(40e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReadSyncTC("test_ReadNonBlockingOrDefaultUnitHs")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReadSyncTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
