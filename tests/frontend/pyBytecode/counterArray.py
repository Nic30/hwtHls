from hwt.hdl.constants import WRITE, READ
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn, propagateClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeInline
from hwt.hdl.types.bits import Bits


class HazardHandlerBram():
    """
    After circuit is scheduled it is possible detect access collisions to externally mapped busses.
    There are several reasons why the data access conflict can appear.
     do usually happen due , but in this case there are more things which can cause conflicts.
    
    1. The memory operations are usually non-atomic and have non-zero latency.
       This implies that the data consistency for meta-state during memory update must be explicitly asserted on the side of user of memory resource.
       The latency of memory resource may change in time.
    2. There may be multiple concurrent IO operations related to a single memory.
    3. The control flow of the original program may be distributed to multiple circuits which may result in reordered IO operations or dynamic latency of the IO.
        This implies a secondary issue. For Read-Modify-Write (RMW) operations the ownership of the data is transfered to user of memory, however this means
        That the user have to assert data consistency for the records which are temporally moved from memory resource.
    
    * Point 3 in previous list implies that the user of memory must keep address for every data which is borrowed from the memory.
        In a trivial case the borrowed data can be recognized a a data on path from read to a write with a same address.
        However, in a generic case, it is unrecognizable and must be marked by user.
        However the presence of an address alone is not sufficient to resolve data collision without blocking.
        The address can be only used to block read until read data is written back from user component. 
    * In addition to previous note the RMW operations are usually commutative and distributive (e.g. counter update)
        It is usually possible to merge several writes to same address or somehow reuse read data and aggregate updates.
        However the exact algorithm of read reuse/write aggregation is known only to a user and can not be generally extracted from an user application code.
        In addition it is hard to reliably recognize the original read data in a scheduled netlist,
        but only in scheduled netlist, it is know that there will be some data access collision.
    
    * It is essential to write data to memory as soon as possible because every pending data needs to be checked for collisions and can potentially stall reads.
        * The latency between read and write is affected by several things.
            * The latency of the operation in user code.
                * This is optimized by user and by generic optimizations.
            * The read latency.
                * This is a physical restriction but can be speculated or forwarded from write.
            * The write, write confirm latency.  
                * This can eliminated in the significant of FPGA resources.
        * The common way how to deal with issues related to write latency is to user Load-Store-Unit (LSU).
          https://www.llvm.org/docs/CommandGuide/llvm-mca.html#load-store-unit-and-memory-consistency-model
          This component has queue for read and write operations and can update read transactions with just written data
          which results in reduced write/write confirm latency. Which reduces the time between start of the read to write confirm
          which is critical for FPGA resource consumption.
    
    The steps of generic hazard handler:
    
        * Detect all IO related to this bus,
        * Detect potential Read-After-Write (RAW) conflicts.
            * Write-After-Write (WAW) and Write-After-Read (WAR) should be conflicts should be asserted by scheduler and LSU functionality.
        * If scheduling allows, forward write data to a read (write is exactly in next or same clock cycle)
        * If all IO operations are done from same FSM just add check for collision with a previous write if the read and write is in same clk.
        * If IO operations are in pipeline or in multiple arch elements the situation is more complex:
            * Try eliminate write latency using LSU.
            * If write is scheduled later than in next clock cycle the write latency elimination is not sufficient to remove RAW.
              Use user provide write aggregation / read reuse scheme or instantiate blocking logic for a critical section which will block
              if section can contain potentially colliding data.
    
    """


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

    def resetRam(self, hls: HlsScope, ram: BramArrayProxy):
        i = Bits(ram.indexT.bit_length()).from_py(0)
        # [todo] if bit slicing is used on i, the llvm generates uglygep because it is not recognizing
        # the bit slicing and this ugly GEP uses 64b pinter type
        while BIT.from_py(1):
            hls.write(0, ram[i])
            if i._eq(self.ITEMS - 1):
                break
            i += 1

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
    u = CounterArray()
    print(to_rtl_str(u, target_platform=Artix7Slow(debugDir="tmp")))

