#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.io.amba.axi4StreamSegmented.axi4ssPacketByteCntr_test import Axi4SSPacketByteCntrTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseLinear_test import Axi4SSParseLinearTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseIf_test import Axi4SSParseIf_TCs
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_inWordPacking_test import Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_TC
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_outWordPacking_test import Axi4streamSegmentedTxSegnemtBuffer_outWordPacking_TC

axi4StreamSegmented_TCs = [
   Axi4SSPacketByteCntrTC,
   Axi4SSParseLinearTC,
   *Axi4SSParseIf_TCs,
   Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_TC,
   Axi4streamSegmentedTxSegnemtBuffer_outWordPacking_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*axi4StreamSegmented_TCs), printTopLongest=3)
