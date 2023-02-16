#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List

from hwt.code import Concat
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.std import VectSignal, Handshaked
from hwt.interfaces.structIntf import StructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.common_nonstd_interfaces.addr_data_hs import AddrDataVldHs


class Rom(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(2, signed=False)
        self.o = VectSignal(32, signed=False)._m()

    def mainThread(self, hls: HlsScope):
        t = self.o._dtype
        # must be hw type otherwise we won't be able to resolve type of "o" later
        mem = [t.from_py(1 << i) for i in range(4)]
        while BIT.from_py(1):
            i = hls.read(self.i).data
            o = mem[i]
            hls.write(o, self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = HlsThreadFromPy(hls, self.mainThread, hls)
        #t.bytecodeToSsa.debug = True
        hls.addThread(t)
        hls.compile()


class CntrArray(Unit):

    def _config(self) -> None:
        self.ITEMS = Param(4)

    def _declr(self):
        addClkRstn(self)
        ADDR_WIDTH = log2ceil(self.ITEMS - 1)
        self.i = VectSignal(ADDR_WIDTH, signed=False)

        self.o_addr = VectSignal(ADDR_WIDTH, signed=False)
        self.o = VectSignal(16, signed=False)._m()

    def mainThread(self, hls: HlsScope):
        mem = [hls.var(f"v{i:d}", self.o._dtype) for i in range(self.ITEMS)]
        for v in mem:
            v(0)  # we are using () instead of = because v is preproc variable

        while BIT.from_py(1):
            o = mem[hls.read(self.o_addr).data]
            i = hls.read(self.i).data
            hls.write(o, self.o)
            mem[i] += 1

    def _impl(self):
        Rom._impl(self)


class Cam(Unit):

    def _config(self) -> None:
        self.KEY_WIDTH = Param(16)
        self.ITEMS = Param(4)

    def _declr(self):
        addClkRstn(self)

        w = AddrDataVldHs()
        w.DATA_WIDTH = self.KEY_WIDTH
        w.ADDR_WIDTH = log2ceil(self.ITEMS - 1)
        self.write = w
    
        self.match = m = Handshaked()
        m.DATA_WIDTH = self.KEY_WIDTH

        # one hot encoded
        self.out = o = Handshaked()._m()
        o.DATA_WIDTH = self.ITEMS

    def matchThread(self, hls: HlsScope, keys: List[StructIntf]):
        while BIT.from_py(1):
            m = hls.read(self.match).data
            match_bits = []
            for k in keys:
                _k = hls.read(k).data
                match_bits.append(_k.vld & _k.key._eq(m))

            hls.write(Concat(*reversed(match_bits)), self.out)

    def updateThread(self, hls: HlsScope, keys: List[StructIntf]):
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

    def _impl(self) -> None:
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
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.platform import HlsDebugBundle
    #from hwtHls.platform.virtual import VirtualHlsPlatform
    u = CntrArray()
    print(to_rtl_str(u, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
