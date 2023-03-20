from hwt.hdl.constants import WRITE, READ
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn, propagateClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock


class CounterArray(Unit):

    def _config(self) -> None:
        self.ITEMS = Param(4)
        self.CNTR_WIDTH = Param(16)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.incr = Handshaked()

        t = RamSingleClock()
        t.ADDR_WIDTH = self.incr.DATA_WIDTH = log2ceil(self.ITEMS - 1)
        t.DATA_WIDTH = self.CNTR_WIDTH
        t.PORT_CNT = (READ, WRITE)
        self.ram = t

    @hlsBytecode
    def resetRam(self, hls: HlsScope, ram: BramArrayProxy):
        i = Bits(ram.indexT.bit_length()).from_py(0)
        # [todo] if bit slicing is used on i, the llvm generates uglygep because it is not recognizing
        # the bit slicing and this ugly GEP uses 64b pinter type
        while BIT.from_py(1):
            hls.write(0, ram[i])
            if i._eq(self.ITEMS - 1):
                break
            i += 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        # reset
        # PyBytecodeInline(self.resetRam)(hls, ram)

        lastVld = BIT.from_py(0)
        lastAddr = self.incr.data._dtype.from_py(None)
        lastData = ram.nativeType.element_t.from_py(None)
        while BIT.from_py(1):
            index = hls.read(self.incr).data
            # The ram[index] can not be read until write is finished or there is an LSU to update read data later
            d = hls.read(ram[index]).data
            if lastVld & lastAddr._eq(index):
                d = lastData
            lastData = d + 1
            lastAddr = index
            lastVld = 1
            hls.write(lastData, ram[index])

            # PyBytecodeLLVMLoopUnroll(True, 2)

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, tuple(self.ram.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    from hwtHls.platform.platform import HlsDebugBundle
    u = CounterArray()
    print(to_rtl_str(u, target_platform=Artix7Slow(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

