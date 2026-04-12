from hwt.hdl.types.struct import HStruct
from hwtHls.scope import HlsScope
from hwt.hdl.types.bits import HBits
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.frontend.trivial import WriteOnce
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period


class Builtin_setattr_setHConst(WriteOnce):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t0 = HBits(self.DATA_WIDTH, signed=False)
        t = HStruct(
            (t0, "vAttr")
        )
        v = t.from_py(None)
        setattr(v, "vAttr", t0.from_py(1))
        hls.write(v, self.dataOut)


class Builtin_setattr_setHConstVar(WriteOnce):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t0 = HBits(self.DATA_WIDTH, signed=False)
        t = HStruct(
            (t0, "vAttr")
        )
        v = t.from_py(None)
        v1 = t0.from_py(1)
        setattr(v, "vAttr", v1)
        hls.write(v, self.dataOut)


class _TestObj():
    pass


class Builtin_setattr_setOnPyObj(WriteOnce):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        a = _TestObj()
        setattr(a, "vAttr", 1)
        assert a.vAttr == 1, a.vAttr
        hls.write(1, self.dataOut)


class Builtin_setattr_TC(SimTestCase):

    def test_setHConst(self, dutCls=Builtin_setattr_setHConst):
        dut = dutCls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        CLK_PERIOD = freq_to_period(dut.CLK_FREQ)
        self.runSim(int(CLK * CLK_PERIOD))
        self.assertValSequenceEqual(dut.dataOut._ag.data, [1, ])

    def test_setHConstVar(self):
        self.test_setHConst(dutCls=Builtin_setattr_setHConstVar)

    def test_setOnPyObj(self):
        self.test_setHConst(dutCls=Builtin_setattr_setOnPyObj)


if __name__ == '__main__':
    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Builtin_setattr_TC)
    # suite = unittest.TestSuite([Builtin_setattr_TC("test_setHConst")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
