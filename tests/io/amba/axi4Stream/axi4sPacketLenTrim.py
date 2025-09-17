#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaInstruction import PyBytecodeIntrinsicAssume,\
    setHasNoUnsignedWrap
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from pyMathBitPrecise.bit_utils import round_up_to_multiple_of
from tests.io.amba.axi4Stream.axi4sCopyByteByByte import Axi4SPacketCopyByteByByteHs



class Axi4SPacketTrimByteByByte0(HwModule):
    """
    Trim packet to specified size (OUT_MAX_LEN).
    """

    def hwConfig(self) -> None:
        Axi4SPacketCopyByteByByteHs.hwConfig(self)
        self.OUT_MAX_LEN = HwParam(64)
        self.OUT_DATA_WIDTH = None

    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = True
        self.tx: Axi4Stream = Axi4Stream()._m()
        self.tx.USE_STRB = True

        if self.OUT_DATA_WIDTH is None:
            # rx, tx has same DATA_WIDTH
            self.tx.DATA_WIDTH = self.OUT_DATA_WIDTH = self.DATA_WIDTH
        else:
            self.tx.DATA_WIDTH = self.OUT_DATA_WIDTH

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")
            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame()

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1)).from_py(0)
            limitExceeded = BIT.from_py(0)
            while b1:
                PyBytecodeBlockLabel("loop.pkt.read")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(8), reliable=False)
                # copy to output only if current packet length does not exceeds the limit
                tx.write(d.data, eof=d._isEoF() | curLen._eq(self.OUT_MAX_LEN - 1))

                # del d is not necessary is there to limit live of d variable which is useful during debug
                if d._isEoF() | curLen._eq(self.OUT_MAX_LEN):
                    PyBytecodeBlockLabel("loop.pkt.stopWrite")
                    limitExceeded = ~d._isEoF()
                    # :note: avoid using masked write as it leads to less readable code and needs to be lowered anyway
                    del d
                    break
                curLen += 1
                del d

            # :note: it is hard to merge these two loops into 1, 1 loop is more hw friendly
            #  and simplifies other transformations

            # :note: eof in reverse order because frame processing behaves a a lock on IO
            # and this order is required to prevent deadlock
            tx.writeEndOfFrame()
            if limitExceeded:
                # drop redundant rx data
                while b1:
                    PyBytecodeBlockLabel("loop.pkt.drop")
                    Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                    d = rx.read(HBits(8), reliable=False)
                    if d._isEoF():
                        PyBytecodeBlockLabel("loop.pkt.drop.last")
                        del d
                        break
                    del d

            rx.readEndOfFrame()

    def hwImpl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        tx = IoProxyAxi4Stream(hls, self.tx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, rx, tx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SPacketTrimByteByByte1(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte0 with shouldBreak extracted before write
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")
            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame()

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1)).from_py(0)
            limitExceeded = b0
            while b1:
                PyBytecodeBlockLabel("loop.pkt.read")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(8), reliable=False)
                shouldBreak = d._isEoF() | curLen._eq(self.OUT_MAX_LEN)
                curLen += 1
                tx.write(d.data, eof=shouldBreak)

                if shouldBreak:
                    PyBytecodeBlockLabel("loop.pkt.stopWrite")
                    limitExceeded = ~d._isEoF()
                    del d
                    break
                del d
            tx.writeEndOfFrame()
            if limitExceeded:
                # drop redundant rx data
                while b1:
                    PyBytecodeBlockLabel("loop.pkt.drop")
                    Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                    d = rx.read(HBits(8), reliable=False)
                    if d._isEoF():
                        PyBytecodeBlockLabel("loop.pkt.drop.last")
                        del d
                        break
                    del d

            rx.readEndOfFrame()

class Axi4SPacketTrimByteByByte2(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte0 with a single loop
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")

            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame(mayBecomeFlushable=False)

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1) + 1).from_py(0)
            # lastMaksBit = b1
            while b1:
                PyBytecodeBlockLabel("loop.pkt.read")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(8), reliable=False)
                # add assumption to let LLVM know that if there is one 0 bit in mask it is not necessary to check remaining bits
                # PyBytecodeIntrinsicAssume()(lastMaksBit | ~d.strb) # lastMaksBit == 0 implies d.mask == 0
                wEn = d._isValid() & (curLen != self.OUT_MAX_LEN)
                if wEn:
                # if d._isValid() & (curLen != self.OUT_MAX_LEN):
                    PyBytecodeBlockLabel("loop.pkt.write")
                    tx.write(d.data,
                             eof=d._isEoF() | curLen._eq(self.OUT_MAX_LEN - 1))
                    # :note: it is hard to extract masked write because writes are
                    # dispersed between reads
                    curLen += 1

                PyBytecodeBlockLabel("loop.pkt.lastCheck")
                # lastMaksBit = d.strb
                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.last")
                    del d
                    break
                PyBytecodeBlockLabel("loop.pkt.end")
                del d

            PyBytecodeBlockLabel("loop.pkt.eof")
            tx.writeEndOfFrame()
            rx.readEndOfFrame()


class Axi4SPacketTrimByteByByte3(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte2b with < instead of != for limit check
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")

            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame(mayBecomeFlushable=False)

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1) + 1).from_py(0)
            # lastMaksBit = b1
            while b1:
                PyBytecodeBlockLabel("loop.pkt.read")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(8), reliable=False)
                # add assumption to let LLVM know that if there is one 0 bit in mask it is not necessary to check remaining bits
                # PyBytecodeIntrinsicAssume()(lastMaksBit | ~d.strb) # lastMaksBit == 0 implies d.mask == 0
                wEn = d._isValid() & (curLen < self.OUT_MAX_LEN)
                if wEn:
                # if d._isValid() & (curLen != self.OUT_MAX_LEN):
                    PyBytecodeBlockLabel("loop.pkt.write")
                    tx.write(d.data,
                             eof=d._isEoF() | curLen._eq(self.OUT_MAX_LEN - 1))
                    # :note: it is hard to extract masked write because writes are
                    # dispersed between reads
                    curLen += 1

                PyBytecodeBlockLabel("loop.pkt.lastCheck")
                # lastMaksBit = d.strb
                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.last")
                    del d
                    break
                PyBytecodeBlockLabel("loop.pkt.end")
                del d

            PyBytecodeBlockLabel("loop.pkt.eof")
            tx.writeEndOfFrame()
            rx.readEndOfFrame()


"""
How is Axi4SPacketTrimByteByByte4 compiled:

* code starts as a loop over bytes described in the :meth:`Axi4SPacketTrimByteByByte4.mainThread`
 * this lop iterates bytes, and checks if the size limit is not exceeded
 * :note: Single byte read implies 0 or 1 byte write
 * for human it is easy to stop that the write is performed until the limit is reached and then
   it data is just dropped and never written in this frame again
   Compiler however have to prove that iteration has exactly this form and the behavior of
   the loop is driven from flags from data of the stream and there are originally
   no assumptions about strb/last flags from from axi4 stream chunks thus
   by default LLVM can not recognize loop behavior at all.

 * After initial simplification and tmp lowering the code will endup in the clear SSA for just a single loop
   for packet bytes and for packets

.. code-block::llvm
    define void @main(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
    bb0:
      br label %loop.pkt
    
    loop.pkt:
      call void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %rx) #2
      call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #2
      br label %loop.pkt.read
    
    loop.pkt.read:
      %curLen.0 = phi i16 [ 0, %loop.pkt ], [ %curLen.1, %loop.pkt.lastCheck ]
      ...
      br i1 %wEn, label %loop.pkt.write, label %loop.pkt.lastCheck
    
    loop.pkt.write:
      ...
      call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %6) #2
      br label %loop.pkt.lastCheck
    
    loop.pkt.lastCheck:
      %curLen.1 = phi i16 [ %8, %loop.pkt.write ], [ %curLen.0, %loop.pkt.read ]
      ...
      br i1 %rx_read_last7, label %loop.pkt.eof, label %loop.pkt.read, !llvm.loop !6
    
    loop.pkt.eof:
      call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #2
      call void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %rx) #2
      br label %loop.pkt
    }
   
* Then the loop for bytes is unrolled, which generates sequence of (read, write){N}
  as the reads and writes are volatile LLVM can not reorder them freely.
  It is highly desired that the reads writes are merged together because
  lowering of them would require handling of all possible offsets. Where the chunk
  of data may be in the current word. This can potentially generate very large
  amount of code if there is lot of chunks and the word is wide. (Note that the
  worst case here is the copy of bytes which is exactly the code bellow.)
  But the main problem is that if the code combines more stream interfaces (e.g. 1 for read
  1 for write as it is in this case.) The problem of in word offset will cross product
  as each handler for one interface will need to have also all handlers for
  each offset of other interface. This practically means that compilation of a simple
  copy at 8B will take minutes to finish and 16B will not finish in hour wall time.
  Thus it is necessary to fix order of reads and writes and then merge them if possible.


* Initial write sink is implemented in StreamLoopUnrollPass/sinkStreamWritesInLoop
  It is highly desired that the stores are sinked before CFG optimizations before
  then it could be much harder to guess the initial order of writes.

  However the code of the loop body has form of chained if-then blocks with additional exit on last or limit,
  and there is no common successor to hoist writes into.
  From this reason we are left with only option to create a new one and create a block
  for every write to implement write condition.
  This immediately causes another issue. As the common successor is now visited on loop break
  and continue the analysis of the loop effect just got much harder.    

* This raw loop can not be efficiently analyzed and the section with writes must be lowered
  to masked writes. Note that we can not generate merged masked writes in previous step
  because the loop Scalar Evolution Analysis was already practically impossible after unroll
  and before unroll it was also hard because each iteration works with different bits from
  input.
* This merging, sinking and hoisting of stream operations is done in SimplifyCfg2.
  The goal is to prove that the condition for next read/write is implied from predecessor.
  * In this case for reads it is easy because the condition for next read is just and of previous conditions
    and next !last flag.
  * For writes however this is impossible without knowledge of about implications about mask and eof.
   If !eof ==> all mask bits set. If eof mask bit n set implies mask bit n-1 set or n==0.
   This knowledge can be injected trough llvm.assume. (However llvm does not have bit get instruction,
   or concatenation.) To make this truly work there is isImpliedConditionAndOrTree
   which implements implication query for bit intrinsics KNF, DNF expressions and few
   additional expressions with non-wrapping arithmetic.
* SimplifyCfg2 converts phis and +1 adders to sequence of selects and +1 adders. This sequence
  is then collected and converted to ctpop, ctpop (popcount, number of 1 in bit vector)
  is used because it can not be proved that it is ctto (trailing one count, number of 1 from lsb side) yet.
  However all intermediate values are used outside for write enable conditions. This is rewritten using umax and icmp.
  This is implemented in HwtHlsInstCombiner.
  * ctpop is then converted to cttz(~x) (which is llvm equivalent for ctto)
  
  
"""
class Axi4SPacketTrimByteByByte4(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte2 with setHasNoUnsignedWrap
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")

            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame(mayBecomeFlushable=False)

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1) + 1).from_py(0)
            # lastMaksBit = b1
            while b1:
                PyBytecodeBlockLabel("loop.pkt.read")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(8), reliable=False)
                # add assumption to let LLVM know that if there is one 0 bit in mask it is not necessary to check remaining bits
                # PyBytecodeIntrinsicAssume()(lastMaksBit | ~d.strb) # lastMaksBit == 0 implies d.mask == 0
                wEn = d._isValid() & (curLen != self.OUT_MAX_LEN)
                if wEn:
                # if d._isValid() & (curLen != self.OUT_MAX_LEN):
                    PyBytecodeBlockLabel("loop.pkt.write")
                    tx.write(d.data,
                             eof=d._isEoF() | curLen._eq(self.OUT_MAX_LEN - 1))
                    # :note: it is hard to extract masked write because writes are
                    # dispersed between reads
                    curLen = setHasNoUnsignedWrap(curLen + 1)

                PyBytecodeBlockLabel("loop.pkt.lastCheck")
                # lastMaksBit = d.strb
                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.last")
                    del d
                    break
                PyBytecodeBlockLabel("loop.pkt.end")
                del d

            PyBytecodeBlockLabel("loop.pkt.eof")
            tx.writeEndOfFrame()
            rx.readEndOfFrame()


class Axi4SPacketTrimByteByByte5(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte0 with a single loop and manual unroll
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        while b1:
            PyBytecodeBlockLabel("loop.pkt")
            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame()

            curLen = HBits(log2ceil(self.OUT_MAX_LEN + 1)).from_py(0)
            while b1:
                PyBytecodeBlockLabel("loop.pkt.word")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(self.DATA_WIDTH), reliable=False)
                for i in range(self.DATA_WIDTH // 8):
                    nonEoF = (curLen != self.OUT_MAX_LEN) & d.strb[i]
                    if nonEoF:
                        PyBytecodeBlockLabel("loop.pkt.word.write.byte")
                        # :note: writes are hard to merge into masked write because all of them have non trivial condition
                        tx.write(d.data[(i + 1) * 8:i * 8], eof=~nonEoF)
                        curLen += 1

                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.word.last")
                    del d
                    break
                del d

            PyBytecodeBlockLabel("loop.pkt.eof")
            tx.writeEndOfFrame()
            rx.readEndOfFrame()


class Axi4SPacketTrimByteByByte6(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte0 with a single loop and manual unroll and masked write
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        WORLD_SIZE = self.DATA_WIDTH // 8
        while b1:
            PyBytecodeBlockLabel("loop.pkt")
            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame()

            curLen = HBits(log2ceil(round_up_to_multiple_of(self.OUT_MAX_LEN, WORLD_SIZE) + WORLD_SIZE + 1)).from_py(0)
            while b1:
                PyBytecodeBlockLabel("loop.pkt.word")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(min(self.DATA_WIDTH, self.OUT_MAX_LEN * 8)), reliable=False)
                if curLen < self.OUT_MAX_LEN:
                    PyBytecodeBlockLabel("loop.pkt.word.write")
                    curLen += WORLD_SIZE
                    # :attention: last word mask is not correct if not aligned
                    tx.write(d.data, mask=d.strb, eof=(curLen >= self.OUT_MAX_LEN) | d._isEoF())
                    # data must wait for EoF because,
                    # it is not predicated that there will be some write in next iterations
                    # or control flow will reach EoF

                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.word.last")
                    del d
                    break
                del d
            tx.writeEndOfFrame()
            rx.readEndOfFrame()


class Axi4SPacketTrimByteByByte7(Axi4SPacketTrimByteByByte0):
    """
    Axi4SPacketTrimByteByByte0 with a single loop and manual unroll and masked write
    and tx.writeEndOfFrame() hoisted into loop
    """

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        assert self.OUT_MAX_LEN >= 0, self.OUT_MAX_LEN
        WORLD_SIZE = self.DATA_WIDTH // 8
        while b1:
            PyBytecodeBlockLabel("loop.pkt")
            # pass rx packet to tx output with length limit
            rx.readStartOfFrame()
            tx.writeStartOfFrame()

            curLen = HBits(log2ceil(round_up_to_multiple_of(self.OUT_MAX_LEN, WORLD_SIZE) + WORLD_SIZE + 1)).from_py(0)
            while b1:
                PyBytecodeBlockLabel("loop.pkt.word")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = rx.read(HBits(min(self.DATA_WIDTH, self.OUT_MAX_LEN * 8)), reliable=False)
                if curLen < self.OUT_MAX_LEN:
                    PyBytecodeBlockLabel("loop.pkt.word.write")
                    curLen += WORLD_SIZE
                    # :attention: last word mask is not correct if not aligned
                    eof = (curLen >= self.OUT_MAX_LEN) | d._isEoF()
                    tx.write(d.data, mask=d.strb, eof=eof)

                if d._isEoF():
                    PyBytecodeBlockLabel("loop.pkt.word.last")
                    del d
                    break
                del d

            tx.writeEndOfFrame()
            rx.readEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    import sys

    sys.setrecursionlimit(int(1e6))

    m = Axi4SPacketTrimByteByByte4()
    m.OUT_MAX_LEN = 162
    m.DATA_WIDTH = 8 * 8
    m.UNROLL = PyBytecodeStreamLoopUnroll
    # m.UNROLL = False
    # m.OUT_DATA_WIDTH = 8
    p = Artix7Medium(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                     LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                     # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
                     # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                     # LLVM_CLI_COMMON_OPTS.printBefore("hwtHls::HwtHlsSimplifyCFGPass"),
                     # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::HwtHlsSimplifyCFGPass"),
                     # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::HwtHlsInstCombinePass"),
                     # LLVM_CLI_COMMON_OPTS.printBefore("hwtHls::SlicesMergePass"),
                     # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::SlicesMergePass"),
                     ]
    )
    print(to_rtl_str(m, target_platform=p))

