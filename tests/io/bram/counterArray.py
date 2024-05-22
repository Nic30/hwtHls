#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.constants import WRITE, READ
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.math import log2ceil
from hwtHls.architecture.transformation.utils.memoryAccessUtils import detectReadModifyWrite, \
    ArchImplementStaling, ArchImplementWriteForwarding
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock
from tests.frontend.pyBytecode.stmWhile import TRUE


class BramCounterArray0nocheck(HwModule):
    """
    Array of counters stored in BRAM without any data consystency handling.
    """

    def _config(self) -> None:
        self.ITEMS = HwParam(4)
        self.CNTR_WIDTH = HwParam(16)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.incr = HwIODataRdVld()

        t = RamSingleClock()
        t.ADDR_WIDTH = self.incr.DATA_WIDTH = log2ceil(self.ITEMS - 1)
        t.DATA_WIDTH = self.CNTR_WIDTH
        t.PORT_CNT = (READ, WRITE)
        self.ram = t

    @hlsBytecode
    def resetRam(self, hls: HlsScope, ram: BramArrayProxy):
        i = HBits(ram.indexT.bit_length()).from_py(0)
        # [todo] if bit slicing is used on i, the llvm generates uglygep because it is not recognizing
        # the bit slicing and this ugly GEP uses 64b pinter type
        while TRUE:
            hls.write(0, ram[i])
            if i._eq(self.ITEMS - 1):
                break
            i += 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        # reset
        # PyBytecodeInline(self.resetRam)(hls, ram)
        while TRUE:
            index = hls.read(self.incr).data
            # The ram[index] can not be read until write is finished or there is an LSU to update read data later
            d = hls.read(ram[index]).data + 1
            hls.write(d, ram[index])
            # PyBytecodeLLVMLoopUnroll(True, 2)

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, MultiPortGroup(self.ram.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        hls.addThread(mainThread)
        hls.compile()
        assert len(hls._threads[0].toHw.scheduler.resourceUsage) == 2, (
            "Intended only for 2 cycle operation", len(hls._threads[0].toHw.scheduler.resourceUsage))


class BramCounterArray1hardcodedWriteForwarding(BramCounterArray0nocheck):
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
        while TRUE:
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


class BramCounterArray3stall(BramCounterArray0nocheck):
    """
    Store last N addresses and stall read if current read address in in last N addresses.
    Stalling of read is done using extraCond flag.
    Flush of last N address pipeline happens every clock. It is implemented using non blocking read of control
    from block where read is.
    """

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, MultiPortGroup(self.ram.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)

        def implementStaling(hls: HlsScope, thread: HlsThreadFromPy):
            netlist: HlsNetlistCtx = thread.toHw
            return ArchImplementStaling(netlist, ram)

        mainThread.archNetlistCallbacks.append(implementStaling)
        hls.addThread(mainThread)
        hls.compile()
        assert len(hls._threads[0].toHw.scheduler.resourceUsage) == 2, (
            "Intended only for 2 cycle operation", len(hls._threads[0].toHw.scheduler.resourceUsage))


class BramCounterArray4WriteForwarding(BramCounterArray0nocheck):
    """
    Array counter with automatically instantiated LSU for write->read latency.
    """

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, MultiPortGroup(self.ram.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)

        def implementWriteForwarding(hls: HlsScope, thread: HlsThreadFromPy):
            netlist: HlsNetlistCtx = thread.toHw
            return ArchImplementWriteForwarding(netlist, ram)

        mainThread.archNetlistCallbacks.append(implementWriteForwarding)
        hls.addThread(mainThread)
        hls.compile()
        assert len(hls._threads[0].toHw.scheduler.resourceUsage) == 2, (
            "Intended only for 2 cycle operation", len(hls._threads[0].toHw.scheduler.resourceUsage))


    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        # reset
        # PyBytecodeInline(self.resetRam)(hls, ram)
        p = hls.parentHwModule._target_platform
        p.runHlsNetlistPostSchedulingPasses = self.createGenerateLSU(ram, p.runHlsNetlistPostSchedulingPasses)
        while TRUE:
            index = hls.read(self.incr).data
            # The ram[index] can not be read until write is finished or there is an LSU to update read data later
            d = hls.read(ram[index]).data + 1
            hls.write(d, ram[index])
            # PyBytecodeLLVMLoopUnroll(True, 2)


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    from hwtHls.platform.platform import HlsDebugBundle
   
    m = BramCounterArray4WriteForwarding()
    m.CLK_FREQ = int(10e6)
    print(to_rtl_str(m, target_platform=Artix7Slow(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

