#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Sequence

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructVld
from hwt.hwIOs.std import HwIODataVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.pragmaInstruction import PyBytecodeIsMaskContinuosFromLsb
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.math.addMasked import AddMaskedHardblock
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStruct import PassTestIoInStruct


class ExampleAddMasked(HwModule):

    def hwConfig(self):
        self.DATA_WIDTH = HwParam(16)
        self.ITEMS = 32
        self.CLK_FREQ = HwParam(int(100e6))
        self._IN_TY: Optional[HStruct] = None

    def hwDeclr(self):
        addClkRstn(self)
        assert self.DATA_WIDTH > 0, self.DATA_WIDTH

        self.dataIn = HwIOStructVld()
        self.dataIn.T = HStruct(
            (HBits(self.DATA_WIDTH)[self.ITEMS], "data"),
            (HBits(self.ITEMS), "mask")
        )

        self.dataOut = HwIODataVld()._m()
        self.dataOut.DATA_WIDTH = self.DATA_WIDTH

    def getInTy(self):
        T = self._IN_TY
        if T is None:
            T = HStruct(
                (HBits(self.DATA_WIDTH)[self.ITEMS], "data"),
                (HBits(self.ITEMS), "mask")
            )
            self._IN_TY = T
        return T

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.dataOut.data._dtype
        p = PyBytecodeInPreproc
        addMaskedFn = p(AddMaskedHardblock(t, t))
        while b1:
            chunk = hls.read(self.dataIn).data
            PyBytecodeIsMaskContinuosFromLsb(chunk.mask)
            acc = t.from_py(0)
            for dItem, mBit in zip(chunk.data, chunk.mask):
                if mBit:
                    acc = addMaskedFn(acc, dItem)
                else:
                    break

            hls.write(acc, self.dataOut)

    @staticmethod
    def model(dataIn: Sequence[tuple[tuple[HBitsConst, ...], tuple[HBitsConst, ...]]], dataOut: list[HBitsConst]):
        for dataInItems, maskIn in dataIn:
            res = dataInItems[0]._dtype.from_py(0)
            for d, m in zip(dataInItems, maskIn):
                if not m._is_full_valid():
                    res = res._dtype.from_py(None)
                    break
                elif m:
                    res = res + d
            dataOut.append(res)

    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class AddMasked_TC(BaseIrMirRtl_TC):

    def test_4items(self, OUT_CNT=8, randomData=False):
        dut = ExampleAddMasked()
        ITEMS = dut.ITEMS = 4
        DATA_WIDTH = dut.DATA_WIDTH = 16
        dut.CLK_FREQ = int(200e6)
        dataT = HBits(DATA_WIDTH)
        maskT = HBits(ITEMS)
        inTy = dut.getInTy()
        if randomData:
            dataIn = [
                (tuple(dataT.from_py(self._rand.getrandbits(DATA_WIDTH)) for _ in range(ITEMS)),
                 maskT.from_py(1 << self._rand.randint(0, ITEMS - 1)))
                for _ in range(OUT_CNT)
            ]
        else:
            # use sequential data
            dataIn = []
            for i in range(OUT_CNT):
                d = tuple(dataT.from_py(i * ITEMS + dataI) for dataI in range(ITEMS))
                m = maskT.from_py(mask(i % (ITEMS + 1)))
                # print([int(_d) for _d in d], int(m))
                dataIn.append((d, m))

        dataIn = [inTy.from_py(d) for d in dataIn]

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 200,
                                wallTimeMir=OUT_CNT * 200,
                                wallTimeHlsNetlist=OUT_CNT * 200,
                                wallTimeRtl=(OUT_CNT * 8) + 2)
        passTests.test_allInOne_withModel((PassTestIoInStruct(inTy, dataIn, name="dataIn"),), platform=Artix7Medium())


if __name__ == "__main__":
    import unittest
    import sys
    sys.setrecursionlimit(int(1e6))
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = ExampleAddMasked()
    m.ITEMS = 4
    m.CLK_FREQ = int(200e6)
    m.DATA_WIDTH = 16
    print(to_rtl_str(m, target_platform=Artix7Medium(
      # debugFilter={HlsDebugBundle.DBG_4_4_arch,},
      debugFilter=HlsDebugBundle.ALL_RELIABLE,
      llvmCliArgs=[
          # LLVM_CLI_COMMON_OPTS.debugOnly("legalizer"),
          # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
          # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
          # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
          # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
          # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
          ]
      )))  #

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AddMasked_TC('test_noUnroll')])
    suite = testLoader.loadTestsFromTestCase(AddMasked_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
