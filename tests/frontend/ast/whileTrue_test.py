#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest.case import expectedFailure

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.ast.whileTrue import WhileTrueWriteCntr0, WhileTrueWriteCntr1, \
    WhileSendSequence0, WhileSendSequence1, WhileSendSequence2, WhileSendSequence3, \
    WhileSendSequence4


#    def test_(\S+)_ast_(\S+)\(self, USE_PY_FRONTEND=False\):
#    def test_$1_py_$2(self):\n        self.test_$1_ast_$2(USE_PY_FRONTEND=True)\n    def test_$1_ast_$2(self, USE_PY_FRONTEND=False):
class HlsAstWhileTrue_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def test_WhileTrueWriteCntr0_ast(self, cls=WhileTrueWriteCntr0, ref=[0, 1, 2, 3],
                                     USE_PY_FRONTEND:bool=False):
        dut = cls()
        dut.USE_PY_FRONTEND = USE_PY_FRONTEND
        # debugFilter={*HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSignalNamesToSync}
        debugFilter = HlsDebugBundle.DEFAULT
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(debugFilter=debugFilter))
        CLK = 5
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

    def test_WhileTrueWriteCntr0_py(self):
        self.test_WhileTrueWriteCntr0_ast(USE_PY_FRONTEND=True)

    def test_WhileTrueWriteCntr1_ast(self, USE_PY_FRONTEND=False):
        self.test_WhileTrueWriteCntr0_ast(cls=WhileTrueWriteCntr1, ref=[1, 2, 3, 4],
                                         USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileTrueWriteCntr1_py(self):
        self.test_WhileTrueWriteCntr1_ast(USE_PY_FRONTEND=True)

    def _test_WhileSendSequence(self, cls: WhileSendSequence0, FREQ:int,
                                randomizeIn: bool, randomizeOut: bool,
                                platform=None,
                                timeMultiplier=1,
                                USE_PY_FRONTEND=False):
        dut = cls()
        dut.FREQ = int(FREQ)
        dut.USE_PY_FRONTEND = USE_PY_FRONTEND
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

        self.runSim(int(CLK * freq_to_period(dut.FREQ) * timeMultiplier))
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

    def test_WhileSendSequence0_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_20Mhz(self):
        self.test_WhileSendSequence0_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, False, False,
                                     timeMultiplier=2, USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_100Mhz(self):
        self.test_WhileSendSequence0_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, False, False, timeMultiplier=2.5,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_150Mhz(self):
        self.test_WhileSendSequence0_ast_150Mhz(USE_PY_FRONTEND=True)

    # @expectedFailure  # problem with flush
    def test_WhileSendSequence1_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_20Mhz(self):
        self.test_WhileSendSequence1_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_40Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 40e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_40Mhz(self):
        self.test_WhileSendSequence1_ast_40Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, False, False, timeMultiplier=1.7,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_100Mhz(self):
        self.test_WhileSendSequence1_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, False, False, timeMultiplier=2.4,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_150Mhz(self):
        self.test_WhileSendSequence1_ast_150Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_20Mhz(self):
        self.test_WhileSendSequence2_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, False, False,
                                     timeMultiplier=2,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_100Mhz(self):
        self.test_WhileSendSequence2_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_130Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 130e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND,
                                     timeMultiplier=2.2)

    def test_WhileSendSequence2_py_130Mhz(self):
        self.test_WhileSendSequence2_ast_130Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, False, False, timeMultiplier=1.1,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_20Mhz(self):
        self.test_WhileSendSequence3_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, False, False, timeMultiplier=2.3,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_100Mhz(self):
        self.test_WhileSendSequence3_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_py_150Mhz(self):
        self.test_WhileSendSequence3_ast_150Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, False, False, timeMultiplier=3.8,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_20Mhz(self):
        self.test_WhileSendSequence4_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_100Mhz(self):
        self.test_WhileSendSequence4_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, False, False, timeMultiplier=1.7,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_150Mhz(self):
        self.test_WhileSendSequence4_ast_150Mhz(USE_PY_FRONTEND=True)

    # last item is stalled inside of the 3 clk loop, the problem is that the decision if loop inputs should be accepted
    # takes too much time and flushing logic begins after it
    @expectedFailure
    def test_WhileSendSequence4_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, False, False, timeMultiplier=2.5,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_20Mhz_rand(self):
        self.test_WhileSendSequence0_ast_20Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_20Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_100Mhz_rand(self):
        self.test_WhileSendSequence0_ast_100Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_100Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_150Mhz_rand(self):
        self.test_WhileSendSequence0_ast_150Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_150Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    # @expectedFailure  # problem with flush
    def test_WhileSendSequence1_py_20Mhz_rand(self):
        self.test_WhileSendSequence1_ast_20Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_20Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_100Mhz_rand(self):
        self.test_WhileSendSequence1_ast_100Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_100Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence1_py_150Mhz_rand(self):
        self.test_WhileSendSequence1_ast_150Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence1_ast_150Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_20Mhz_rand(self):
        self.test_WhileSendSequence2_ast_20Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_20Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_100Mhz_rand(self):
        self.test_WhileSendSequence2_ast_100Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_100Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_150Mhz_rand(self):
        self.test_WhileSendSequence2_ast_150Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_150Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 150e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_20Mhz_rand(self):
        self.test_WhileSendSequence3_ast_20Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_20Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_100Mhz_rand(self):
        self.test_WhileSendSequence3_ast_100Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_100Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_150Mhz_rand(self):
        self.test_WhileSendSequence3_ast_150Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_150Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_20Mhz_rand(self):
        self.test_WhileSendSequence4_ast_20Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_20Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_100Mhz_rand(self):
        self.test_WhileSendSequence4_ast_100Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_100Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_150Mhz_rand(self):
        self.test_WhileSendSequence4_ast_150Mhz_rand(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_150Mhz_rand(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, True, True,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)


if __name__ == "__main__":
    #from hwt.synth import to_rtl_str
    #m = WhileSendSequence4()
    #m.USE_PY_FRONTEND = True
    #m.FREQ = int(150e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
    #    *HlsDebugBundle.ALL_RELIABLE,
    #    HlsDebugBundle.DBG_20_addSignalNamesToSync,
    #    HlsDebugBundle.DBG_20_addSignalNamesToData,
    # })))
    # Artix7Medium
    #print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={*HlsDebugBundle.ALL_RELIABLE, })))

    import unittest
    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([
    #    HlsAstWhileTrue_TC('test_WhileSendSequence3_ast_150Mhz'),
    #  #  HlsAstWhileTrue_TC('test_WhileSendSequence2_py_100Mhz_rand'),
    #])
    suite = testLoader.loadTestsFromTestCase(HlsAstWhileTrue_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
