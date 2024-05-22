from hwt.doc_markers import internal
from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.typingFuture import override


class _HVoidOrdering(HdlType):
    """
    :note: use HVoidOrdering directly
    """

    def bit_length(self):
        return 0

    @internal
    @override
    @classmethod
    def getConstCls(cls):
        try:
            return cls._constCls
        except AttributeError:
            cls._constCls = _HVoidConst
            return cls._constCls


class _HVoidConst(HConst):

    @classmethod
    def from_py(cls, typeObj, val, vld_mask=None):
        assert val is None, ("Only allowed value is None because void value does not contain any data", val)
        return cls(typeObj, None, vld_mask=None)

    def _concat(self, other: "_HVoidConst"):
        assert isinstance(self, HConst) and self.__class__ == other.__class__, (self, other, self.__class__, other.__class__)
        assert self._dtype == other._dtyp
        assert self

    def __repr__(self):
        return f"<void>"


class _HVoidData(_HVoidOrdering):
    """
    :note: use HDataVoid directly
    """
    pass


class _HVoidExternData(_HVoidOrdering):
    """
    :note: use HVoidExternData directly
    """
    pass

"""
:var ~.HVoidOrdering: A type used for connections between HlsNetNode instances to keep its ordering during scheduling.
    (similar to glue type in LLVM)
:var ~.HVoidDataT: Same as HVoidOrdering but in addition it means that there is/was some data dependency.
:var ~.HVoidExternData: Same as a HVoidOrdering but in addition it means that there is an external data connection
    on outside of this component which asserts that connected two nodes are asserted to have ordering by externally connected circuit.
"""
HVoidOrdering = _HVoidOrdering()
HVoidData = _HVoidData()
HVoidExternData = _HVoidExternData()


def HdlType_isNonData(t: HdlType):
    return t is HVoidOrdering or t is HVoidExternData


def HdlType_isVoid(t: HdlType):
    return t is HVoidOrdering or t is HVoidData or t is HVoidExternData
