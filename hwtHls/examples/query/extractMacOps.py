from hwt.synthesizer.unit import Unit
from hwt.synthesizer.param import Param
from hwt.interfaces.utils import addClkRstn
from hwt.interfaces.std import VectSignal
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class MacExtractingHls(Hls):
    def _discoverAllNodes(self):
        
        return Hls._discoverAllNodes(self)
 


class GroupOfMacOps(Unit):
    def _config(self):
        self.CLK_FREQ = Param(int(25e6))
        self.INPUT_CNT = Param(4)

    def _declr(self):
        addClkRstn(self)
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn0 = [VectSignal(32, signed=False)
                        for _ in range(int(self.INPUT_CNT))]
        self._registerArray("dataIn0", self.dataIn0)

        self.dataIn1 = [VectSignal(32, signed=False)
                        for _ in range(int(self.INPUT_CNT))]
        self._registerArray("dataIn1", self.dataIn1)

        self.dataOut0 = VectSignal(64, signed=False)
        self.dataOut1 = VectSignal(64, signed=False)

    def _impl(self):
        with MacExtractingHls(self, freq=self.CLK_FREQ) as hls:
            a, b, c, d = [hls.read(intf)
                          for intf in self.dataIn0]
            e = a * b + c * d
            hls.write(e, self.dataOut0)

            a, b, c, d = [hls.read(intf)
                          for intf in self.dataIn1]
            e = a * b + c * d
            hls.write(e, self.dataOut1)


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    import unittest
    u = GroupOfMacOps()
    
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
