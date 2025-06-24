"""
OpenGL coordinates, (0, 0) stands at the center,
(-1, 1) defines the top-left, (1, 1) marks the top-right,
(-1, -1) designates the bottom-left, and
(1, -1) signifies the bottom-right

fragCoord.xy is in rectangle (0, 0), (width, height) with (0,0) in bottom left corner
"""
# [todo] inherit from HlsVarContainer/HwIo, add some method to initialize members and update them on store
# [todo] define Swizzling accessors https://www.khronos.org/opengl/wiki/Data_Type_(GLSL)#Swizzling

from dataclasses import dataclass
from dis import Instruction
import operator
from typing import Self

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.mainBases import RtlSignalBase, HwIOBase
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.fromPython import PyBytecodeToSsa
from hwtHls.frontend.instructions import NULL
from hwtHls.frontend.pyBytecodeUtils import ObjectWithHlsStoreOverride
from hwtHls.llvm.llvmIr import BasicBlock
from tests.math.hFloatTmp.hFloatTmpOps import sin, cos, log, log2, log10

_VEC4_PROP_NAMES = ("x", "y", "z", "w")


@dataclass
class vec2(ObjectWithHlsStoreOverride):
    x: float
    y: float

    def __init__(self, *args):
        if len(args) == 2:
            self.x, self.y = args
        else:
            assert len(args) == 1, "expects 2 items or 1 sequence with 2 items or 1 scalar"
            a = args[0]
            if isinstance(a, float) or isinstance(a, (HConst, RtlSignalBase)) and a._dtype.isScalar():
                self.x, self.y = (a, a)
            else:
                self.x, self.y = a

    def hlsInheritName(self, newLocalName: str):
        # apply name prefix for better orientation in generated code
        for v in self:
            if isinstance(v, RtlSignalBase):
                v._name = f"{newLocalName:s}.{v._name:s}"
                v._hasGenericName = False

        self.hlsInheritName = None

    @override
    def hlsStoreOverride(self, toSsa: "PyBytecodeToSsa", curBlock:BasicBlock, newValue) -> BasicBlock:
        assert type(self) == type(newValue), (self.__class__, newValue.__class__)
        for v, vSrc in zip(self, newValue):
            curBlock = toSsa._storeToHwSignal(curBlock, v, vSrc)

        return curBlock

    def hlsOverrideInitializeStorageCell(self, toSsa:"PyBytecodeToSsa", localVarName:str) -> Self:
        if len(self) <= 4:
            makeVar = toSsa.hls.var
            return self.__class__(
                *(makeVar(name, v._dtype) if isinstance(v, (RtlSignalBase, HwIOBase, HConst)) else v
                 for v, name in zip(self, ("x", "y", "z", "w")))
            )
        else:
            raise NotImplementedError(self)

    @classmethod
    def hlsCallOverride(cls, toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, _self, fn, args, kwargs):
        """
        override constructor in hls to wrap members in hls variables
        """
        assert _self is NULL, (_self, "This is expected to be called only if new instance is created")
        self = cls(*args, **kwargs)

        if len(self) <= 4:
            makeVar = toSsa.hls.var
            for v, name in zip(self, ("x", "y", "z", "w")):
                if isinstance(v, (RtlSignalBase, HConst)):
                    vAsVar = makeVar(name, v._dtype)
                    toSsa._storeToHwSignal(curBlock, vAsVar, v)
                    setattr(self, name, vAsVar)
            return self
        else:
            raise NotImplementedError()

    @classmethod
    def getHType(cls, elementTy: HdlType):
        return HStruct(
            (elementTy, "x"),
            (elementTy, "y"),
        )

    def _unOp(self, fn):
        return vec2(fn(self.x), fn(self.y))

    def _binOp(self, other, fn):
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return vec2(fn(self.x, other), fn(self.y, other))
        else:
            return vec2(fn(self.x, other.x), fn(self.y, other.y))

    def _rbinOp(self, other, fn):
        """
        reverse version of _binOp(), self is RHS and other is LHS
        """
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return vec2(fn(other, self.x), fn(other, self.y))
        else:
            return vec2(fn(other.x, self.x), fn(other.y, self.y))

    def __getitem__(self, key):
        if key == 0:
            return self.x
        elif key == 1:
            return self.y
        else:
            raise IndexError(key)

    def __neg__(self):
        return self.__class__(-n for n in self)

    def __add__(self, other):
        return self._binOp(other, operator.add)

    def __radd__(self, other):
        return self._rbinOp(other, operator.add)

    def __sub__(self, other):
        return self._binOp(other, operator.sub)

    def __rsub__(self, other):
        return self._rbinOp(other, operator.sub)

    def __mul__(self, other):
        if isinstance(other, mat2):
            v = self
            m = other
            # vec2 v = vec2(10., 20.);
            # mat2 m = mat2(1., 2.,  3., 4.);
            # vec2 w = v * m; // = vec2(1. * 10. + 2. * 20.,
            #                           3. * 10. + 4. * 20.)
            return vec2(
                m[0][0] * v.x + m[0][1] * v.y,
                m[0][1] * v.x + m[1][1] * v.y)
        return self._binOp(other, operator.mul)

    def __rmul__(self, other):
        return self._rbinOp(other, operator.mul)

    def __truediv__(self, other):
        return self._binOp(other, operator.truediv)

    def __rtruediv__(self, other):
        return self._rbinOp(other, operator.truediv)

    def __floordiv__(self, other):
        return self._binOp(other, operator.floordiv)

    def __rfloordiv__(self, other):
        return self._rbinOp(other, operator.floordiv)

    def __mod__(self, other):
        return self._binOp(other, operator.mod)

    def __rmod__(self, other):
        return self._rbinOp(other, operator.mod)

    def sin(self):
        return self._unOp(sin)

    def cos(self):
        return self._unOp(cos)

    def log(self):
        return self._unOp(log)

    def log2(self):
        return self._unOp(log2)

    def log10(self):
        return self._unOp(log10)

    def __len__(self):
        return 2

    def __iter__(self):
        return iter((self.x, self.y))


@dataclass
class vec3(vec2):
    z: float

    def __init__(self, *args):
        if len(args) == 3:
            self.x, self.y, self.z = args
        else:
            assert len(args) == 1, "expects 3 items or 1 sequence with 3 items or 1 scalar"
            a = args[0]
            if isinstance(a, float) or isinstance(a, (HConst, RtlSignalBase)) and a._dtype.isScalar():
                self.x, self.y, self.z = (a, a, a)
            else:
                self.x, self.y, self.z = a

    @classmethod
    def getHType(cls, elementTy: HdlType):
        return HStruct(
            (elementTy, "x"),
            (elementTy, "y"),
            (elementTy, "z"),
        )

    def _unOp(self, fn):
        return vec2(fn(self.x), fn(self.y), fn(self.z))

    def _binOp(self, other, fn):
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return self.__class__(fn(self.x, other), fn(self.y, other), fn(self.z, other))
        else:
            return self.__class__(fn(self.x, other.x), fn(self.y, other.y), fn(self.z, other.z))

    def _rbinOp(self, other, fn):
        """
        reverse version of _binOp(), self is RHS and other is LHS
        """
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return self.__class__(fn(other, self.x), fn(other, other.y), fn(other, other.z))
        else:
            return self.__class__(fn(other.x, self.x), fn(other.y, self.y), fn(other.z, self.z))

    def __getitem__(self, key):
        if key == 0:
            return self.x
        elif key == 1:
            return self.y
        elif key == 2:
            return self.z
        else:
            raise IndexError(key)

    def __len__(self):
        return 3

    def __iter__(self):
        return iter((self.x, self.y, self.z))


@dataclass
class vec4(vec3):
    w: float

    def __init__(self, *args):
        if len(args) == 4:
            self.x, self.y, self.z, self.w = args
        else:
            assert len(args) == 1, "expects 4 items or 1 sequence with 4 items or 1 scalar"
            a = args[0]
            if isinstance(a, float) or isinstance(a, (HConst, RtlSignalBase)) and a._dtype.isScalar():
                self.x, self.y, self.z, self.w = (a, a, a, a)
            else:
                self.x, self.y, self.z, self.w = a

    @classmethod
    def getHType(cls, elementTy: HdlType):
        return HStruct(
            (elementTy, "x"),
            (elementTy, "y"),
            (elementTy, "z"),
            (elementTy, "w"),
        )

    def _unOp(self, fn):
        return vec2(fn(self.x), fn(self.y), fn(self.z), fn(self.w))

    def _binOp(self, other, fn):
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return self.__class__(fn(self.x, other), fn(self.y, other), fn(self.z, other), fn(self.w, other))
        else:
            return self.__class__(fn(self.x, other.x), fn(self.y, other.y), fn(self.z, other.z), fn(self.w, other.w))

    def _rbinOp(self, other, fn):
        """
        reverse version of _binOp(), self is RHS and other is LHS
        """
        if isinstance(other, (float, int, HConst)) or (isinstance(other, RtlSignalBase) and other._dtype.isScalar()):
            return self.__class__(fn(other, self.x), fn(other, other.y), fn(other, other.z), fn(other, other.w))
        else:
            return self.__class__(fn(other.x, self.x), fn(other.y, self.y), fn(other.z, self.z), fn(other.w, self.w))

    def __getitem__(self, key):
        if key == 0:
            return self.x
        elif key == 1:
            return self.y
        elif key == 2:
            return self.z
        elif key == 3:
            return self.w
        else:
            raise IndexError(key)

    def __len__(self):
        return 4

    def __iter__(self):
        return iter((self.x, self.y, self.z, self.w))


class mat2():

    def __init__(self, *args):
        """
        mat2(
          float, float,   // first column
          float, float);  // second column

        mat2(x:float) = mat2(x, 0,
                             0, x)
        """
        if len(args) == 4:
            self.__data = [vec2(args[0], args[1]),
                           vec2(args[2], args[3]),
                           ]
        else:
            assert len(args) == 1, "expects 4 items or 1 sequence with 4 items or 1 scalar"
            a = args[0]
            if isinstance(a, float) or isinstance(a, (HConst, RtlSignalBase)) and a._dtype.isScalar():
                zero = 0.
                if not isinstance(a, float):
                    zero = a._dtype.from_py(zero)
                self.__data = [
                    vec2(a, zero),
                    vec2(zero, a),
                ]
            else:
                args = a
                self.__data = [vec2(args[0], args[1]),
                               vec2(args[2], args[3]),
                              ]

    def __getitem__(self, key):
        return self.__data[key]
