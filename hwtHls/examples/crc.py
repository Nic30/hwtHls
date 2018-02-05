from hwt.synthesizer.vectorUtils import iterBits
from hwtHls.hls import Hls
from hwtLib.logic.crcPoly import CRC_32
from hwtLib.logic.crcUtils import buildCrcMatrix_dataMatrix
from hwtLib.logic.crcComb import CrcComb


class CrcCombHls(CrcComb):
    def _config(self):
        CrcComb._config(self)
        self.CLK_FREQ = 100e6
        self.POLY_WIDTH.set(32)
        self.DATA_WIDTH.set(8)
        self.POLY.set(CRC_32)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            DW = int(self.DATA_WIDTH)
            # assert PW == DW
            polyCoefs, PW = self.parsePoly()
            xorMatrix = buildCrcMatrix_dataMatrix(polyCoefs, PW, DW)

            for outBit, inMask in zip(iterBits(self.dataOut),
                                      xorMatrix):
                bit = None
                for m, b in zip(reversed(inMask),
                                iterBits(self.dataIn)):
                    if m:
                        b = hls.io(b)
                        if bit is None:
                            bit = b
                        else:
                            bit = bit ^ b
                assert bit is not None

                hls.io(outBit)(bit)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import toRtl
    from hwtHls.platform.virtual import VirtualHlsPlatform

    u = CrcCombHls()

    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    # suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
