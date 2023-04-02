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
from hwtHls.io.bram import BramArrayProxy, HlsNetNodeWriteBramCmd
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock
from typing import Callable
from hwtHls.netlist.context import HlsNetlistCtx


class CounterArray0(Unit):

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
        while BIT.from_py(1):
            index = hls.read(self.incr).data
            # The ram[index] can not be read until write is finished or there is an LSU to update read data later
            d = hls.read(ram[index]).data + 1
            hls.write(d, ram[index])
            # PyBytecodeLLVMLoopUnroll(True, 2)

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, tuple(self.ram.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class CounterArray1(CounterArray0):
    """
    Array counter with manually instantiated LSU for 1 clock write->read latency
    """

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


class CounterArray2(CounterArray0):
    """
    Array counter with automatically instantiated LSU for write->read latency.
    """

    @staticmethod
    def detectBramRMW(ram: BramArrayProxy, netlist: HlsNetlistCtx):
        r = None
        w = None
        for o in netlist.outputs:
            if o.dst is ram.interface[0]:
                assert o.cmd == READ
                r = o
            elif o.dst is ram.interface[1]:
                assert o.cmd == WRITE
                w = o
        assert r is not None
        assert w is not None
        clkPeriod: int = r.netlist.normalizedClkPeriod
        r: HlsNetNodeWriteBramCmd
        w: HlsNetNodeWriteBramCmd

        rAddr = r.dependsOn[1]
        wAddr = w.dependsOn[1]
        assert rAddr is wAddr, (rAddr, wAddr)
        rToWClkDiff = (w.scheduledIn[1] // clkPeriod) - (r.scheduledIn[1] // clkPeriod)
        assert rToWClkDiff >= 0
        return r, w, rToWClkDiff

    def createGenerateLSU(self, ram: BramArrayProxy, runHlsNetlistPostSchedulingPasses: Callable[[HlsScope, HlsNetlistCtx], bool]):

        def createLSU(hls: HlsScope, netlist: HlsNetlistCtx):
            """
            If the write and read is not immediate create the circuit which updates read data with just written based on address
            (Load-Store Unit).
            """
            modified = runHlsNetlistPostSchedulingPasses(hls, netlist)
            r, w, rToWClkDiff = self.detectBramRMW(ram, netlist)
            raise NotImplementedError()

            return modified

        return createLSU

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        # reset
        # PyBytecodeInline(self.resetRam)(hls, ram)
        p = hls.parentUnit._target_platform
        p.runHlsNetlistPostSchedulingPasses = self.createGenerateLSU(ram, p.runHlsNetlistPostSchedulingPasses)
        while BIT.from_py(1):
            index = hls.read(self.incr).data
            # The ram[index] can not be read until write is finished or there is an LSU to update read data later
            d = hls.read(ram[index]).data + 1
            hls.write(d, ram[index])
            # PyBytecodeLLVMLoopUnroll(True, 2)


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    from hwtHls.platform.platform import HlsDebugBundle
    u = CounterArray2()
    print(to_rtl_str(u, target_platform=Artix7Slow(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

