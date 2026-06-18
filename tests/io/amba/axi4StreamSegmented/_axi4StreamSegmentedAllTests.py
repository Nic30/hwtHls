#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.io.amba.axi4StreamSegmented.axi4ssPacketByteCntr_test import Axi4SSPacketByteCntrTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseLinear_test import Axi4SSParseLinearTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseIf_test import Axi4SSParseIf_TCs

axi4StreamSegmented_TCs = [
   Axi4SSPacketByteCntrTC,
   Axi4SSParseLinearTC,
   *Axi4SSParseIf_TCs,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*axi4StreamSegmented_TCs), printTopLongest=3)
