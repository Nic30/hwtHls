#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.io.amba.axi4Lite.axi4LiteCopy_test import Axi4LiteCopy_TC
from tests.io.amba.axi4Lite.axi4LiteRead_test import Axi4LiteRead_TC
from tests.io.amba.axi4Lite.axi4LiteWrite_test import Axi4LiteWrite_TC
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import Axi4SPacketCopyByteByByteTC
from tests.io.amba.axi4Stream.axi4sPacketByteCntr_test import Axi4SPacketByteCntrTC
from tests.io.amba.axi4Stream.axi4sPacketCntr_test import Axi4SPacketCntrTC
from tests.io.amba.axi4Stream.axi4sPacketLenTrim_test import Axi4sPacketLenTrimTC
from tests.io.amba.axi4Stream.axi4sParseEth_test import Axi4SParseEthTC
from tests.io.amba.axi4Stream.axi4sParseIf_test import Axi4SParseIfTC
from tests.io.amba.axi4Stream.axi4sParseLinear_test import Axi4SParseLinearTC
from tests.io.amba.axi4Stream.axi4sPingResponder import Axi4SPingResponder_256_TC, Axi4SPingResponder_512_TC
from tests.io.amba.axi4Stream.axi4sWriteByte_test import Axi4SWriteByteTC
from tests.io.amba.axi4StreamSegmented.axi4ssPacketByteCntr_test import Axi4SSPacketCntrTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseIf_test import Axi4SSParseIf_1Seg_TC, \
    Axi4SSParseIf_2Seg_TC, Axi4SSParseIf_3Seg_TC, Axi4SSParseIf_4Seg_TC
from tests.io.amba.axi4StreamSegmented.axi4ssParseLinear_test import Axi4SSParseLinearTC
from tests.io.bram.bramRead_test import BramRead_TC
from tests.io.bram.bramWrite_test import BramWrite_TC
from tests.io.bram.counterArray_test import BramCounterArray_TC
from tests.io.bram.readSizeFromRamAndSendSequence_test import ReadSizeFromRamAndSendSequence_TC
from tests.io.flushing_test import Flushing_TC
from tests.io.ioFsm2_test import IoFsm2_TC
from tests.io.ioFsm_test import IoFsm_TC
from tests.io.readAtleastOne_test import ReadAtleastOne_TC
from tests.testCaseUtils import testSuiteFromTCs


io_TCs = [
    Flushing_TC,
    IoFsm_TC,
    IoFsm2_TC,
    Axi4SPacketCntrTC,
    Axi4SPacketByteCntrTC,
    Axi4sPacketLenTrimTC,
    Axi4SParseEthTC,
    Axi4SParseLinearTC,
    Axi4SParseIfTC,
    Axi4SWriteByteTC,
    Axi4SPacketCopyByteByByteTC,
    Axi4SSPacketCntrTC,
    Axi4SSParseLinearTC,
    Axi4SSParseIf_1Seg_TC,
    Axi4SSParseIf_2Seg_TC,
    Axi4SSParseIf_3Seg_TC,
    Axi4SSParseIf_4Seg_TC,
    BramRead_TC,
    BramWrite_TC,
    Axi4SPingResponder_256_TC,
    Axi4SPingResponder_512_TC,
    Axi4LiteRead_TC,
    Axi4LiteWrite_TC,
    Axi4LiteCopy_TC,
    BramCounterArray_TC,
    ReadSizeFromRamAndSendSequence_TC,
    ReadAtleastOne_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*io_TCs))

