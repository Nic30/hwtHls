#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List

from hwt.code import Concat
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.std import HwIOVectSignal, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.commonHwIO.addr_data import HwIOAddrDataVldRdVld


class Rom(HwModule):

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
        while BIT.from_py(1):
            i = hls.read(self.i).data
            o = mem[i]
            hls.write(o, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(t)
        hls.compile()


class CntrArray(HwModule):

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

        while BIT.from_py(1):
            o = mem[hls.read(self.o_addr).data]
            i = hls.read(self.i).data
            hls.write(o, self.o)
            mem[i] += 1

    @override
    def hwImpl(self):
        Rom.hwImpl(self)


class Cam(HwModule):

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
        while BIT.from_py(1):
            m = hls.read(self.match).data
            match_bits = []
            for k in keys:
                _k = hls.read(k).data
                match_bits.append(_k.vld & _k.key._eq(m))

            hls.write(Concat(*reversed(match_bits)), self.out)

    def updateThread(self, hls: HlsScope, keys: List[HwIOStruct]):
        # initial reset
        for k in keys:
            k.vld(0)

        while BIT.from_py(1):
            w = hls.read(self.write).data
            newKey = keys[0]._dtype.from_py(None)
            newKey.vld = w.vld_flag
            newKey.key = w.data
            # the result of HW index on python object is only reference
            # and the item select is constructed when item is used first time
            # or write switch-case  is constructed if the item is written
            hls.write(newKey, keys[w.addr])

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, freq=int(100e6))
        record_t = HStruct(
            (self.match.data._dtype, "key"),
            (BIT, "vld")
        )
        keys = [hls.varShared(f"k{i:d}", record_t) for i in range(self.ITEMS)]
        hls.addThread(HlsThreadFromPy(hls, self.updateThread, hls, [k.getWritePort() for k in keys]))
        hls.addThread(HlsThreadFromPy(hls, self.matchThread, hls, [k.getReadPort() for k in keys]))

        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.platform import HlsDebugBundle
    # from hwtHls.platform.virtual import VirtualHlsPlatform

    m = CntrArray()
    print(to_rtl_str(m, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
