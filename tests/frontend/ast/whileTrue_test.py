#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.platform.xilinx.artix7 import Artix7Medium
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
        u = cls()
        u.USE_PY_FRONTEND = USE_PY_FRONTEND
        self.compileSimAndStart(u,
                                target_platform=VirtualHlsPlatform(debugFilter={
                                    *HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSignalNamesToSync}))
        CLK = 5
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, ref)

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
        u = cls()
        u.FREQ = int(FREQ)
        u.USE_PY_FRONTEND = USE_PY_FRONTEND
        if platform is None:
            platform = VirtualHlsPlatform()
            # platform = VirtualHlsPlatform(debugFilter={HlsDebugBundle.DBG_20_addSignalNamesToSync})
        self.compileSimAndStart(u, target_platform=platform)
        # u.dataIn._ag.data.extend([1, 1, 1, 1])

        u.dataIn._ag.data.extend([5, 0, 0, 3, 2, 0, 1, 3, 1,
                                  1, 0, 1])
        u.dataIn._ag.presetBeforeClk = True
        # u.dataIn._ag.data.extend([2, 2])
        CLK = 40
        if randomizeIn and randomizeOut:
            CLK *= 4
        elif randomizeIn or randomizeOut:
            CLK *= 3

        self.runSim(int(CLK * freq_to_period(u.FREQ) * timeMultiplier))
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, [5, 4, 3, 2, 1,
                                                         3, 2, 1,
                                                         2, 1,
                                                         1,
                                                         3, 2, 1,
                                                         1, 1, 1])

    def test_WhileSendSequence0_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence0_py_20Mhz(self):
        self.test_WhileSendSequence0_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence0_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, False, False,
                                     timeMultiplier=2, USE_PY_FRONTEND=False)

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
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, False, False, platform=Artix7Medium(),
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_100Mhz(self):
        self.test_WhileSendSequence2_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence2_ast_130Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence2, 130e6, False, False, platform=Artix7Medium(),
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence2_py_130Mhz(self):
        self.test_WhileSendSequence2_ast_130Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, False, False, timeMultiplier=1.1,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_20Mhz(self):
        self.test_WhileSendSequence3_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, False, False, timeMultiplier=1.8,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence3_py_100Mhz(self):
        self.test_WhileSendSequence3_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_py_150Mhz(self):
        self.test_WhileSendSequence3_ast_150Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence3_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, False, False, timeMultiplier=2.9,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_20Mhz(self):
        self.test_WhileSendSequence4_ast_20Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_20Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, False, False,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_100Mhz(self):
        self.test_WhileSendSequence4_ast_100Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_100Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, False, False, timeMultiplier=1.4,
                                     USE_PY_FRONTEND=USE_PY_FRONTEND)

    def test_WhileSendSequence4_py_150Mhz(self):
        self.test_WhileSendSequence4_ast_150Mhz(USE_PY_FRONTEND=True)

    def test_WhileSendSequence4_ast_150Mhz(self, USE_PY_FRONTEND=False):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, False, False, timeMultiplier=2.3,
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
    # from hwt.synthesizer.utils import to_rtl_str
    # u = WhileSendSequence1()
    # u.USE_PY_FRONTEND = True
    # u.FREQ = int(150e6)
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter={
    #     *HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSignalNamesToSync
    # })))
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsAstWhileTrue_TC('test_WhileSendSequence1_py_150Mhz_rand')])
    suite = testLoader.loadTestsFromTestCase(HlsAstWhileTrue_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
