from typing import Optional, Literal

from hwtHls.frontend.pragmaLoop import PyBytecodeStreamLoopUnroll
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from tests.io.amba.axi4Stream.axi4sPacketLenTrim import Axi4SPacketTrimByteByByte1b
from hwt.simulator.simTestCase import SimTestCase
from tests.passTestInjectorForStreamHwModule import PassTestInjectorForStreamHwModule
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils


class Axi4sPacketLenTrimTC(SimTestCase):
    StreamFrameUtils = Axi4StreamSimFrameUtils

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH:int, FRAME_LENGTHS:list[int], OUT_MAX_LEN: int,
        UNROLL:Optional[Literal[PyBytecodeStreamLoopUnroll]]=None, freq=int(1e6),
        cls=Axi4SPacketTrimByteByByte1b):

        dut = cls()
        dut.UNROLL = UNROLL
        dut.DATA_WIDTH = DATA_WIDTH
        dut.OUT_DATA_WIDTH = OUT_DATA_WIDTH
        dut.OUT_MAX_LEN = OUT_MAX_LEN
        dut.CLK_FREQ = freq

        refFramesIn = []
        refFramesOut = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFramesIn.append(data)

            # apply functionality o f Axi4SPacketTrim
            if len(data) <= OUT_MAX_LEN:
                out = data
            else:
                out = data[:OUT_MAX_LEN]

            refFramesOut.append(out)

        passTests = PassTestInjectorForStreamHwModule(dut, self, self.StreamFrameUtils)
        passTests.bindDataByInOut((refFramesIn,), (refFramesOut,),)
        passTests.setRunTestsAfter(
            # runTestAfterEachIrPass=True,
            # runTestAfterIrInstrCombineChange=True,
            # runTestAfterIrCfgSimplify=True,
            # runTestAfterEachMirPass=True,
            # runTestAfterMirVRegIfConverterChange=True,
            # runTestAfterMirGISelCombinerChange=True,
            )
        passTests.test_allInOne(
            platformKwArgs=dict(
                    # debugFilter={
                    #     *HlsDebugBundle.ALL_RELIABLE,
                    #     HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                    #     HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                    #  },
                    llvmCliArgs=[
                      # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                      # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                      # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                      # ("hwthls-simplifycfg-SwitchReduceRange", 0, "", "false"),
                      # ("hwthls-simplifycfg-HoistHoistableAssumes", 0, "", "false"),
                      # ("hwthls-simplifycfg-NormalizeLookupTableIndex", 0, "", "false"),
                      # ("hwthls-simplifycfg-RewriteMaskPatternsFromCFGToData", 0, "", "false"),
                      # ("hwthls-simplifycfg-StoreHoist", 0, "", "false"),
                      # ("hwthls-simplifycfg-AggresiveStoreSink", 0, "", "false"),
                      # ("hwthls-simplifycfg-MergePredecessorsStore", 0, "", "false"),
                      # ("hwthls-simplifycfg-PhiToLogicalExpr", 0, "", "false"),
                      # ("hwthls-simplifycfg-UnswitchCheapManyPredManySuccBB", 0, "", "false"),
                      # ("hwthls-simplifycfg-UnswitchComplementarySequentialBlocks", 0, "", "false"),
                      # ("hwthls-simplifycfg-SpeculatePredecessor", 0, "", "false"),
                      # ("hwthls-simplifycfg-StreamWriteMerge", 0, "", "false"),
                      # ("hwthls-simplifycfg-StreamReadMerge", 0, "", "false"),
                      # ("hwthls-simplifycfg-SwitchToSelectOrRomLoad", 0, "", "false"),
                      # ("hwthls-simplifycfg-NormalizeBrCond", 0, "", "false"),
                      # ("hwthls-simplifycfg-ConstantFoldTerminator", 0, "", "false"),
                      # ("hwthls-simplifycfg-EliminateDuplicatePHINodes", 0, "", "false"),
                      # ("hwthls-simplifycfg-EemoveUndefIntroducingPredecessor", 0, "", "false"),
                      # ("hwthls-simplifycfg-MergeBlockIntoPredecessor", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunEarlyCSEPass", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunRomExtractPass", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunHwtHlsInstCombinePass", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunTrivialSimplifyCFGPass", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunSimplifyCFGPass", 0, "", "false"),
                      # ("hwthls-simplifycfg-RunBitcountMergePass", 0, "", "false"),
                    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                    LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                    #LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                  ],
                  # runTestAfterEachPass=True,
                  # runTestAfterEachIrPass=True,
                  # runTestAfterEachMirPass=True,
                )
            )

    def _test_anyB(self, BYTE_CNT:int, OUT_MAX_LEN:int, PKT_CNT=6):
        frameLens = [self._rand.randint(1, BYTE_CNT * 3) for _ in range(PKT_CNT)]
        # print(frameLens)
        # frameLens = [7, ]
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

    # def test_64B_max128(self):
    #     self._test_anyB(64, 128)
    
    # def test_64B_max96(self):
    #    self._test_anyB(64, 96)
    #
    # def test_64B_max129(self):
    #    self._test_anyB(64, 129)


if __name__ == '__main__':
    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4sPacketLenTrimTC)
    # suite = unittest.TestSuite([Axi4sPacketLenTrimTC("test_4B_max128")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
