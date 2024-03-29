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
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtLib.common_nonstd_interfaces.addr_data_hs import AddrDataVldHs
from hwtLib.types.ctypes import uint32_t
from hwt.hdl.constants import READ
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread


class Rom(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(2, signed=False)
        self.o = VectSignal(32, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        # must be hw type otherwise we won't be able to resolve type of o
        mem = [uint32_t.from_py(1 << i) for i in range(4)]
        while BIT.from_py(1):
            i = hls.read(self.i)
            o = mem[i]
            hls.write(o, self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        hls.compile()


class CntrArray(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(2, signed=False)

        self.o_addr = VectSignal(2, signed=False)
        self.o = VectSignal(32, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        mem = [hls.var(f"v{i:d}", uint32_t) for i in range(4)]
        for v in mem:
            v(0)  # we are using () instead of = because v is preproc variable

        while BIT.from_py(1):
            o = mem[hls.read(self.o_addr)]
            hls.write(o, self.o)
            i = hls.read(self.i)
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

    def matchThread(self, hls: HlsStreamProc, keys: List[StructIntf]):
        while BIT.from_py(1):
            m = hls.read(self.match)
            match_bits = []
            for k in keys:
                match_bits.append(k.vld & k.key._eq(m))

            hls.write(Concat(*reversed(match_bits)), self.out)

    def updateThread(self, hls: HlsStreamProc, keys: List[StructIntf]):
        # initial reset
        for k in keys:
            k.vld(0)

        while BIT.from_py(1):
            w = hls.read(self.write)
            keys[w.addr].vld(w.vld_flag)
            keys[w.addr].key(w.data)

    def _impl(self) -> None:
        hls = HlsStreamProc(self, freq=int(100e6))
        record_t = HStruct(
            (self.match.data._dtype, "key"),
            (BIT, "vld")
        )
        keys = [hls.var(f"k{i:d}", record_t) for i in range(self.ITEMS)]
        
        w = hls.thread(HlsStreamProcPyThread(hls, self.updateThread, hls, keys))
        m = hls.thread(HlsStreamProcPyThread(hls, self.matchThread, hls, keys))
        for k in keys:
            w.addExport(k, READ)
            m.addImport(k, READ)

        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = Cam()
    print(to_rtl_str(u, target_platform=Artix7Medium(**makeDebugPasses("tmp"))))
