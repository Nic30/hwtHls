#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.types.ctypes import uint8_t
from tests.io.ioFsm import WriteFsm1


class WriteFsmFor(WriteFsm1):
    """
    IO write FSM inside of pipeline
    """

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        i = hls.var("i", uint8_t)
        hls.thread(
            hls.For(i(0), i < 10, i(i + 1),
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            )
        )
        hls.compile()



class WriteFsmPrequel(WriteFsm1):
    """
    IO write FSM before pipeline
    """

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        i = hls.var("i", uint8_t)
        hls.thread(
            hls.write(99, self.o),
            hls.write(100, self.o),
            hls.For(i(0), i < 10, i(i + 1),
                hls.write(i + 1, self.o),
                hls.write(i + 2, self.o),
                hls.write(i + 3, self.o),
            )
        )
        hls.compile()



class WriteFsmIf(WriteFsm1):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        i = hls.var("i", uint8_t)
        hls.thread(
            i(0),
            hls.While(True,
                hls.If(i._eq(0),
                    hls.write(1, self.o),
                    hls.write(2, self.o),
                    i(1),
                ).Else(
                    hls.write(3, self.o),
                    i(0),
                ),
            ),
        )
        hls.compile()



if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = WriteFsmFor()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
