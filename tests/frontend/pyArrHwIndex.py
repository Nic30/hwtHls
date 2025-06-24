#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List

from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStruct, HdlType_to_HwIO
from hwt.hwIOs.std import HwIOVectSignal, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_without_registration
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.commonHwIO.addr_data import HwIOAddrDataVldRdVld


class ExampleRomPyList(HwModule):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.i = HwIOVectSignal(2, signed=False)
        self.o = HwIOVectSignal(32, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.o._dtype
        # must be hw type otherwise we won't be able to resolve type of "o" later
        mem = [t.from_py(1 << i) for i in range(4)]
        while b1:
            i = hls.read(self.i).data
            o = mem[i]
            hls.write(o, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(t)
        hls.compile()


class ExampleRomHwArray(ExampleRomPyList):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        mem = self.o._dtype[4].from_py([1 << i for i in range(4)])
        while b1:
            i = hls.read(self.i).data
            o = mem[i]
            hls.write(o, self.o)


class ExampleCntrArray(HwModule):

    @override
    def hwConfig(self) -> None:
        self.ITEMS = HwParam(4)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        ADDR_WIDTH = log2ceil(self.ITEMS - 1)
        self.i = HwIOVectSignal(ADDR_WIDTH, signed=False)

        self.o_addr = HwIOVectSignal(ADDR_WIDTH, signed=False)
        self.o = HwIOVectSignal(16, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        mem = [hls.var(f"v{i:d}", self.o._dtype) for i in range(self.ITEMS)]
        for v in mem:
            v(0)  # we are using () instead of = because v is preproc variable

        while b1:
            o = mem[hls.read(self.o_addr).data]
            i = hls.read(self.i).data
            hls.write(o, self.o)
            mem[i] += 1

    @override
    def hwImpl(self):
        ExampleRomPyList.hwImpl(self)


class ExampleCntrArrayHwArray(ExampleCntrArray):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        mem = self.o._dtype[self.ITEMS].from_py([0 for _ in range(self.ITEMS)])

        while b1:
            o = mem[hls.read(self.o_addr).data]
            i = hls.read(self.i).data
            hls.write(o, self.o)
            mem[i] += 1


class ExampleCam(HwModule):

    @override
    def hwConfig(self) -> None:
        self.KEY_WIDTH = HwParam(16)
        self.ITEMS = HwParam(4)

    @override
    def hwDeclr(self):
        addClkRstn(self)

        w = HwIOAddrDataVldRdVld()
        w.DATA_WIDTH = self.KEY_WIDTH
        w.ADDR_WIDTH = log2ceil(self.ITEMS - 1)
        self.write = w

        self.match = m = HwIODataRdVld()
        m.DATA_WIDTH = self.KEY_WIDTH

        # one hot encoded
        self.out = o = HwIODataRdVld()._m()
        o.DATA_WIDTH = self.ITEMS

    def matchThread(self, hls: HlsScope, keys: List[HwIOStruct]):
        while b1:
            m = hls.read(self.match).data
            match_bits = []
            for k in keys:
                _k = hls.read(k).data
                match_bits.append(_k.vld & _k.key._eq(m))
                del _k # :note: if _k is not deleted the same read object will be used for all iterations

            hls.write(Concat(*reversed(match_bits)), self.out)

    def updateThread(self, hls: HlsScope, record_t: HStruct, keysOut: List[HwIOStruct]):
        keys = [hls.var(f"k{i:d}", record_t) for i in range(self.ITEMS)]
        # initial reset
        for k in keys:
            PyBytecodeBlockLabel("ExampleCam.updateThread.rstLoop")
            k.vld(0)

        while b1:
            for keyIndex, key in enumerate(keys):
                PyBytecodeBlockLabel("ExampleCam.updateThread.keyExportLoop")
                hls.write(key, keysOut[keyIndex])

            PyBytecodeBlockLabel("ExampleCam.updateThread.keyUpdate")
            w = hls.read(self.write).data
            newKey = record_t.from_py(None)
            newKey.vld = w.vld_flag
            newKey.key = w.data
            # the result of HW index on python object is only reference
            # and the item select is constructed when item is used first time
            # or write switch-case  is constructed if the item is written
            keys[w.addr] = newKey

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, freq=int(100e6))
        record_t = HStruct(
            (self.match.data._dtype, "key"),
            (BIT, "vld")
        )

        keysFromUpdateToMatchThread = []
        for i in range(self.ITEMS):
            p = HdlType_to_HwIO().apply(record_t)
            HwIO_without_registration(self, p, f"keyForMatchThread_{i:d}")
            keysFromUpdateToMatchThread.append(p)

        hls.addThread(HlsThreadFromPy(hls, self.updateThread, hls, record_t, keysFromUpdateToMatchThread))
        hls.addThread(HlsThreadFromPy(hls, self.matchThread, hls, keysFromUpdateToMatchThread))

        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    
    m = ExampleCntrArray()
    m.ITEMS = 4
    print(to_rtl_str(m, target_platform=Artix7Medium(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
         llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ],
        )))
