from typing import Union

from hwt.doc_markers import internal
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwt.serializer.generic.indent import getIndent
from pyMathBitPrecise.bit_utils import mask
from hwtHls.llvm.llvmIr import Type

# https://github.com/WangXuan95/FPGA-FixedPoint/blob/master/RTL/fixedpoint.v
# https://www.allaboutcircuits.com/technical-articles/fixed-point-representation-the-q-format-and-addition-examples/
(
 ROUND_HALF_EVEN,  # nearest with ties going to nearest even integer. (c fp default)
# ROUND_HALF_DOWN, # nearest with ties going towards 0.
 ROUND_HALF_UP,  #  nearest with ties going away from 0.

 ROUND_DOWN,  #  towards 0.
 ROUND_CEILING,  # towards inf.
 ROUND_FLOOR,  # towards -Inf.

 # ROUND_UP, # away from 0.
 # ROUND_05UP, # away from 0 if last digit after rounding towards zero would have been 0 or 5;
              # otherwise towards 0.
 ) = range(5)

SATURATE_NONE = 0  # no saturation, operations may overflow
SATURATE_INF = 3  # saturate +/- inf

"""
    
Example Q-number ranges:
.. code-block::
    Q4.4
    Range:      -8 to 7.9375 (7 + 15/16)
    Precision:  0.0625 (1/16)

    Q16.16
    Range:      -32768 to 32767.9999847...
    Precision:  0.0000152... (1/65536)

Example of Q numbers
.. code-block::
      10.01        - 1.75
      10.11        - 1.25
     110.11        - 1.25
     011.010         3.25
    0011.1010        3.625
    0100.0001        4.0625
    1110.1000      - 1.5

Example of negative Q number
.. code-block::
    1.5 = 1 + 1/2 = 0001.1000

    Start:  0001.1000 (1.5)
    Invert: 1110.0111
    Add 1:  0000.0001
    Result: 1110.1000 (-1.5)


.. table:: Example of rounding to integers using the IEEE 754 rules

    =========================================== =========================
    Mode                                         Example value
    =========================================== =========================
                                                 +11.5  +12.5 −11.5 −12.5
     ========================================== ====== ====== ===== =====
     to nearest, ties to even (half_even)        +12.0  +12.0 −12.0 −12.0
     to nearest, ties away from zero (half_up)   +12.0  +13.0 −12.0 −13.0
     toward 0  (down)                            +11.0  +12.0 −11.0 −12.0
     toward +∞ (ceil)                            +12.0  +13.0 −11.0 −12.0
     toward −∞ (floor)                           +11.0  +12.0 −12.0 −13.0 
     ========================================== ====== ====== ===== =====

.. table:: Example of rounding to integers using the IEEE 754 rules in binary
    ========================================== ========================================== ===================  =================== ====================== ======================
    Q8.1 (dec, hex, bin)                        rule                                       11.5, 17, 01011.1    12.5, 19, 01100.1   -11.5, e9, 1110100.1   -12.5, e7, 1110011.1
    ========================================== ========================================== ===================  =================== ====================== ======================
    to nearest, ties to even (half_even)        if round_bit && newLsb: x += 1; trunc(x)   12.0, 18, 01100.0    12.0, 18, 01100.0   −12.0, e8, 1110100.0   −12.0, e8, 1110100.0
    to nearest, ties away from zero (half_up)   if round_bit && x >= 0: x += 1; trunc(x)   12.0, 18, 01100.0    13.0, 1a, 01101.0   −12.0, e8, 1110100.0   −13.0, e6, 1110011.0
    toward 0  (down)                            if round_bit && x < 0: x += 1; trunc(x)    11.0, 16, 01011.0    12.0, 18, 01100.0   −11.0, ea, 1110101.0   −12.0, e8, 1110100.0
    toward +∞ (ceil)                            if round_bit: x += 1; trunc(x)             12.0, 18, 01100.0    13.0, 1a, 01101.0   −11.0, ea, 1110101.0   −12.0, e8, 1110100.0
    toward −∞ (floor)                           trunc(x)                                   11.0, 16, 01011.0    12.0, 18, 01100.0   −12.0, e8, 1110100.0   −13.0, e6, 1110011.0
    ========================================== ========================================== ===================  =================== ====================== ======================
"""

HFixedPointQComaptibleValue = Union["HFixedPointQConst", "HFixedPointQRtlSignal", float, int, None]


class HFixedPointQ(HdlType):
    """
    Fixed point number in Q notation

    :ivar int_bit_length: number of bits in integer part (including sign bit), (usually noted m)
    :ivar frac_bit_length: number of bits in fraction part (usually noted Q) 
    
    :note: ARM version includes sign bit in integer bit count
        Texas Instruments version does not.
        This type follows ARM notation so signed Q8.4 means 8b for int part of signed 2-complement int,
        and 4b for fract part (also in 2-complement). 

    :note: common overflow rule applies:
        If both our operands are positive and the result is negative, then overflow must have occurred.
        Similarly, if both our operands are negative and the result is positive, then it has overflowed too.
    
    """

    _PRECOMPUTE_CONSTANT_SIGNALS = False

    def __init__(self,
                 int_bit_length,
                 frac_bit_length,
                 signed=True,
                 roundig=ROUND_HALF_EVEN,
                 saturation=SATURATE_INF,
                 name=None,
                 const=False,):
        HdlType.__init__(self, const=const)
        self.name = name
        self.int_bit_length = int_bit_length
        self.frac_bit_length = frac_bit_length
        self.signed = signed
        self.roundig = roundig
        self.saturation = saturation
        self._all_mask = mask(self.bit_length())

    def all_mask(self):
        return self._all_mask

    def bit_length(self) -> int:
        return self.int_bit_length + self.frac_bit_length

    def __eq__(self, value:object) -> bool:
        return (
            isinstance(value, self.__class__) and
            self.int_bit_length == value.int_bit_length and
            self.frac_bit_length == value.frac_bit_length and
            self.signed == value.signed and
            self.roundig == value.roundig and
            self.saturation == value.saturation
        )

    def __hash__(self) -> int:
        return hash((
            self.__class__,
            self.signed,
            self.roundig,
            self.saturation,
            self.int_bit_length,
            self.frac_bit_length
        ))

    @internal
    @classmethod
    def get_auto_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixedpointCast import castHFixedPointQ
        return castHFixedPointQ

    @internal
    @override
    @classmethod
    def get_auto_cast_HConst_fn(cls):
        from tests.math.fixp.fixedpointCast import castHFixedPointQ
        return castHFixedPointQ

    @internal
    @classmethod
    def get_reinterpret_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixedpointCast import reinterpretCastHFixedPointQ
        return reinterpretCastHFixedPointQ

    @internal
    @override
    @classmethod
    def get_reinterpret_cast_HConst_fn(cls):
        from tests.math.fixp.fixedpointCast import reinterpretCastHFixedPointQ
        return reinterpretCastHFixedPointQ

    @internal
    @override
    @classmethod
    def getConstCls(cls):
        try:
            return cls._constCls
        except AttributeError:
            from tests.math.fixp.fixedpointConst import HFixedPointQConst
            cls._constCls = HFixedPointQConst
            return cls._constCls

    @internal
    @override
    @classmethod
    def getRtlSignalCls(cls):
        try:
            return cls._rtlSignalCls
        except AttributeError:
            from tests.math.fixp.fixedpointRtlSignal import HFixedPointQRtlSignal
            cls._rtlSignalCls = HFixedPointQRtlSignal
            return cls._rtlSignalCls

    def toLlvm(self, toLlvm: "ToLlvmIrTranslator"):
        return Type.getIntNTy(toLlvm.ctx, self.bit_length())

    def __repr__(self, indent=0, withAddr=None, expandStructs=False):
        """
        :param indent: number of indentation
        :param withAddr: if is not None is used as a additional
            information about on which address this type is stored
            (used only by HStruct)
        :param expandStructs: expand HStructTypes (used by HStruct and HArray)
        """
        constr = []
        if self.name is not None:
            constr.append('"%s"' % self.name)

        if self.const:
            constr.append("const")

        if self.signed:
            constr.append("signed")

        constr.append(f"Q{self.int_bit_length:d}.{self.frac_bit_length:d}")

        return "%s<%s, %s>" % (getIndent(indent),
                               self.__class__.__name__,
                               ", ".join(constr))
