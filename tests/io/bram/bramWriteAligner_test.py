#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from random import Random
from typing import Sequence, Optional
import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.agents.bramPort import storeToRamMaskedByAddress, \
    storeToRamMaskedByIndex
from hwt.math import log2ceil
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import HlsDebugBundle
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtSimApi.agents.base import NOP
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask, byte_mask_to_bit_mask_int
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.bram.bramSimRam import BramSimRam
from tests.io.bram.bramWriteAligner import HwIOAddrDataUnalignedToBram
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform
from tests.utils.testQueue import TestQueueIn, TestQueueOutIndexed


class HwIOAddrDataUnalignedToBram_TC(unittest.TestCase):

    @staticmethod
    def _generateInputTransaction(inputTy: HStruct, addr: int, data:int, addrStep:int, wordByteMask:int, wordBitMask:int, rand: Random, thisWordMask:Optional[int]):
        if thisWordMask is None:
            dataSize = rand.randint(1, addrStep)
            m = mask(dataSize)
            bitMask = mask(dataSize * 8)
        else:
            m = thisWordMask
            bitMask = byte_mask_to_bit_mask_int(thisWordMask, addrStep, 8)
        data &= bitMask

        d = inputTy.from_py({  # data aligned to 4B, addr[2:] specifies which bytes from first 4B word are used
            "addr": addr,
            "data": data,
            "mask": m
        })
        return d, data, m

    @classmethod
    def _getRequestT(cls, unalignedAddrWidth: int, dataWidth: int):
        return HStruct(
            (HBits(unalignedAddrWidth), "addr"),
            (HBits(dataWidth), "data"),
            (HBits(dataWidth // 8), "mask"),
        )

    @classmethod
    def _generateInputTransactions(cls, addresses: Sequence[int],
                                        rand: Optional[Random],
                                        unalignedAdderessWidth: int,
                                        dataWidth: int,
                                        hasDataAtBegin: bool,
                                        requestChannelRandomize: bool):
        inWordAddrWidth = log2ceil(dataWidth // 8)
        inputTy = cls._getRequestT(unalignedAdderessWidth, dataWidth)
        dataIn = TestQueueIn(inputTy, maxNbReadsWithoutData=5)
        if rand is None:
            rand: Random = Random(0)

        addrStep = dataWidth // 8  # number of bytes in the word
        # mask used to clear bits in the datamask for addresses not aligned to 4B
        wordByteMask = mask(addrStep)
        wordBitMask = mask(addrStep * 8)
        refRam: dict[int, tuple[int, int]] = {}

        for i, addr in enumerate(addresses):
            if i == 0:
                # add optional nop at the beginning to test also this case
                if not hasDataAtBegin:
                    dataIn.append(NOP)
            else:
                # add NOPs randomly in requrests
                if requestChannelRandomize and rand.getrandbits(1):
                    dataIn.append(NOP)

            if addr is NOP:
                dataIn.append(NOP)
                continue

            data = rand.getrandbits(addrStep * 8)  # (i + 1) * 0x01010101  #
            # data = 0x9999  # i
            if isinstance(addr, tuple):
                addr, thisWordMask = addr
            else:
                thisWordMask = None

            d, data, m = cls._generateInputTransaction(inputTy, addr, data,
                                                       addrStep, wordByteMask, wordBitMask,
                                                       rand, thisWordMask=thisWordMask)
            # print(f"d: {int(d.addr):x}, {int(d.data):x}, {int(d.mask):x}")

            bitmask = byte_mask_to_bit_mask_int(m, addrStep)
            storeToRamMaskedByAddress(refRam, addr, inWordAddrWidth, data, bitmask)
            dataIn.append(d)

        dataIn.append(NOP)
        dataIn.append(NOP)

        return dataIn, refRam

    def _test(self, addresses: Sequence[int],
              rand: Random=None,
              dataWidth=32, unalignedAdderessWidth=64,
              hasDataAtBegin=True,
              WORD_INDEX_STEP=1,
              requestChannelRandomize=True,
              debugLogTestRequests=False):
        if rand is None:
            rand: Random = Random(0)

        dataIn, refRam = self._generateInputTransactions(addresses, rand, unalignedAdderessWidth, dataWidth,
                                                         hasDataAtBegin, requestChannelRandomize)
        if debugLogTestRequests:
            for din in dataIn:
                if din is NOP:
                    print("dataIn NOP")
                else:
                    print(f"dataIn {int(din.addr):02x}: {int(din.data):08x} {int(din.mask):x}")
        dataRamOut = TestQueueOutIndexed()
        ALIGN_BIT_CNT = log2ceil(dataWidth // 8)
        wordT = HBits(dataWidth)
        wordMaskT = HBits(dataWidth // 8)
        wordIndexTy = HBits(unalignedAdderessWidth - ALIGN_BIT_CNT)
        try:
            HwIOAddrDataUnalignedToBram().forwardRequestThread(
                wordIndexTy, wordT, wordMaskT,
                ALIGN_BIT_CNT, WORD_INDEX_STEP,
                dataIn, dataRamOut, isSim=True)

        except SimIoUnderflowErr:
            pass  # finish of the simulation

        self.assertFalse(bool(dataIn))
        ram: dict[int, tuple[int, int]] = {}
        for _i, _d, _m in dataRamOut:
            i = int(_i)
            m = int(_m)
            mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
            d = _d.val & _d.vld_mask & mExpanded
            if debugLogTestRequests:
                print(f"_test {i:02x}: {d:08x} {m:x}")
            assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
            storeToRamMaskedByIndex(ram, i, d, mExpanded)

        if debugLogTestRequests:
            print("ramRef:")
            for a, d in sorted(refRam.items(), key=lambda x: x[0]):
                print(f"  {a:02x}: {d[0]:08x} {d[1]:01x}")
            print("ram:")
            for a, d in sorted(ram.items(), key=lambda x: x[0]):
                print(f"  {a:02x}: {d[0]:08x} {d[1]:01x}")

        self.assertDictEqual(ram, refRam)
        return dataRamOut

    def test_aligned_sequential_firstAvail(self):
        #
        N = 2
        dataWidth = 32
        addrStep = dataWidth // 8
        addresses = [i * addrStep for i in range(N)]
        unalignedAdderessWidth = 4 + log2ceil(dataWidth // 8)
        dataRamOut = self._test(addresses=addresses, unalignedAdderessWidth=unalignedAdderessWidth, dataWidth=dataWidth)
        self.assertEqual(len(dataRamOut), N)

    def test_unaligned_0_1(self, addresses=[0x0, 0x1], addrWidth=10, dataWidth=32, requestChannelRandomize=True, expectedTransactionCount=3):
        dataRamOut = self._test(addresses=addresses,
                                unalignedAdderessWidth=addrWidth,
                                dataWidth=dataWidth,
                                requestChannelRandomize=requestChannelRandomize)
        self.assertLessEqual(len(dataRamOut), expectedTransactionCount)

    def test_unaligned_0_4(self, addresses=[0x0, 0x4], expectedTransactionCount=2):
        self.test_unaligned_0_1(addresses=addresses, expectedTransactionCount=expectedTransactionCount)

    def test_unaligned_0x10_0x11(self):
        self.test_unaligned_0_1(addresses=[0x10, 0x11])

    def test_unaligned_0x10_0x10(self):
        self.test_unaligned_0_1(addresses=[0x10, 0x10])

    def test_unaligned_0x3aa_0x201(self):
        self.test_unaligned_0_1(addresses=[0x3aa, 0x201], expectedTransactionCount=4)

    def test_unaligned_0x3e1_0x3aa_0x201(self):
        self.test_unaligned_0_1(addresses=[(0x3e1, 0b0011), NOP, (0x3aa, 0b0111), (0x201, 0b0111)],
                                requestChannelRandomize=False, expectedTransactionCount=6)

    def test_unaligned_0x192_0x2b(self):
        self.test_unaligned_0_1(addresses=[(0x192, 0b1111), NOP, (0x2b, 0b0001)],
                                requestChannelRandomize=False, expectedTransactionCount=6)

    def test_unaligned_0x18f_0x192(self):
        self.test_unaligned_0_1(addresses=[(0x18f, 0b1111),
                                           (0x192, 0b1111),
                                           # (0x2b, 0b0001)
                                           ],
                                requestChannelRandomize=False, expectedTransactionCount=6)

    def test_unaligned(self, rand: Optional[Random]=None, N=64, addrWidth=10, dataWidth=32):
        if rand is None:
            rand = Random(SimTestCase._defaultSeed)

        size = int(2 ** addrWidth)
        addresses = [rand.randint(0, size - 1)  for _ in range(N)]
        dataRamOut = self._test(addresses=addresses,
                                rand=rand,
                                unalignedAdderessWidth=addrWidth,
                                dataWidth=dataWidth)
        self.assertLessEqual(len(dataRamOut), 2 * N)


class HwIOAddrDataUnalignedToBram_rtl_TC(SimTestCase):

    def _testLlvmIrOrMir(self, platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator,
                         isMir: bool, dataIn: list[HStructConstBase], refRam: dict[int, HBitsConst]):
        dut = toLlvm.parentHwModule
        wallTime = len(dataIn) * 1000
        ramOut = BramSimRam(dut.DATA_WIDTH, int(2 ** dut.ADDR_WIDTH), hasWeMask=True)
        dinFlatT = HBits(dataIn[0]._dtype.bit_length())
        # concat with b1 because read is non-blocking
        dataInFlat = deque(
            NOP
            if d is NOP else
            d._reinterpret_cast(dinFlatT)
            for d in dataIn)
        args = (ramOut, iter(dataInFlat))
        BaseIrMirRtl_TC._runLlvmIrOrMir(self, platform, toLlvm, "", wallTime, isMir, args)
        ram: dict[int, tuple[int, int]] = {k: (v.val, v.vld_mask) for k, v in ramOut.data.items()}
        # print("")
        # print(refRam)
        # print(ram)
        self.assertDictEqual(ram, refRam)

    def _test(self, addresses: Sequence[int],
                 unalignedAdderessWidth=10,
                 dataWidth=32,
                 hasDataAtBegin=True, wordIndexStep=1,
                 requestChannelRandomize=True,
                 rand:Optional[Random]=None):
        dut = HwIOAddrDataUnalignedToBram()
        dut.CLK_FREQ = int(1e6)
        dut.ADDR_WIDTH = unalignedAdderessWidth - log2ceil(dataWidth // 8)
        dut.DATA_WIDTH = dataWidth
        if rand is None:
            rand = self._rand
        # prepare transactions and reference ram
        dataIn, refRam = HwIOAddrDataUnalignedToBram_TC._generateInputTransactions(
            addresses, rand=rand,
            unalignedAdderessWidth=unalignedAdderessWidth,
            dataWidth=dataWidth,
            hasDataAtBegin=hasDataAtBegin,
            requestChannelRandomize=requestChannelRandomize)
        tc = self

        def testLlvmOptIr(*args):
            tc._testLlvmIrOrMir(*args, False, dataIn, refRam)

        def testLlvmOptMir(*args):
            tc._testLlvmIrOrMir(*args, True, dataIn, refRam)

        # debugFilter = None
        debugFilter = HlsDebugBundle.ALL_RELIABLE
        platform = TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr,
            optMirTest=testLlvmOptMir,
            debugFilter=debugFilter,
            # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER, ],
            # runTestAfterEachPass=True,
            # runTestAfterEachMirPass=True,
        )

        self.compileSimAndStart(dut, target_platform=platform)
        dut.reqIn._ag.presetBeforeClk = True  # for more easy orientation in sim
        dut.reqIn._ag.data.extend(dataIn)
        # dut.ramOut._ag._debugOutput = sys.stdout
        self.runSim(int(freq_to_period(dut.CLK_FREQ) * len(dataIn) * 2))
        self.assertFalse(bool(dut.reqIn._ag.data))
        ram: dict[int, tuple[int, int]] = {k: (v.val, v.vld_mask) for k, v in dut.ramOut._ag.mem.items()}
        # for _i, _d, _m in dataRamOut:
        #    i = int(_i)
        #    m = int(_m)
        #    mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
        #    d = _d.val & _d.vld_mask & mExpanded
        #    assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
        #    storeToRamMaskedByIndex(ram, i, d, mExpanded)

        # print("")
        # print(refRam)
        # print(ram)
        self.assertDictEqual(ram, refRam)
        return ram

    def test_aligned_sequential_firstAvail(self):
        HwIOAddrDataUnalignedToBram_TC.test_aligned_sequential_firstAvail(self)

    def test_unaligned_0_1(self, addresses=[0x0, 0x1], requestChannelRandomize=True, expectedTransactionCount=3):
        HwIOAddrDataUnalignedToBram_TC.test_unaligned_0_1(self, addresses=addresses,
                                                          requestChannelRandomize=requestChannelRandomize,
                                                          expectedTransactionCount=expectedTransactionCount)

    def test_unaligned_0_4(self):
        HwIOAddrDataUnalignedToBram_TC.test_unaligned_0_4(self)

    def test_unaligned_0x10_0x11(self):
        HwIOAddrDataUnalignedToBram_TC.test_unaligned_0x10_0x11(self)

    def test_unaligned_0x10_0x10(self):
        HwIOAddrDataUnalignedToBram_TC.test_unaligned_0x10_0x10(self)

    def test_unaligned(self):
        HwIOAddrDataUnalignedToBram_TC.test_unaligned(self, rand=self._rand)


HwIOAddrDataUnalignedToBram_TCs = [
    HwIOAddrDataUnalignedToBram_TC,
    HwIOAddrDataUnalignedToBram_rtl_TC,
]

if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(tc)
                               for tc in HwIOAddrDataUnalignedToBram_TCs)
    # suite = testLoader.loadTestsFromTestCase(HwIOAddrDataUnalignedToBram_TC)
    # suite = unittest.TestSuite([HwIOAddrDataUnalignedToBram_rtl_TC("test_aligned_sequential_firstAvail")])
    # suite = testLoader.loadTestsFromTestCase(HwIOAddrDataUnalignedToBram_rtl_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

