#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.serializer.mode import serializeOnce
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.query.rtlNetlist import QuerySignal, HwSelect
from hwtHls.query.rtlNetlistManipulator import RtlNetlistManipulator


def MAC_qurey() -> QuerySignal:
    a = QuerySignal("a")
    b = QuerySignal("b")
    c = QuerySignal("c")
    d = QuerySignal("d")

    out = (a * b) + (c * d)
    out.setLabel("out")

    return out


@serializeOnce
class MAC(Unit):

    def _config(self):
        self.DATA_WIDTH = Param(32)

    def _declr(self):
        DW = self.DATA_WIDTH
        self.a = VectSignal(DW, signed=False)
        self.b = VectSignal(DW, signed=False)
        self.c = VectSignal(DW, signed=False)
        self.d = VectSignal(DW, signed=False)

        self.out = VectSignal(DW, signed=False)._m()

    def _impl(self):
        out = (self.a * self.b) + (self.c * self.d)
        self.out(out)


class MacExtractingHls(Hls):

    def _build_data_flow_graph(self):
        m = RtlNetlistManipulator(self.ctx, self._io)
        macs = list(HwSelect(self.ctx).select(MAC_qurey))
        for i, mac in enumerate(macs):
            # replace MAC expression with MAC unit
            macU = MAC()
            setattr(self.parentUnit, f"mac{i:d}", macU)

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

        return Hls._build_data_flow_graph(self)


class GroupOfMacOps(Unit):

    def _config(self):
        self.CLK_FREQ = Param(int(25e6))
        self.INPUT_CNT = Param(4)

    def _declr(self):
        addClkRstn(self)
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn0 = HObjList(
            VectSignal(32, signed=False)
            for _ in range(int(self.INPUT_CNT))
        )

        self.dataOut0 = VectSignal(32, signed=False)._m()

        self.dataIn1 = HObjList(
            VectSignal(32, signed=False)
            for _ in range(int(self.INPUT_CNT))
        )

        self.dataOut1 = VectSignal(32, signed=False)._m()

    def _impl(self):

        def mac(hls, inputs, out):
            a, b, c, d = [hls.io(intf) for intf in inputs]
            e = a * b + c * d
            hls.io(out)(e)

        with MacExtractingHls(self, freq=self.CLK_FREQ) as hls:
            mac(hls, self.dataIn0, self.dataOut0)
            mac(hls, self.dataIn1, self.dataOut1)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    u = GroupOfMacOps()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
