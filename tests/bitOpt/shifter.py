"""
:attention: Optimizations in LLVM.IR/LLVM.MIR should result always in a flat MUX in LLVM.MIR for
    any shifter implementation in user code. Under normal conditions an implementation of shifter
    is something which should be resolved during netlist optimizations.
:attention: It is undesired to have complicated shifter description in user code because it increases probability
    that some optimization will not work as intended. Implementation specifics of this type should be
    resolved on netlist level.
"""

from typing import Optional

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Signal
from hwt.interfaces.utils import addClkRstn
from hwt.math import log2ceil, isPow2
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.interfaces.hsStructIntf import HsStructIntf


class ShifterLeft0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.i = Signal(Bits(self.DATA_WIDTH))
        self.sh = Signal(Bits(log2ceil(self.DATA_WIDTH)))
        self.o = Signal(Bits(self.DATA_WIDTH))._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Shift implemented as a loop unrolled in the frontend
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            for i in range(self.DATA_WIDTH):
                if sh._eq(i):
                    break
                else:
                    v <<= 1
            hls.write(v, self.o)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class ShifterLeft1(ShifterLeft0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Loop unrolled in frontend which implements shift left
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            for i in range(v._dtype.bit_length()):
                if sh._eq(i):
                    # :note: following code would not work because i would be shapshoted when first seeing this hw block
                    # v <<= i # this block would be actually outside of the loop
                    # break
                    v = v << i

            hls.write(v, self.o)


class ShifterLeftUsingHwLoopWithWhileNot0(ShifterLeft0):

    def _config(self) -> None:
        super(ShifterLeftUsingHwLoopWithWhileNot0, self)._config()
        self.UNROLL_META: Optional[PyBytecodeLLVMLoopUnroll] = Param(None)
        self.FN_META: Optional[PyBytecodeLLVMLoopUnroll] = Param(None)
        

    def _declr(self) -> None:
        """
        Use handshake for sync of IO because the implementation may not be fully pipelined.
        """
        addClkRstn(self)
        self.i = HsStructIntf()
        self.sh = HsStructIntf()
        self.sh.T = Bits(log2ceil(self.DATA_WIDTH))
        self.o = HsStructIntf()._m()

        self.i.T = self.o.T = Bits(self.DATA_WIDTH)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Sequential loop which implements shift left
        """
        self.FN_META
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            while sh != 0:
                v <<= 1
                sh -= 1
                self.UNROLL_META

            hls.write(v, self.o)


class ShifterLeftUsingHwLoopWithBreakIf0(ShifterLeftUsingHwLoopWithWhileNot0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Sequential loop which implements shift left
        """
        self.FN_META
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            while BIT.from_py(1):
                if sh._eq(0):
                    break
                v <<= 1
                sh -= 1
                self.UNROLL_META

            hls.write(v, self.o)


class ShifterLeftBarrelUsingLoop0(ShifterLeft0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Barrel shifter described using loop.
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            shWidth = sh._dtype.bit_length()
            for isLast, level in iter_with_last(range(shWidth)):
                # level 0 shifts by 1 or by 0, level 1 shifts by 2 or 0, 4 or 0 ...
                shAmount = 1 << level
                # build level of multiplexers
                v = sh[level]._ternary(v << shAmount, v)
                if isLast:
                    hls.write(v, self.o)


class ShifterLeftBarrelUsingLoop1(ShifterLeft0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Same as ShifterLeftBarrelUsingLoop0 just with "if" instead of _ternary.
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            shWidth = sh._dtype.bit_length()
            for isLast, level in iter_with_last(range(shWidth)):
                # level 0 shifts by 1 or by 0, level 1 shifts by 2 or 0, 4 or 0 ...
                shAmount = 1 << level
                # build level of multiplexers
                if sh[level]:
                    v <<= shAmount

                if isLast:
                    hls.write(v, self.o)


class ShifterLeftBarrelUsingLoop2(ShifterLeft0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Same as ShifterLeftBarrelUsingLoop2 just with write outside of the loop.
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            shWidth = sh._dtype.bit_length()
            for level in range(shWidth):
                # level 0 shifts by 1 or by 0, level 1 shifts by 2 or 0, 4 or 0 ...
                shAmount = 1 << level
                # build level of multiplexers
                if sh[level]:
                    v <<= shAmount

            hls.write(v, self.o)


class ShifterLeftBarrelUsingPyExprConstructor(ShifterLeft0):

    def buildBarrelShiftLeft(self, sh: RtlSignal, v: RtlSignal):
        """
        :attention: This is normal python function which is not subject to a HLS
            it only generates the expression which is then returned.
        """
        shWidth = sh._dtype.bit_length()

        if shWidth > 1:
            subSh = sh[shWidth - 1:]  # slice off MSB
            v = self.buildBarrelShiftLeft(subSh, v)

        shMsb = sh[shWidth - 1]
        shAmount = 1 << (shWidth - 1)
        res = shMsb._ternary(v << shAmount, v)
        return res

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Implement barrel shifter using recursive expression construction function.
        
        level 0 of multiplexers is shifting by 0 or 1b, level 1 by 0 or 2b, ...
        """
        while BIT.from_py(1):
            v = hls.read(self.i).data
            sh = hls.read(self.sh).data
            shiftedV = self.buildBarrelShiftLeft(sh, v)
            hls.write(shiftedV, self.o)

