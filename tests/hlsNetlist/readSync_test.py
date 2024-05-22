#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hwIOs.std import HwIOVectSignal, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.hObjList import HObjList
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class ReadOrDefaultHwModule(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def hwDeclr(self) -> None:
        self.dataIn = HwIOVectSignal(self.DATA_WIDTH)
        self.dataOut = HwIOVectSignal(self.DATA_WIDTH)._m()

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
        w = HlsNetNodeWrite(netlist, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])

    def hwImpl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class ReadNonBlockingOrDefaultHwModule(ReadOrDefaultHwModule):

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
        r._isBlocking = False
        netlist.inputs.append(r)
        r = r._outputs[0]
        rVld = b.buildReadSync(r)
        t = r._dtype

        mux = b.buildMux(t, (r, rVld, t.from_py(0)))
        w = HlsNetNodeWrite(netlist, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])


class ReadOrDefaultHwModuleHs(ReadOrDefaultHwModule):

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()


class ReadNonBlockingOrDefaultHwModuleHs(ReadNonBlockingOrDefaultHwModule):

    def hwDeclr(self) -> None:
        ReadOrDefaultHwModuleHs.hwDeclr(self)


class ReadAnyHsHwModule(ReadOrDefaultHwModule):

    def hwConfig(self) -> None:
        ReadOrDefaultHwModule.hwConfig(self)
        self.INPUT_CNT = HwParam(3)

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataIn = HObjList(HwIODataRdVld() for _ in range(self.INPUT_CNT))
            self.dataOut = HwIODataRdVld()._m()

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
        w = HlsNetNodeWrite(netlist, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])


class HlsNetlistReadSyncTC(SimTestCase):

    def test_ReadOrDefaultHwModule(self, cls=ReadOrDefaultHwModule, dataIn=range(4), dataOut=list(range(4))):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.dataIn._ag.data.extend(dataIn)
        clkPeriod = freq_to_period(dut.CLK_FREQ)

        self.runSim(int(len(dataIn) * clkPeriod))

        res = dut.dataOut._ag.data
        self.assertValSequenceEqual(res, dataOut)

    def test_ReadOrDefaultHwModuleHs(self, cls=ReadOrDefaultHwModuleHs, dataIn=range(8), dataOut=list(range(8))):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.dataIn._ag.data.extend(dataIn)
        clkPeriod = freq_to_period(dut.CLK_FREQ)

        self.randomize(dut.dataIn)
        self.randomize(dut.dataOut)

        self.runSim(int((len(dataIn) * 6) * clkPeriod))

        res = dut.dataOut._ag.data
        self.assertValSequenceEqual(res, dataOut)

    def test_ReadNonBlockingOrDefaultHwModuleHs(self,
                                            cls=ReadNonBlockingOrDefaultHwModuleHs,
                                            dataIn=range(8),
                                            dataOut=[0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 0, 5, 6, 0, 7, 0, 0, 0, 0, 0]):
        self.test_ReadOrDefaultHwModuleHs(cls, dataIn, dataOut)

    def test_ReadNonBlockingOrDefaultHwModule(self):
        self.test_ReadOrDefaultHwModule(ReadNonBlockingOrDefaultHwModule, dataIn=range(4), dataOut=list(range(4)))

    def test_ReadAnyHsHwModule(self, N=4):
        dut = ReadAnyHsHwModule()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        for i, hwIO in enumerate(dut.dataIn):
            self.randomize(hwIO)
            hwIO._ag.data.extend(range(i * N, (i + 1) * N))
        self.randomize(dut.dataOut)

        clkPeriod = freq_to_period(dut.CLK_FREQ)
        self.runSim(int((N * dut.INPUT_CNT * 3) * clkPeriod))

        res = dut.dataOut._ag.data
        self.assertValSequenceEqual(res, [8, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11])


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = ReadNonBlockingOrDefaultHwModule()
    # m.DATA_WIDTH = 32
    m.CLK_FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistReadSyncTC("test_ReadNonBlockingOrDefaultHwModuleHs")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistReadSyncTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
