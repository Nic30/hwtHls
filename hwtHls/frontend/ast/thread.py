from typing import List, Tuple, Union

from hwt.interfaces.structIntf import HdlType_to_Interface
from hwt.interfaces.vldSyncedStructIntf import VldSyncedStructIntf
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration, \
    getInterfaceName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import AnyStm, HlsAstToSsa
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statements import HlsStmCodeBlock
from hwtHls.thread import HlsThread
from ipCorePackager.constants import DIRECTION


class HlsThreadFromAst(HlsThread):

    def __init__(self, hls: "HlsScope", code: List[AnyStm], name: str):
        super(HlsThreadFromAst, self).__init__(hls)
        self.code = code
        self.name = name

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.name}"

    def _formatCode(self, code: List[AnyStm]) -> HlsStmCodeBlock:
        """
        Normalize an input code.
        """
        _code = HlsStmCodeBlock(self)
        _code.name = self.name
        _code._sensitivity = UniqList()
        _code.statements.extend(flatten(code))
        return _code

    def compileToSsa(self):
        _code = self._formatCode(self.code)
        platform = self.hls.parentUnit._target_platform
        toSsa = HlsAstToSsa(self.hls.ssaCtx, self.getLabel(), _code, platform.getPassManagerDebugLogFile())
        toSsa._onAllPredecsKnown(toSsa.start)
        toSsa.visit_top_CodeBlock(_code)
        toSsa.finalize()
        self.toSsa = toSsa


class HlsThreadForSharedVar(HlsThreadFromAst):

    def __init__(self, hls: "HlsScope", var: Union[RtlSignal, Interface]):
        super(HlsThreadForSharedVar, self).__init__(hls, None, f"sharedVarThread_{getInterfaceName(var)}")
        self.var = var
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = []

    def getReadPort(self):
        p = HdlType_to_Interface().apply(self.var._dtype)
        Interface_without_registration(self.hls.parentUnit, p,
                                        f"{getInterfaceName(self._parent.parentUnit, self.var):s}_{len(self._exports):d}")
        self._exports.append((p, DIRECTION.OUT))
        return p

    def getWritePort(self):
        p = VldSyncedStructIntf()
        p.T = self.var._dtype
        Interface_without_registration(self.hls.parentUnit, p,
                                       f"{getInterfaceName(self._parent.parentUnit, self.var):s}_{len(self._exports):d}")
        self._exports.append((p, DIRECTION.IN))
        return p

    def compileToSsa(self):
        hls = self.hls
        v = self.var
        access = []
        for i, dir_ in self._exports:
            if dir_ == DIRECTION.OUT:
                res = (hls.write(v, i),)
            elif dir_ == DIRECTION.IN:
                res = v(hls.read(i).data)
            else:
                raise NotImplementedError(dir_)
            access.extend(res)
        astBuilder = HlsAstBuilder(hls)
        self.code = astBuilder.While(True,
            *access,
        )
        HlsThreadFromAst.compileToSsa(self)

