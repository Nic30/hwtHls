#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.io.amba.axi4Stream.axi4SVlan1qDecapUncond_test import Axi4SVlan1qDecapUncondTC
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import Axi4SPacketCopyByteByByteTC
from tests.io.amba.axi4Stream.axi4sCopyWithLookahead_test import Axi4SCopyWithLookaheadTC
from tests.io.amba.axi4Stream.axi4sCrc_test import Axi4SCrc32_TC
from tests.io.amba.axi4Stream.axi4sPacketByteCntr_test import Axi4SPacketByteCntrTC
from tests.io.amba.axi4Stream.axi4sPacketCntr_test import Axi4SPacketCntrTC
from tests.io.amba.axi4Stream.axi4sPacketLenTrim_test import Axi4sPacketLenTrimTC
from tests.io.amba.axi4Stream.axi4sParse5Tuple_test import Axi4SParse5Tuple_TC
from tests.io.amba.axi4Stream.axi4sParseEth_test import Axi4SParseEthTC
from tests.io.amba.axi4Stream.axi4sParseIf_test import Axi4SParseIfTC
from tests.io.amba.axi4Stream.axi4sParseLinear_test import Axi4SParseLinearTC
from tests.io.amba.axi4Stream.axi4sParseUdpIpv4_test import Axi4SParseUdpIpv4TC
from tests.io.amba.axi4Stream.axi4sPingResponder import Axi4SPingResponder_256_TC, Axi4SPingResponder_512_TC
from tests.io.amba.axi4Stream.axi4sSum_test import Axi4SSum_TC
from tests.io.amba.axi4Stream.axi4sVlan1qEncapUncond_test import Axi4SVlan1qEncapUncondTC
from tests.io.amba.axi4Stream.axi4sWriteByte_test import Axi4SWriteByteTC
from tests.testCaseUtils import testSuiteFromTCs


axi4Stream_TCs = [
    Axi4SPacketCntrTC,
    Axi4SCopyWithLookaheadTC,
    Axi4SPacketByteCntrTC,
    Axi4SSum_TC,
    Axi4SCrc32_TC,
    Axi4sPacketLenTrimTC,
    Axi4SParseEthTC,
    Axi4SParseLinearTC,
    Axi4SParseUdpIpv4TC,
    Axi4SParseIfTC,
    Axi4SParse5Tuple_TC,
    Axi4SWriteByteTC,
    Axi4SPacketCopyByteByByteTC,
    Axi4SPingResponder_256_TC,
    Axi4SPingResponder_512_TC,
    Axi4SVlan1qDecapUncondTC,
    Axi4SVlan1qEncapUncondTC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*axi4Stream_TCs), printTopLongest=3)
