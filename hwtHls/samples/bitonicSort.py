from hwt.synthesizer.param import Param
from hwt.interfaces.utils import addClkRstn
from hwtHls.hls import Hls
from hwtLib.logic.bitonicSorter import BitonicSorter


class BitonicSorterHLS(BitonicSorter):
    def _config(self):
        BitonicSorter._config(self)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        BitonicSorter._declr(self)

    def _impl(self):
        with Hls(self, self.CLK_FREQ) as hls:
            outs = self.bitonic_sort(self.cmpFn,
                                     [hls.read(i) for i in self.inputs])
            for o, otmp in zip(self.outputs, outs):
                hls.write(otmp, o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = BitonicSorterHLS()
    u.ITEMS.set(4)
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
