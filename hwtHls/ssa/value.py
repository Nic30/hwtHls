from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.ssa.context import SsaContext


class SsaUser():
    pass


class SsaValue():
    """
    :ivar origin: an object which was this generated from
    """
    GEN_NAME_PREFIX = "%"

    def __init__(self, ctx: SsaContext, dtype: HdlType, name:str, origin):
        self.origin = origin
        if name is None:
            name = ctx.genName(self)
        self._name = name
        self._dtype = dtype
        self.users: UniqList[SsaUser] = UniqList()
