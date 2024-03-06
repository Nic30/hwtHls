from hwt.hdl.types.defs import BIT
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.frontend.pyBytecode.pragmaInline import PragmaInline_writeCntr1


class CntrHolder():

    def __init__(self, hls: HlsScope):
        self.val = hls.var("cntr", uint8_t)


class VarReference_writeCntr0(PragmaInline_writeCntr1):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = CntrHolder(hls)
        cntr.val = 0
        limit = 4

        while BIT.from_py(1):
            hls.write(cntr.val, self.o)
            if limit > 0:
                cntr.val += 1

class VarReference_writeCntr1(PragmaInline_writeCntr1):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = CntrHolder(hls)
        cntr.val = 0xff
        limit = 4

        while BIT.from_py(1):
            if limit > 0:
                cntr.val += 1
            hls.write(cntr.val, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = VarReference_writeCntr1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
