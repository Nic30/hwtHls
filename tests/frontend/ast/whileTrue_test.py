#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.ast.whileTrue import WhileTrueWriteCntr0, WhileTrueWriteCntr1, \
    WhileSendSequence0, WhileSendSequence1, WhileSendSequence2, WhileSendSequence3, \
    WhileSendSequence4


class HlsAstWhileTrue_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def test_WhileTrueWriteCntr0(self, cls=WhileTrueWriteCntr0, ref=[0, 1, 2, 3]):
        dut = cls()
        # debugFilter={*HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSignalNamesToSync}
        debugFilter = HlsDebugBundle.DEFAULT
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(debugFilter=debugFilter))
        CLK = 5
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

    def test_WhileTrueWriteCntr1(self):
        self.test_WhileTrueWriteCntr0(cls=WhileTrueWriteCntr1, ref=[1, 2, 3, 4])

    def _test_WhileSendSequence(self, cls: WhileSendSequence0, FREQ:int,
                                randomizeIn: bool, randomizeOut: bool,
                                platform=None,
                                timeMultiplier=1):
        dut = cls()
        dut.CLK_FREQ = int(FREQ)
        if platform is None:
            # platform = VirtualHlsPlatform()
            platform = VirtualHlsPlatform(debugFilter={  # *HlsDebugBundle.ALL_RELIABLE,
                                                        HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                                                        HlsDebugBundle.DBG_4_0_addSignalNamesToData})
        self.compileSimAndStart(dut, target_platform=platform)
        # dut.dataIn._ag.data.extend([1, 1, 1, 1])
        inputData = [5, 0, 0, 3, 2, 0, 1, 3, 1,
                                  1,
                                  0,
                                  1
                                   ]
        # print("input", inputData)
        dut.dataIn._ag.data.extend(inputData)
        dut.dataIn._ag.presetBeforeClk = True
        # dut.dataIn._ag.data.extend([2, 2])
        CLK = 40
        if randomizeIn and randomizeOut:
            CLK *= 4
        elif randomizeIn or randomizeOut:
            CLK *= 3

        self.runSim(int(CLK * freq_to_period(dut.CLK_FREQ) * timeMultiplier))
        self._test_no_comb_loops()
        # explainer = RtlSimExplainer(self.rtl_simulator, dut)
        # print("\n")
        # explainer.selectSignalsByRegex(re.compile("hsScc0_elm144_0_en_ack"))\
        #    .filterByValue(0)\
        #    .dumpAsCode(depth=20)
        # print("\n")
        # explainer.selectChannels()\
        #    .dump()
        # print("\n")
        modelOut = list(int(o) for o in dut.model(iter(inputData)))
        self.assertValSequenceEqual(dut.dataOut._ag.data, modelOut)
        refOut = [5, 4, 3, 2, 1,
                  3, 2, 1,
                  2, 1,
                  1,
                  3, 2, 1,
                  1, 1,
                  1
                  ]
        self.assertSequenceEqual(modelOut, refOut)

    def test_WhileSendSequence0_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, False, False)

    def test_WhileSendSequence0_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, False, False,
                                     timeMultiplier=2)

    def test_WhileSendSequence0_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, False, False, timeMultiplier=2.5)

    # @expectedFailure  # problem with flush
    def test_WhileSendSequence1_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, False, False)

    def test_WhileSendSequence1_40Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 40e6, False, False)

    def test_WhileSendSequence1_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, False, False, timeMultiplier=1.7)

    def test_WhileSendSequence1_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, False, False, timeMultiplier=2.4)

    def test_WhileSendSequence2_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, False, False)

    def test_WhileSendSequence2_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, False, False,
                                     timeMultiplier=2)

    def test_WhileSendSequence2_130Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 130e6, False, False,
                                     timeMultiplier=2.2)

    def test_WhileSendSequence3_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, False, False, timeMultiplier=1.1)

    def test_WhileSendSequence3_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, False, False, timeMultiplier=2.3)

    def test_WhileSendSequence3_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, False, False, timeMultiplier=3.8)

    def test_WhileSendSequence4_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, False, False)

    def test_WhileSendSequence4_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, False, False, timeMultiplier=1.7)

    # last item is stalled inside of the 3 clk loop, the problem is that the decision if loop inputs should be accepted
    # takes too much time and flushing logic begins after it
    def test_WhileSendSequence4_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, False, False, timeMultiplier=2.5)

    def test_WhileSendSequence0_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, True, True)

    def test_WhileSendSequence0_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, True, True)

    def test_WhileSendSequence0_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, True, True)

    def test_WhileSendSequence1_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, True, True)

    def test_WhileSendSequence1_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, True, True)

    def test_WhileSendSequence1_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, True, True)

    def test_WhileSendSequence2_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, True, True)

    def test_WhileSendSequence2_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, True, True)

    def test_WhileSendSequence2_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 150e6, True, True)

    def test_WhileSendSequence3_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, True, True)

    def test_WhileSendSequence3_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, True, True)

    def test_WhileSendSequence3_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, True, True)

    def test_WhileSendSequence4_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, True, True)

    def test_WhileSendSequence4_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, True, True)

    def test_WhileSendSequence4_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, True, True)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    m = WhileSendSequence1()
    m.CLK_FREQ = int(20e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
    #   *HlsDebugBundle.ALL_RELIABLE,
    #   HlsDebugBundle.DBG_20_addSignalNamesToSync,
    #   HlsDebugBundle.DBG_20_addSignalNamesToData,
    # })))
    # Artix7Medium
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={*HlsDebugBundle.ALL_RELIABLE, })))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([
    #    HlsAstWhileTrue_TC('test_WhileSendSequence1_20Mhz'),
    #  #  HlsAstWhileTrue_TC('test_WhileSendSequence2_py_100Mhz_rand'),
    # ])
    suite = testLoader.loadTestsFromTestCase(HlsAstWhileTrue_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
