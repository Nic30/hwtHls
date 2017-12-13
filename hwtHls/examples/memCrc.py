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
        self.mem.a(self.data)

        with Hls(self, freq=self.CLK_FREQ) as hls:
            # collect all interfaces
            # hls see bram interface as array
            mem = hls(self.mem.b)
            run = hls(self.run)
            hasherOut = hls(crc.dataOut)
            hasherIn = hls(crc.dataIn)
            crcOut = hls(self.crcOut)
            # tell hls that default state of this interface should be 0
            clean = hls(crc.clean, pull=0)

            If = hls.If

            If(run,
                hls.seq(
                    # reset crc hasher
                    clean(1),
                    # walk memory and accumulate hash,
                    hls.For(lambda i: hasherIn(mem[i]),
                            items=mem),
                    # send data to utside word
                    crcOut(hasherOut)
                )
            )


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = MemCrc()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
