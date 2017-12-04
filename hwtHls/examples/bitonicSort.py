#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC


class BitonicSorterHLS(BitonicSorter):
    def _config(self):
        BitonicSorter._config(self)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        BitonicSorter._declr(self)

    def _impl(self):
        with Hls(self, self.CLK_FREQ) as hls:
            _sig = self._sig
            self._sig = hls.var

            outs = self.bitonic_sort(self.cmpFn,
                                     [hls.read(i) for i in self.inputs])
            for o, otmp in zip(self.outputs, outs):
                hls.write(otmp, o)

            self._sig = _sig


class BitonicSorterHLS_TC(BitonicSorterTC):
    def createUnit(self):
        u = BitonicSorterHLS()
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        return u


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    u = BitonicSorterHLS()
    u.ITEMS.set(4)
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
