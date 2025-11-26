#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.hlsNetlist.bitwiseOpsAggregation_test import HlsNetlistBitwiseOpsTC
from tests.hlsNetlist.breakHandshakeCycles_channelCond_test import BreakHandshakeCycles_channelCond_TC
from tests.hlsNetlist.breakHandshakeCycles_test import BreakHandshakeCycles_TC
from tests.hlsNetlist.netlistReduceBitwise_test import HlsNetlistReduceBitwiseTC
from tests.hlsNetlist.netlistReduceMul_test import HlsNetlistReduceMulTC
from tests.hlsNetlist.netlistReduceMux_test import HlsNetlistReduceMuxTC
from tests.hlsNetlist.readNonBlocking_test import ReadNonBockingTC
from tests.hlsNetlist.readSync_test import HlsNetlistReadSyncTC
from tests.hlsNetlist.simplifyBackedgeWritePropagation_test import HlsCycleDelayHwModule
from tests.hlsNetlist.syncLowering_exprExtraction_negations_test import RtlArchPassSyncLowering_exprExtraction_negations_TC
from tests.hlsNetlist.syncLowering_exprExtraction_test import RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC
from tests.hlsNetlist.wire_test import HlsNetlistWireTC
from tests.testCaseUtils import testSuiteFromTCs


hlsNetlistAllTests_TCs = [
    HlsNetlistWireTC,
    HlsNetlistBitwiseOpsTC,
    HlsNetlistReduceBitwiseTC,
    HlsNetlistReduceMuxTC,
    HlsNetlistReduceMulTC,
    # HlsNetlistPassInjectVldMaskToSkipWhenConditionsTC,
    HlsNetlistReadSyncTC,
    BreakHandshakeCycles_channelCond_TC,
    RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC,
    RtlArchPassSyncLowering_exprExtraction_negations_TC,
    BreakHandshakeCycles_TC,
    ReadNonBockingTC,
    HlsCycleDelayHwModule,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*hlsNetlistAllTests_TCs), printTopLongest=3)

