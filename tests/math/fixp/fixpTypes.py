# https://github.com/WangXuan95/FPGA-FixedPoint/blob/master/RTL/fixedpoint.v
# https://www.allaboutcircuits.com/technical-articles/fixed-point-representation-the-q-format-and-addition-examples/
from typing import Union, Self, Optional

from hwt.constants import NOT_SPECIFIED
from hwt.doc_markers import internal
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwt.serializer.generic.indent import getIndent
from hwt.serializer.hwt.serializer import ToHdlAstHwt
from hwtHls.llvm.llvmIr import HFloatTmpConfig, Type, HFloatTmpRounding, HFloatTmpSaturation
from pyMathBitPrecise.bit_utils import mask

HFixedPointQComaptibleValue = Union["HFixedPointQConst", "HFixedPointQRtlSignal", float, int, None]

# Fixed point
#   add/sub is same as for int
#     * saturation https://forum.digikey.com/t/n-bit-saturated-math-carry-look-ahead-combinational-adder-design-in-vhdl/13366
#   multiplication produces twice the bits, (on bout sides, Q4.4 * Q4.4 = Q8.8, truncatable by taking middle bits)
#   https://projectf.io/posts/fixed-point-numbers-in-verilog/
#  https://github.com/Schweitzer-Engineering-Laboratories/fixedpoint/blob/master/fixedpoint/fixedpoint.py


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

    """

    _PRECOMPUTE_CONSTANT_SIGNALS = False

    def __init__(self,
                 int_bit_length: int,
                 frac_bit_length: int,
                 signed=True,
                 rounding=HFloatTmpRounding.ROUND_C_DEFAULT,
                 saturation=HFloatTmpSaturation.SATURATE_C_DEFAULT,
                 name:Optional[str]=None,
                 const=False,):
        HdlType.__init__(self, const=const)
        self.name = name
        self.int_bit_length = int_bit_length
        self.frac_bit_length = frac_bit_length
        self.signed = signed
        self.rounding = rounding
        self.saturation = saturation
        self._all_mask = mask(self.bit_length())

        exponentOrIntWidth = self.int_bit_length
        mantissaOrFracWidth = self.frac_bit_length
        isInQFormat = True
        supportSubnormal = False
        hasSign = bool(self.signed)
        hasIsNaN = False
        hasIsInf = False
        hasIs1 = False
        hasIs0 = False

        self._cfg = HFloatTmpConfig(
            isInQFormat,
            exponentOrIntWidth,
            mantissaOrFracWidth,
            supportSubnormal,
            hasSign,
            hasIsNaN,
            hasIsInf,
            hasIs1,
            hasIs0,
            rounding,
            saturation
        )

    def _createMutated(self,
                      int_bit_length: int=NOT_SPECIFIED,
                      frac_bit_length: int=NOT_SPECIFIED,
                      signed:bool=NOT_SPECIFIED,
                      rounding:HFloatTmpRounding=NOT_SPECIFIED,
                      saturation:HFloatTmpSaturation=NOT_SPECIFIED,
                      name:str=NOT_SPECIFIED,
                      const:bool=NOT_SPECIFIED
                      ):
        if int_bit_length is NOT_SPECIFIED:
            int_bit_length = self.int_bit_length
        if frac_bit_length is NOT_SPECIFIED:
            frac_bit_length = self.frac_bit_length
        if signed is NOT_SPECIFIED:
            signed = self.signed
        if rounding is NOT_SPECIFIED:
            rounding = self.rounding
        if saturation is NOT_SPECIFIED:
            saturation = self.saturation
        if name is NOT_SPECIFIED:
            name = self.name
        if const is NOT_SPECIFIED:
            const = self.const

        return self.__class__(int_bit_length, frac_bit_length,
                              signed=signed,
                              rounding=rounding,
                              saturation=saturation,
                              name=name,
                              const=const)

    def getHFloatTmpConfig(self) -> HFloatTmpConfig:
        return self._cfg

    @classmethod
    def fromHFloatTmpConfig(cls, cfg: HFloatTmpConfig) -> Self:
        assert cfg.isInQFormat, cfg
        res = cls(cfg.exponentOrIntWidth, cfg.mantissaOrFracWidth, cfg.hasSign, cfg.rounding, cfg.saturation)
        res._cfg = cfg
        return res

    @override
    def all_mask(self) -> int:
        return self._all_mask

    @override
    def bit_length(self) -> int:
        return self.int_bit_length + self.frac_bit_length

    def getMinValue(self):
        if self._cfg.hasIsInf or self._cfg.hasIs0:
            raise NotImplementedError()
        scale = 2 ** self.frac_bit_length
        if self.signed:
            return self.from_py((-mask(self.int_bit_length + self.frac_bit_length - 1) - 1) / scale)
        else:
            return self.from_py(0)

    def getMaxValue(self):
        if self._cfg.hasIsInf or self._cfg.hasIs0:
            raise NotImplementedError()
        scale = 2 ** self.frac_bit_length
        numWidth = self.int_bit_length + self.frac_bit_length
        if self.signed:
            return self.from_py(mask(numWidth - 1) / scale)
        else:
            return self.from_py(mask(numWidth) / scale)

    def _as_hdl(self, to_Hdl: "ToHdlAst", declaration:bool):
        if isinstance(to_Hdl, ToHdlAstHwt) and to_Hdl.debug:
            raise NotImplementedError()
        else:
            return to_Hdl.as_hdl_HdlType(HBits(self.bit_length()), declaration)

    @override
    def __eq__(self, other:object) -> bool:
        return (
            isinstance(other, self.__class__) and
            self._cfg == other._cfg
        )

    @override
    def __hash__(self) -> int:
        return hash((
            self.__class__,
            self._cfg.__hash__(),
        ))

    @internal
    @override
    @classmethod
    def get_auto_cast_HConst_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_auto_cast
        return HFixedPointQ_auto_cast

    @internal
    @override
    @classmethod
    def get_auto_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_auto_cast
        return HFixedPointQ_auto_cast

    @internal
    @override
    @classmethod
    def get_reverse_auto_cast_HConst_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reverse_auto_cast_HConst
        return HFixedPointQ_reverse_auto_cast_HConst

    @internal
    @override
    @classmethod
    def get_reverse_auto_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reverse_auto_cast_RtlSignal
        return HFixedPointQ_reverse_auto_cast_RtlSignal

    @internal
    @override
    @classmethod
    def get_reinterpret_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reinterpret_cast_RtlSignal
        return HFixedPointQ_reinterpret_cast_RtlSignal

    @internal
    @override
    @classmethod
    def get_reverse_reinterpret_cast_RtlSignal_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reverse_reinterpret_cast_RtlSignal
        return HFixedPointQ_reverse_reinterpret_cast_RtlSignal

    @internal
    @override
    @classmethod
    def get_reinterpret_cast_HConst_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reinterpret_cast_HConst
        return HFixedPointQ_reinterpret_cast_HConst

    @internal
    @override
    @classmethod
    def get_reverse_reinterpret_cast_HConst_fn(cls):
        from tests.math.fixp.fixpCast import HFixedPointQ_reverse_reinterpret_cast_HConst
        return HFixedPointQ_reverse_reinterpret_cast_HConst

    @internal
    @override
    @classmethod
    def getConstCls(cls):
        try:
            return cls._constCls
        except AttributeError:
            from tests.math.fixp.fixpConst import HFixedPointQConst
            cls._constCls = HFixedPointQConst
            return cls._constCls

    @internal
    @override
    @classmethod
    def getRtlSignalCls(cls):
        try:
            return cls._rtlSignalCls
        except AttributeError:
            from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
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

        if self.rounding != HFloatTmpRounding.ROUND_C_DEFAULT:
            constr.append(self.rounding.name)
        if self.saturation != HFloatTmpSaturation.SATURATE_C_DEFAULT:
            constr.append(self.saturation.name)

        return "%s<%s, %s>" % (getIndent(indent),
                               self.__class__.__name__,
                               ", ".join(constr))
