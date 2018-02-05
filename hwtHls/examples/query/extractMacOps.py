from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.examples.query.rtlNetlistManipulator import RtlNetlistManipulator,\
    QuerySignal, HwSelect
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


def MAC_qurey():
    a = QuerySignal("a")
    b = QuerySignal("b")
    c = QuerySignal("c")
    d = QuerySignal("d")

    out = (a * b) + (c * d)
    out.setLabel("out")

    return out


class MAC(Unit):
    def _config(self):
        self.DATA_WIDTH = Param(32)

    def _declr(self):
        self.a = VectSignal(self.DATA_WIDTH, signed=False)
        self.b = VectSignal(self.DATA_WIDTH, signed=False)
        self.c = VectSignal(self.DATA_WIDTH, signed=False)
        self.d = VectSignal(self.DATA_WIDTH, signed=False)

        self.out = VectSignal(self.DATA_WIDTH * 2, signed=False)

    def _impl(self):
        out = (self.a * self.b) + (self.c * self.d)
        self.out(out)


class MacExtractingHls(Hls):
    def _discoverAllNodes(self):
        m = RtlNetlistManipulator(self.ctx, self._io)
        macs = list(HwSelect(self.ctx).select(MAC_qurey))
        for i, mac in enumerate(macs):
            name = "mac%d" % i
            macU = MAC()
            setattr(self.parentUnit, name, macU)
            print(mac)

            io = self.io
            new_a = io(macU.a)
            new_b = io(macU.b)
            new_c = io(macU.c)
            new_d = io(macU.d)
            new_out = io(macU.out)

            m.reconnect_subgraph({
                mac["a"]: new_a,
                mac["b"]: new_b,
                mac["c"]: new_c,
                mac["d"]: new_d,
            }, {
                mac["out"]: new_out
            })

            # substitute io signals in _io mapping
            _io = self._io
            for oldIo, newIo in [(mac["a"], new_a),
                                 (mac["b"], new_b),
                                 (mac["c"], new_c),
                                 (mac["d"], new_d),
                                 #(mac["out"], new_out)
                                 ]:
                assert newIo.endpoints, newIo
                _io[newIo] = _io[oldIo]
                del _io[oldIo]

        nodes = Hls._discoverAllNodes(self)
        return nodes


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

        self.dataOut0 = VectSignal(64, signed=False)

        # self.dataIn1 = [VectSignal(32, signed=False)
        #                for _ in range(int(self.INPUT_CNT))]
        #self._registerArray("dataIn1", self.dataIn1)
        #
        #self.dataOut1 = VectSignal(64, signed=False)

    def _impl(self):
        def mac(hls, inputs, out):
            a, b, c, d = [hls.io(intf) for intf in inputs]
            e = a * b + c * d
            hls.io(out)(e)

        with MacExtractingHls(self, freq=self.CLK_FREQ) as hls:
            mac(hls, self.dataIn0, self.dataOut0)
            #mac(hls, self.dataIn1, self.dataOut1)


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    u = GroupOfMacOps()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
