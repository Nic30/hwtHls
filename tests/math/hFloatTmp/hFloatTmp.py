
from hwt.doc_markers import internal
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import Type


class _HFloatTmp(HdlType):
    """
    Temporary float type to represent arbitrary Float and fixed point Q numbers in LLVM.
    
    LLVM does support only some float type configurations and it does not support fixed point numbers in Q format,
    to support any FP type the compilation runs in 2 steps:
    1. every floating point type is represented using double and all IR passes are executed.
    2. every floating point type is replaced with integer (with desired bit width)
       which will be used to as a storage for final floating point values.
       And then code is optimized again compilation continues to MIR. 
    
    :attention: this type is represented by double in LLVM if this type is tmp type
        for larger type constants may suffer from rounding errors. 
    """
    _PRECOMPUTE_CONSTANT_SIGNALS = False

    @override
    def bit_length(self) -> int:
        return 64

    def all_mask(self):
        return (1 << 64) - 1

    @internal
    @classmethod
    def get_auto_cast_HConst_fn(cls):
        from tests.math.hFloatTmp.hFloatTmpCast import castFromHFloatTmp
        return lambda curTy, cur, newTy: castFromHFloatTmp(cur, newTy)

    # @internal
    # @override
    # @classmethod
    # def get_reinterpret_cast_HConst_fn(cls):
    #    from tests.math.hFloatTmpCast import reinterpretBits__HConst
    #    return reinterpretBits__HConst

    @internal
    @classmethod
    def get_auto_cast_RtlSignal_fn(cls):
        from tests.math.hFloatTmp.hFloatTmpCast import castFromHFloatTmp
        return lambda curTy, cur, newTy: castFromHFloatTmp(cur, newTy)

    # @internal
    # @override
    # @classmethod
    # def get_reinterpret_cast_RtlSignal_fn(cls):
    #    from tests.math.hFloatTmpCast import reinterpretBits__RtlSignal
    #    return reinterpretBits__RtlSignal

    @internal
    @override
    @classmethod
    def getConstCls(cls):
        try:
            return cls._constCls
        except AttributeError:
            from tests.math.hFloatTmp.hFloatTmpConst import HFloatTmpConst
            cls._constCls = HFloatTmpConst
            return cls._constCls

    @internal
    @override
    @classmethod
    def getRtlSignalCls(cls):
        try:
            return cls._rtlSignalCls
        except AttributeError:
            from tests.math.hFloatTmp.hFloatTmpRtlSignal import HFloatTmpRtlSignal
            cls._rtlSignalCls = HFloatTmpRtlSignal
            return cls._rtlSignalCls

    def toLlvm(self, toLlvm: "ToLlvmIrTranslator") -> Type:
        return Type.getDoubleTy(toLlvm.ctx)


HFloatTmp = _HFloatTmp()
