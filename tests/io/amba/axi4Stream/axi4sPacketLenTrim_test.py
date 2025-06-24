from typing import List, Tuple, Optional, Literal

from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamLoopUnroll
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import BaseAxi4SPktInPktOutTC
from tests.io.amba.axi4Stream.axi4sPacketLenTrim import Axi4SPacketTrimByteByByte4


class Axi4sPacketLenTrimTC(BaseAxi4SPktInPktOutTC):

    # DEFAULT_BUILD_DIR = "tmp"
    @override
    def generateTestData(self, FRAME_LENGTHS: List[int]) -> Tuple[List[List[int]], List[List[int]]]:
        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)
        return refFrames, refFrames

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH:int, FRAME_LENGTHS:List[int], OUT_MAX_LEN: int,
        UNROLL:Optional[Literal[PyBytecodeStreamLoopUnroll]]=None, freq=int(1e6),
        cls=Axi4SPacketTrimByteByByte4):

        dut = cls()
        dut.UNROLL = UNROLL
        dut.DATA_WIDTH = DATA_WIDTH
        dut.OUT_DATA_WIDTH = OUT_DATA_WIDTH
        dut.OUT_MAX_LEN = OUT_MAX_LEN

        refFramesIn = []
        refFramesOut = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFramesIn.append(data)
            if len(data) <= OUT_MAX_LEN:
                out = data
            else:
                out = data[:OUT_MAX_LEN]
            refFramesOut.append(out)

        BaseAxi4SPktInPktOutTC._test(self, dut, refFramesIn, refFramesOut, freq=freq,
                                     platformKwargs=dict(
                  # debugFilter={*HlsDebugBundle.ALL_RELIABLE,
                  # HlsDebugBundle.DBG_20_addSignalNamesToSync,
                  # HlsDebugBundle.DBG_20_addSignalNamesToData,
                  # },
                  llvmCliArgs=[
                    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                    # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                  ],
                  # runTestAfterEachPass=True,
                  # runTestAfterEachIrPass=True,
                  # runTestAfterEachMirPass=True,
              ))

    def _test_anyB(self, BYTE_CNT:int, OUT_MAX_LEN:int, PKT_CNT=6):
        frameLens = [self._rand.randint(1, BYTE_CNT * 3) for _ in range(PKT_CNT)]
        self._test(BYTE_CNT * 8, BYTE_CNT * 8, frameLens, OUT_MAX_LEN, UNROLL=PyBytecodeStreamLoopUnroll)

    def test_1B_max2(self):
        self._test_anyB(1, 2)

    def test_2B_max1(self):
        self._test_anyB(1, 1)

    def test_2B_max2(self):
        self._test_anyB(1, 2)

    def test_2B_max3(self):
        self._test_anyB(1, 3)

    def test_3B_max1(self):
        self._test_anyB(3, 1)

    def test_3B_max2(self):
        self._test_anyB(3, 2)

    def test_3B_max3(self):
        self._test_anyB(3, 3)

    def test_3B_max4(self):
        self._test_anyB(3, 4)

    def test_3B_max7(self):
        self._test_anyB(3, 7)

    def test_64B_max128(self):
        self._test_anyB(64, 128)

    def test_64B_max96(self):
        self._test_anyB(64, 96)

    def test_64B_max129(self):
        self._test_anyB(64, 129)


if __name__ == '__main__':
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4sPacketLenTrimTC("test_64B_max128")])
    suite = testLoader.loadTestsFromTestCase(Axi4sPacketLenTrimTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
