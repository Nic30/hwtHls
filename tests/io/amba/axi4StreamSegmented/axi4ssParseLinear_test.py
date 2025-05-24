#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParseStructManyInts0, \
    Axi4SParseStructManyInts1, Axi4SParse2fields
from tests.io.amba.axi4Stream.axi4sParseLinear_test import Axi4SParseLinearTC
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmentedFrameUtils
from tests.io.amba.axi4StreamSegmented.axi4ssParseLinear import Axi4SSParseStructManyInts0, \
    Axi4SSParseStructManyInts1, Axi4SSParse2fields


class Axi4SSParseLinearTC(Axi4SParseLinearTC):
    dutClsPatch = {
        Axi4SParseStructManyInts0: Axi4SSParseStructManyInts0,
        Axi4SParseStructManyInts1: Axi4SSParseStructManyInts1,
        Axi4SParse2fields: Axi4SSParse2fields,
    }

    def _test_parse(self, DATA_WIDTH:int, SEGMENT_CNT:int=1, cls=Axi4SSParseStructManyInts0, N=3, T=structManyInts):
        cls = self.dutClsPatch.get(cls, cls)
        dut = cls()
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.SEGMENT_CNT = SEGMENT_CNT
        self._run_test_parse(dut, Axi4StreamSegmentedFrameUtils, N, T)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SSParseLinearTC("test_Axi4SParseStructManyInts1_512b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SSParseLinearTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
