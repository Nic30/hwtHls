#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope  import HlsScope
from tests.frontend.ast.trivial import WhileTrueReadWrite


class WhileTrueReadWriteExpr(WhileTrueReadWrite):

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write((hls.read(self.dataIn, self.dataIn.T) * 8 + 2) * 3, self.dataOut)
            ),
            self._name)
        )
        hls.compile()



class WhileSendSequence(WhileTrueReadWrite):

    def _impl(self) -> None:
        hls = HlsScope(self)

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                size(hls.read(self.dataIn)),
                ast.While(size != 0,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                ),
            ),
            self._name)
        )
        hls.compile()



if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileSendSequence()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
