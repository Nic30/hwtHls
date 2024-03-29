#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.hlsStreamProc.streamProc  import HlsStreamProc
from tests.syntaxElements.trivial import WhileTrueReadWrite


class WhileTrueReadWriteExpr(WhileTrueReadWrite):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(
            hls.While(True,
                hls.write((hls.read(self.dataIn, self.dataIn.T) * 8 + 2) * 3, self.dataOut)
            )
        )
        hls.compile()



class WhileSendSequence(WhileTrueReadWrite):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)

        size = hls.var("size", self.dataIn.T)
        hls.thread(
            hls.While(True,
                size(hls.read(self.dataIn)),
                hls.While(size != 0,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                ),
            )
        )
        hls.compile()



if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileSendSequence()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
