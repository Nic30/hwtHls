from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.ssa.context import SsaContext


class SsaUser():
    pass


class SsaValue():
    """
    :ivar origin: an object which was this generated from
    """
    _GEN_NAME_PREFIX = "%"

    def __init__(self, ctx: SsaContext, dtype: HdlType, name:str, origin):
        self.origin = origin
        if name is None:
            name = ctx.genName(self)
            if isinstance(origin, RtlSignalBase) and not origin.hasGenericName:
                name = f"{name}({origin.name:s})"
            
        self._name = name
        self._dtype = dtype
        self.users: UniqList[SsaUser] = UniqList()
