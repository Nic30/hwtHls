from typing import List, Tuple, Union, Optional

from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HdlType_to_HwIO
from hwt.hwIOs.hwIOStruct import HwIOStructVld
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.setList import SetList
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_without_registration, \
    HwIO_getName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import AnyStm, HlsAstToSsa
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statements import HlsStmCodeBlock
from hwtHls.thread import HlsThread
from ipCorePackager.constants import DIRECTION
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints


class HlsThreadFromAst(HlsThread):

    def __init__(self, hls: "HlsScope", code: List[AnyStm], name: str,
                 resourceConstraints: Optional[SchedulingResourceConstraints]=None):
        super(HlsThreadFromAst, self).__init__(hls, resourceConstraints)
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
        _code._sensitivity = SetList()
        _code.statements.extend(flatten(code))
        return _code

    def compileToSsa(self):
        _code = self._formatCode(self.code)
        platform = self.hls.parentHwModule._target_platform
        namePrefix = self.hls.namePrefix
        if len(self.hls._threads) > 1:
            i = self.hls._threads.index(self)
            namePrefix = f"{self.hls.namePrefix}t{i:d}_"
        toSsa = HlsAstToSsa(self.hls.ssaCtx, self.getLabel(), namePrefix, _code, platform.getPassManagerDebugLogFile())
        toSsa._onAllPredecsKnown(toSsa.start)
        toSsa.visit_top_CodeBlock(_code)
        toSsa.finalize()
        self.toSsa = toSsa


class HlsThreadForSharedVar(HlsThreadFromAst):

    def __init__(self, hls: "HlsScope", var: Union[RtlSignal, HwIO]):
        super(HlsThreadForSharedVar, self).__init__(hls, None, f"sharedVarThread_{HwIO_getName(var)}")
        self.var = var
        self._exports: List[Tuple[Union[RtlSignal, HwIO], DIRECTION.IN]] = []

    def getReadPort(self):
        p = HdlType_to_HwIO().apply(self.var._dtype)
        HwIO_without_registration(self.hls.parentHwModule, p,
                                        f"{HwIO_getName(self._parent.parentHwModule, self.var):s}_{len(self._exports):d}")
        self._exports.append((p, DIRECTION.OUT))
        return p

    def getWritePort(self):
        p = HwIOStructVld()
        p.T = self.var._dtype
        HwIO_without_registration(self.hls.parentHwModule, p,
                                       f"{HwIO_getName(self._parent.parentHwModule, self.var):s}_{len(self._exports):d}")
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

