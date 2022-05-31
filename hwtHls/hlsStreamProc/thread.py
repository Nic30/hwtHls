from typing import List, Optional, Tuple, Union

from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.std import Signal, VldSynced
from hwt.interfaces.structIntf import HdlType_to_Interface
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration, \
    getSignalName
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.statements import HlsStreamProcCodeBlock
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.ssa.translation.fromAst.astToSsa import AnyStm, AstToSsa
from ipCorePackager.constants import DIRECTION


class HlsStreamProcThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsStreamProc"):
        self.hls = hls
        self.toSsa: Optional[AstToSsa] = None
        self.toHw: Optional[HlsNetlistCtx] = None

    def compileToSsa(self):
        raise NotImplementedError("Must be implemented in child class", self)


class HlsStreamProcThreadFromAst(HlsStreamProcThread):

    def __init__(self, hls: "HlsStreamProc", code: List[AnyStm], name: str):
        super(HlsStreamProcThreadFromAst, self).__init__(hls)
        self.code = code
        self.name = name
    
    def _formatCode(self, code: List[AnyStm]) -> HlsStreamProcCodeBlock:
        """
        Normalize an input code.
        """
        _code = HlsStreamProcCodeBlock(self)
        _code.name = self.name
        _code._sensitivity = UniqList()
        _code.statements.extend(flatten(code))
        return _code

    def compileToSsa(self):
        _code = self._formatCode(self.code)
        toSsa = AstToSsa(self.hls.ssaCtx, self.name, _code)
        toSsa._onAllPredecsKnown(toSsa.start)
        toSsa.visit_top_CodeBlock(_code)
        toSsa.finalize()
        self.toSsa = toSsa  


class VldSyncedStructIntf(VldSynced):

    def _config(self):
        self.T: HdlType = Param(None)
    
    def _declr(self):
        assert self.T is not None
        self._dtype = self.T
        self.vld:Signal = Signal()._m()
        self.data = HdlType_to_Interface().apply(self.T)._m()


class HlsStreamProcSharedVarThread(HlsStreamProcThreadFromAst):

    def __init__(self, hls: "HlsStreamProc", var: Union[RtlSignal, Interface]):
        super(HlsStreamProcSharedVarThread, self).__init__(hls, None, f"managerThread_{getSignalName(var)}")
        self.var = var
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = [] 

    def getReadPort(self):
        p = HdlType_to_Interface().apply(self.var._dtype)
        Interface_without_registration(self.hls.parentUnit, p, f"{getSignalName(self.var):s}_{len(self._exports):d}")
        self._exports.append((p, DIRECTION.OUT))
        return p
    
    def getWritePort(self):
        p = VldSyncedStructIntf()
        p.T = self.var._dtype
        Interface_without_registration(self.hls.parentUnit, p, f"{getSignalName(self.var):s}_{len(self._exports):d}")
        self._exports.append((p, DIRECTION.IN))
        return p

    def compileToSsa(self):
        hls = self.hls
        v = self.var
        access = []
        for i, dir_ in self._exports:
            if dir_ == DIRECTION.OUT:
                res = (hls.write(v, i), )
            elif dir_ == DIRECTION.IN:
                res = v(hls.read(i))
            else:
                raise NotImplementedError(dir_)
            access.extend(res)

        self.code = hls.While(True,
            *access,
        )
        HlsStreamProcThreadFromAst.compileToSsa(self)

