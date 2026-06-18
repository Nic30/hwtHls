#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.io.amba.axi4Lite.axi4LiteCopy_test import Axi4LiteCopy_TC
from tests.io.amba.axi4Lite.axi4LiteRead_test import Axi4LiteRead_TC
from tests.io.amba.axi4Lite.axi4LiteWrite_test import Axi4LiteWrite_TC
from tests.io.amba.axi4Stream._axi4StreamAllTests import axi4Stream_TCs
from tests.io.amba.axi4StreamSegmented._axi4StreamSegmentedAllTests import axi4StreamSegmented_TCs
from tests.io.avalon.avalonStParseLinear_test import AvalonStParseLinearTC
from tests.io.bram.bramRead_test import BramRead_TC
from tests.io.bram.bramWriteAligner_test import HwIOAddrDataUnalignedToBram_TCs
from tests.io.bram.bramWrite_test import BramWrite_TC
from tests.io.bram.counterArray_test import BramCounterArray_TC
from tests.io.bram.readSizeFromRamAndSendSequence_test import ReadSizeFromRamAndSendSequence_TC
from tests.io.flushing_test import Flushing_TC
from tests.io.ioFsm2_test import IoFsm2_TC
from tests.io.ioFsm_test import IoFsm_TC
from tests.io.ioVectorizeStore_test import IoVectorizationStore_TC
from tests.io.pcie.pcieDmaTlpHandlerHost2dev_test import PcieDmaTlpHandlerHost2dev_TCs
from tests.io.pcie.pcieUtils_test import PcieUtils_TC
from tests.io.pcie.storeAligner_test import PcieTlpStoreAligner_TCs
from tests.io.readAtleastOne_test import ReadAtleastOne_TC
from tests.testCaseUtils import testSuiteFromTCs


io_TCs = [
    Flushing_TC,
    IoFsm_TC,
    IoFsm2_TC,
    *axi4Stream_TCs,
    AvalonStParseLinearTC,
    *axi4StreamSegmented_TCs,
    BramRead_TC,
    BramWrite_TC,
    Axi4LiteRead_TC,
    Axi4LiteWrite_TC,
    Axi4LiteCopy_TC,
    BramCounterArray_TC,
    *HwIOAddrDataUnalignedToBram_TCs,
    ReadSizeFromRamAndSendSequence_TC,
    ReadAtleastOne_TC,
    IoVectorizationStore_TC,
    PcieUtils_TC,
    *PcieDmaTlpHandlerHost2dev_TCs,
    *PcieTlpStoreAligner_TCs,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*io_TCs), printTopLongest=3)

