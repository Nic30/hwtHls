#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.interfaces.std import HandshakeSync, Handshaked, BramPort_withoutClk
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hls import Hls
from hwtLib.logic.crc import Crc
from hwtLib.mem.ram import RamSingleClock


class MemCrc(Crc):
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))
        Crc._config(self)
        self.ADDR_WIDTH = Param(4)

    def _declr(self):
        addClkRstn(self)
        self.run = HandshakeSync()
        self.crcOut = Handshaked()

        with self._paramsShared():
            # port for data acess from external word
            self.data = BramPort_withoutClk()
            # crc hasher
            self.crc = Crc()
            # memory
            self.mem = RamSingleClock()
            self.mem.PORT_CNT.set(2)

    def _impl(self):
        crc = self.crc
        mem = self.mem
        mem.a(self.data)

        with Hls(self, freq=self.CLK_FREQ) as hls:
            r, w, If = hls.read, hls.write, hls.If
            run = r(self.run)
            # tell hls that default state of this interface should be 0
            hls.pull(crc.clean, 0)

            If(run,
                hls.seq(
                    # reset crc hasher
                    w(1, crc.clean),
                    # walk memory and accumulate hash
                    hls.For(main_for_body, items=mem.b),
                    # send data to utside word
                    w(crc.dataOut, self.crcOut)
                )
            )

            def main_for_body(index):
                data = r(mem.b, index)

                # return operations in iteration
                return [
                    data,
                    w(data, crc.dataIn),
                ]


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = MemCrc()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
