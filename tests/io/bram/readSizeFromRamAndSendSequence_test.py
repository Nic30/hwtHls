#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.io.bram.readSizeFromRamAndSendSequence import ReadSizeFromRamAndSendSequence
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class ReadSizeFromRamAndSendSequence_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def test_ReadSizeFromRamAndSendSequence(self, FREQ=50e6):
        dut = ReadSizeFromRamAndSendSequence()
        dut.CLK_FREQ = int(FREQ)
        CLK = 12
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
        #    debugFilter={
        #    HlsDebugBundle.DBG_20_addSignalNamesToSync,
        #    HlsDebugBundle.DBG_20_addSignalNamesToData
        #}
        ))
        indexLenTuples = [
            (3, 4),
            (2, 1),
            (0, 2),
        ]
        dut.index._ag.presetBeforeClk = True
        dut.index._ag.data.extend(i for i, _ in indexLenTuples)
        dut.index._ag.presetBeforeClk = True
        dut.ram._ag.mem.update({i: v for i, v in indexLenTuples})

        self.runSim(CLK * int(freq_to_period(FREQ)))
        self._test_no_comb_loops()
        ref = []
        for _, size in indexLenTuples:
            ref.extend(range(size, -1, -1))
        self.assertValSequenceEqual(dut.out._ag.data, ref)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = ReadSizeFromRamAndSendSequence()
    m.CLK_FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
        *HlsDebugBundle.ALL_RELIABLE,
        # HlsDebugBundle.DBG_20_addSignalNamesToSync,
        # HlsDebugBundle.DBG_20_addSignalNamesToData
    })))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ReadSizeFromRamAndSendSequence_TC("test_ReadSizeFromRamAndSendSequence")])
    suite = testLoader.loadTestsFromTestCase(ReadSizeFromRamAndSendSequence_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)