#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from random import Random
from typing import Sequence, Optional
import unittest

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.agents.bramPort import storeToRamMaskedByAddress, \
    storeToRamMaskedByIndex
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.debugBundle import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtSimApi.agents.base import NOP
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask, byte_mask_to_bit_mask_int, align
from tests.frontend.trivial import WriteOnce
from tests.io.pcie.storeAligner import PcieTlpStoreAligner
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform
from tests.utils.testQueue import TestQueueIn, TestQueueOutIndexed


# from hwtHls.llvm.llvmIr import LlvmCompilationBundle
# from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
class PcieTlpStoreAligner_TC(unittest.TestCase):

    @staticmethod
    def _generateInputTransaction(inputTy: HStruct, addr: int, data:int, addrStep:int,
                                  wordByteMask:int, wordBitMask:int, rand: Random):
        # the data of pcie transaction is aligned to 4B boundary, the lower bits of address may be used to disable
        # bytes at the beginning of the first word
        firstWordOffset = addr & 0b11
        while True:
            empty = rand.randint(0, addrStep - 1)
            dataSize = addrStep - empty
            if firstWordOffset < dataSize:
                break

        m = mask(dataSize)
        data &= wordBitMask >> (empty * 8)

        if firstWordOffset:
            # align data to 4B, mark first bytes and invalid, crop if overflow
            m <<= firstWordOffset
            data << 8 * firstWordOffset
            m &= wordByteMask
            data &= wordBitMask

        d = inputTy.from_py({  # data aligned to 4B, addr[2:] specifies which bytes from first 4B word are used
            "addr": addr,
            "data": data,
            "empty": empty
        })
        return d, data, m

    @classmethod
    def _generateInputTransactions(cls, addresses: Sequence[int],
                                        rand: Optional[Random],
                                        dataWidth: int,
                                        ramWords: int,
                                        hasDataAtBegin: bool):
        inWordAddrWidth = log2ceil(dataWidth // 8)
        inputTy = PcieTlpStoreAligner.getWordToStore_t(64, dataWidth)
        addressWidth = log2ceil(ramWords * (dataWidth // 8))
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
                if not hasDataAtBegin:
                    dataIn.append(NOP)
            else:
                if rand.getrandbits(1):
                    dataIn.append(NOP)

            data = rand.getrandbits(addrStep * 8)
            # data = 0x9999  # i

            d, data, m = cls._generateInputTransaction(inputTy, addr, data, addrStep, wordByteMask, wordBitMask, rand)
            # print(f"d: {int(d.addr):x}, {int(d.data):x}, {int(d.empty)}")

            bitmask = byte_mask_to_bit_mask_int(m, addrStep)
            # :note: lower bits of address already used to update bitmask
            storeToRamMaskedByAddress(refRam, align(addr, 2), inWordAddrWidth, data, bitmask)
            dataIn.append(d)

        return dataIn, addressWidth, refRam

    def _test(self, addresses: Sequence[int], rand: Random=None,
                 dataWidth=256, ramWords=64,
                 hasDataAtBegin=True, wordIndexStep=1):
        if rand is None:
            rand: Random = Random(0)

        dataIn, addressWidth, refRam = self._generateInputTransactions(addresses, rand, dataWidth, ramWords, hasDataAtBegin)
        dataRamOut = TestQueueOutIndexed()

        try:
            # print("PcieTlpStoreAligner.mainThread")
            PcieTlpStoreAligner().mainThread(
                dataIn, dataRamOut, addressWidth, dataWidth, wordIndexStep, isSim=True)
        except SimIoUnderflowErr:
            pass  # finish of the simulation

        self.assertFalse(bool(dataIn))
        ram: dict[int, tuple[int, int]] = {}
        for _i, _d, _m in dataRamOut:
            i = int(_i)
            m = int(_m)
            mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
            d = _d.val & _d.vld_mask & mExpanded
            assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
            storeToRamMaskedByIndex(ram, i, d, mExpanded)

        # print("")
        # print(refRam)
        # print(ram)
        self.assertDictEqual(ram, refRam)
        return dataRamOut

    def test_aligned_sequential_firstAvail(self):
        N = 32
        dataWidth = 256
        addrStep = dataWidth // 8
        addresses = [i * addrStep for i in range(N) ]
        dataRamOut = self._test(addresses=addresses, dataWidth=dataWidth)
        self.assertEqual(len(dataRamOut), N)

    def test_unaligned(self, N=2, dataWidth=256, ramWords=64, rand:Optional[Random]=None):
        if rand is None:
            rand = Random(SimTestCase._defaultSeed)

        size = ramWords * (dataWidth // 8)
        addresses = [rand.randint(0, size // 4) << 2  for _ in range(N)]
        dataRamOut = self._test(addresses=addresses, rand=rand, dataWidth=dataWidth, ramWords=ramWords)
        self.assertLessEqual(len(dataRamOut), 2 * N)

    def test_splitToAlignedWords(self, rand=None, ramWords=64, dataWidth=256):
        addressWidth = log2ceil(ramWords * (dataWidth // 8))
        inWordAddrWidth = log2ceil(dataWidth // 8)
        inputTy = PcieTlpStoreAligner.getWordToStore_t(addressWidth, dataWidth)
        addrToWordIndexAlignBits = log2ceil(dataWidth // 8)
        if rand is None:
            rand: Random = Random(0)
        addrStep = dataWidth // 8  # number of bytes in the word
        # mask used to clear bits in the datamask for addresses not aligned to 4B
        wordByteMask = mask(addrStep)
        wordBitMask = mask(addrStep * 8)
        size = ramWords * (dataWidth // 8)
        N = 64
        addresses = [rand.randint(0, size // 4) << 2  for _ in range(N)]
        # print("test:::::")
        for addr in addresses:
            data = rand.getrandbits(addrStep * 8)
            # data = 0x9999  # i

            d, data, m = self._generateInputTransaction(inputTy, addr, data, addrStep, wordByteMask, wordBitMask, rand)
            newWIndex, newWord0, newWord0Mask, newWord1, newWord1Mask = PcieTlpStoreAligner.splitToAlignedWords(
                d, addrToWordIndexAlignBits, dataWidth)

            # print("refRam:")
            refRam: dict[int, tuple[int, int]] = {}
            bitmask = byte_mask_to_bit_mask_int(m, addrStep)
            # :note: lower bits of address already used to update bitmask
            storeToRamMaskedByAddress(refRam, align(addr, 2), inWordAddrWidth, data, bitmask)

            # print("ram:")
            ram: dict[int, tuple[int, int]] = {}
            storeToRamMaskedByIndex(ram, int(newWIndex), int(newWord0),
                                    byte_mask_to_bit_mask_int(int(newWord0Mask), dataWidth))
            if newWord1Mask:
                storeToRamMaskedByIndex(ram, int(newWIndex) + 1, int(newWord1),
                                        byte_mask_to_bit_mask_int(int(newWord1Mask),
                                                                  dataWidth))

            # check that storing original data and storing 2 split words resulted in the same memory state
            self.assertDictEqual(ram, refRam)


class TestHwModulePcieTlpStoreAligner_splitToAlignedWords(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(64)
        self.DATA_WIDTH = HwParam(256)
        self.INDEX_STEP = HwParam(1)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        i = self.dataIn = HwIOStructRdVld()
        i.T = PcieTlpStoreAligner.getWordToStore_t(self.ADDR_WIDTH, self.DATA_WIDTH)

        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = self.getOutTy()

    def getOutTy(self):
        self.ADDR_TO_WORD_INDEX_ALIGN_BITS = log2ceil(self.DATA_WIDTH // 8)
        index_t = HBits(self.ADDR_WIDTH - self.ADDR_TO_WORD_INDEX_ALIGN_BITS)
        data_t = HBits(self.DATA_WIDTH)
        mask_t = HBits(self.DATA_WIDTH // 8)
        return HStruct(
            (index_t, "newWIndex"),
            (data_t, "newWord0"),
            (mask_t, "newWord0Mask"),
            (data_t, "newWord1"),
            (mask_t, "newWord1Mask"),
        )

    @hwt_expr_producer
    @staticmethod
    def byteEnabledByEmpty(byteI: int, bytesTotal: int, empty: AnyHBitsValue):
        return PcieTlpStoreAligner.byteEnabledByEmpty(byteI, bytesTotal, empty)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            newD: HStructConstBase = hls.read(self.dataIn).data
            (newWIndex, newWord0, newWord0Mask, newWord1, newWord1Mask) = \
                PyBytecodeInline(PcieTlpStoreAligner.splitToAlignedWords)(newD, self.ADDR_TO_WORD_INDEX_ALIGN_BITS, self.DATA_WIDTH)

            outTmp = self.dataOut.T.from_py(None)
            outTmp.newWIndex = newWIndex
            outTmp.newWord0 = newWord0
            outTmp.newWord0Mask = newWord0Mask
            outTmp.newWord1 = newWord1
            outTmp.newWord1Mask = newWord1Mask
            hls.write(outTmp, self.dataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class PcieTlpStoreAligner_splitToAlignedWords_rtl_TC(SimTestCase):

    def test0(self):

        dataIn = [
            (0x00000000, 0x100f0e0d0c0b0a090804060504030201, 30),
            (0x00000004, 0x100f0e0d0c0b0a090804060504030201, 30),
            (0x00000008, 0x100f0e0d0c0b0a090804060504030201, 30),
            # (0x00000764, 0x0000000000000000000000000000edf0, 30),
            # (0x00000050, 0x000000000000775c4907b2dea46afa6c, 22),
        ]
        refDataOut = []

        dut = TestHwModulePcieTlpStoreAligner_splitToAlignedWords()
        dut.CLK_FREQ = int(1e6)
        outTy = dut.getOutTy()
        dinT = PcieTlpStoreAligner.getWordToStore_t(dut.ADDR_WIDTH, dut.DATA_WIDTH)

        for newDPy in dataIn:
            newD = dinT.from_py({
                "addr": newDPy[0],
                "data": newDPy[1],
                "empty": newDPy[2],
            })
            ref = PcieTlpStoreAligner.splitToAlignedWords(newD, dut.ADDR_TO_WORD_INDEX_ALIGN_BITS, dut.DATA_WIDTH)
            refDataOut.append(ref)

        tc = self

        debugFilter = None
        inFlatTy = HBits(dinT.bit_length())
        dataInFlat = [dinT.from_py({
             "addr": newDPy[0],
                "data": newDPy[1],
                "empty": newDPy[2],
            })._reinterpret_cast(inFlatTy) for newDPy in dataIn]

        def prepareDataInFn():
            return dataInFlat

        def checkDataOutFn(dataOut: Sequence[HBitsConst]):
            tc.assertEqual(len(dataOut), len(refDataOut))
            for out, outRef in zip(dataOut, refDataOut):
                out = out._reinterpret_cast(outTy)
                index, w0d, w0m, w1d, w1m = out.newWIndex, out.newWord0, out.newWord0Mask, out.newWord1, out.newWord1Mask
                ref_index, ref_w0d, ref_w0m, ref_w1d, ref_w1m = outRef
                # print(f"dataOut 0x{int(index):08x}: 0x{int(w0d):064x} {int(w0m):08x}")
                # print(f"                    0x{int(w1d):064x} {int(w1m):08x}")
                # print(f"ref out 0x{int(ref_index):08x}: 0x{int(ref_w0d):064x} {int(ref_w0m):08x}")
                # print(f"                    0x{int(ref_w1d):064x} {int(ref_w1m):08x}\n")
                tc.assertEqual(int(index), int(ref_index))
                tc.assertEqual(int(w0d), int(ref_w0d))
                tc.assertEqual(int(w0m), int(ref_w0m))
                tc.assertEqual(int(w1d), int(ref_w1d))
                tc.assertEqual(int(w1m), int(ref_w1m))

        platform = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            prepareDataInFn, checkDataOutFn,
            Path(self.DEFAULT_LOG_DIR, self.getTestName()),
            debugFilter=debugFilter,
            # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER, ],
            # runTestAfterEachPass=True,
            # runTestAfterEachMirPass=True,
        )

        self.compileSimAndStart(dut, target_platform=platform)
        dut.dataIn._ag.data.extend(dataIn)
        self.runSim(int(freq_to_period(dut.CLK_FREQ) * (len(dataIn) + 2) * 2))
        self.assertFalse(bool(dut.dataIn._ag.data))

        doutRefIt = iter(refDataOut)
        # print("PcieTlpStoreAligner_splitToAlignedWords_rtl_TC\n")
        self.assertEqual(len(dut.dataOut._ag.data), len(refDataOut))
        for (index, w0d, w0m, w1d, w1m), ref in zip(dut.dataOut._ag.data, refDataOut):
            # print(f"dataOut 0x{int(index):08x}: 0x{int(w0d):064x} {int(w0m):08x}")
            # print(f"                    0x{int(w1d):064x} {int(w1m):08x}")

            ref_index, ref_w0d, ref_w0m, ref_w1d, ref_w1m = next(doutRefIt)
            # print(f"ref out 0x{int(ref_index):08x}: 0x{int(ref_w0d):064x} {int(ref_w0m):08x}")
            # print(f"                    0x{int(ref_w1d):064x} {int(ref_w1m):08x}\n")
            self.assertEqual(int(index), int(ref_index))
            self.assertEqual(int(w0d), int(ref_w0d))
            self.assertEqual(int(w0m), int(ref_w0m))
            self.assertEqual(int(w1d), int(ref_w1d))
            self.assertEqual(int(w1m), int(ref_w1m))


class PcieTlpStoreAligner_rtl_TC(SimTestCase):

    def test_aligned_sequential_firstAvail(self):
        PcieTlpStoreAligner_TC.test_aligned_sequential_firstAvail(self)

    def test_unaligned(self):
        PcieTlpStoreAligner_TC.test_unaligned(self, rand=self._rand)

    def _test(self, addresses: Sequence[int],
                 dataWidth=256, ramWords=64,
                 rand:Optional[Random]=None,
                 hasDataAtBegin=True, wordIndexStep=1):
        dut = PcieTlpStoreAligner()
        dut.CLK_FREQ = int(1e6)
        dut.ADDR_WIDTH = 64
        dut.DATA_WIDTH = dataWidth
        dut.INDEX_STEP = 1
        if rand is None:
            rand = self._rand
        # prepare transactions and reference ram
        dataIn, _, refRam = PcieTlpStoreAligner_TC._generateInputTransactions(
            addresses, rand=rand, dataWidth=dataWidth, ramWords=ramWords, hasDataAtBegin=hasDataAtBegin)
        # for din in dataIn:
        #    if din is NOP:
        #        print("dataIn NOP")
        #    else:
        #        print(f"dataIn 0x{int(din.addr):08x}: 0x{int(din.data):064x} {int(din.empty):d}")
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.dataIn._ag.data.extend(dataIn)
        # dut.ramOut._ag._debugOutput = sys.stdout
        self.runSim(int(freq_to_period(dut.CLK_FREQ) * (len(dataIn) + 2) * 2))
        self.assertFalse(bool(dut.dataIn._ag.data))
        ram: dict[int, tuple[int, int]] = {k: (v.val, v.vld_mask) for k, v in dut.ramOut._ag.mem.items()}
        # for _i, _d, _m in dataRamOut:
        #    i = int(_i)
        #    m = int(_m)
        #    mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
        #    d = _d.val & _d.vld_mask & mExpanded
        #    assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
        #    storeToRamMaskedByIndex(ram, i, d, mExpanded)

        # print("ramRef:")
        # for a, d in sorted(refRam.items(), key=lambda x: x[0]):
        #    print(f"  {a:08x}: {d[0]:064x} {d[1]:08x}")
        # print("ram:")
        # for a, d in sorted(ram.items(), key=lambda x: x[0]):
        #    print(f"  {a:08x}: {d[0]:064x} {d[1]:08x}")
        self.assertDictEqual(ram, refRam)
        return ram


PcieTlpStoreAligner_TCs = [
    PcieTlpStoreAligner_TC,
    PcieTlpStoreAligner_splitToAlignedWords_rtl_TC,
    PcieTlpStoreAligner_rtl_TC,
]

if __name__ == "__main__":
    from hwt.synth import to_rtl_str

    dut = TestHwModulePcieTlpStoreAligner_splitToAlignedWords()
    dut.CLK_FREQ = int(1e6)
    dut.DATA_WIDTH = 64
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED]
    )
    # print(to_rtl_str(dut, target_platform=p))

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(tc)
                               for tc in PcieTlpStoreAligner_TCs)
    # suite = unittest.TestSuite([PcieTlpStoreAligner_rtl_TC("test_unaligned")])
    # suite = testLoader.loadTestsFromTestCase(PcieTlpStoreAligner_splitToAlignedWords_rtl_TC)
    # suite = testLoader.loadTestsFromTestCase(PcieTlpStoreAligner_rtl_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

