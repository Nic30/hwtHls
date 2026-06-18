#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from tests.math.fixp._fixpAlu1_TC import FixpAlu1_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpCastOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.math.fixp.passTestIoFixp import PassTestIoInHFixedPoint, \
    PassTestIoOutHFixedPoint


class FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC(SimTestCase):
    FP_TY = HFixedPointQ(3, 2)
    FP_TY_OUT = HFixedPointQ(3, 1)
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    INPUT_DATA = [
        0.0,
        0.25,
        0.5, 0.75, 1.25, 1.5, 1.75,
        -0.25, -0.5, -0.75, -1.25, -1.5,
    ]

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = _FixpCastOpTestModule()
        dut.T = self.FP_TY
        dut.T_OUT = self.FP_TY_OUT
        dut.CLK_FREQ = freq
        passTests = PassTestInjectorForDInDOutHwModule(
            dut, self)
        passTests.setRunTestsAfter(
            runTestAfterEachPass=runTestAfterEachPass,
            # runTestAfterEachMirPass=True,
        )
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=self.RTL_SIM_TIME_MULTIPLIER,
                                wallTimeRtlDefaultAddAfter=20)
        platform = VirtualHlsPlatform()
        FixpAlu1_TC.initPlatform(self, platform)
        passTests.test_allInOne_withModel(IN_DATA=(PassTestIoInHFixedPoint(dut.T, self.INPUT_DATA),),
                                          OUT_DATA_REF=(PassTestIoOutHFixedPoint(dut.T_OUT, self.INPUT_DATA, []),),
                                          platform=platform)
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = testLoader.loadTestsFromTestCase(FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC)
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

