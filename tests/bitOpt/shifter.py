"""
:attention: Optimizations in LLVM.IR/LLVM.MIR should result always in a flat MUX in LLVM.MIR for
    any shifter implementation in user code. Under normal conditions an implementation of shifter
    is something which should be resolved during netlist optimizations.
:attention: It is undesired to have complicated shifter description in user code because it increases probability
    that some optimization will not work as intended. Implementation specifics of this type should be
    resolved on netlist level.
"""

from typing import Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.math import log2ceil
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class ShifterLeft0(HwModule):

    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.i = HwIOSignal(HBits(self.DATA_WIDTH))
        self.sh = HwIOSignal(HBits(log2ceil(self.DATA_WIDTH)))
        self.o = HwIOSignal(HBits(self.DATA_WIDTH))._m()

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

    def hwImpl(self) -> None:
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

    def hwConfig(self) -> None:
        super(ShifterLeftUsingHwLoopWithWhileNot0, self).hwConfig()
        self.UNROLL_META: Optional[PyBytecodeLLVMLoopUnroll] = HwParam(None)
        self.FN_META: Optional[PyBytecodeLLVMLoopUnroll] = HwParam(None)

    def hwDeclr(self) -> None:
        """
        Use handshake for sync of IO because the implementation may not be fully pipelined.
        """
        addClkRstn(self)
        self.i = HwIOStructRdVld()
        self.sh = HwIOStructRdVld()
        self.sh.T = HBits(log2ceil(self.DATA_WIDTH))
        self.o = HwIOStructRdVld()._m()

        self.i.T = self.o.T = HBits(self.DATA_WIDTH)

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

