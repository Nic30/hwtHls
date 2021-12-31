from collections import defaultdict
from typing import List, Dict, Set

from hdlConvertorAst.hdlAst import HdlStmWhile, HdlValueId, HdlStmIf
from hdlConvertorAst.hdlAst._bases import iHdlStatement
from hdlConvertorAst.hdlAst._statements import HdlStmBreak, HdlStmContinue
from hdlConvertorAst.translate.verilog_to_basic_hdl_sim_model.utils import hdl_call, \
    hdl_getattr
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.serializer.hwt import HwtDebugSerializer, ToHdlAstDebugHwt
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hlsStreamProc.statements import HlsStreamProcWhile, \
    HlsStreamProcCodeBlock, HlsStreamProcWrite, HlsStreamProcIf, \
    HlsStreamProcBreak, HlsStreamProcContinue
from hwtHls.ssa.basicBlock import SsaBasicBlock


class ToHdlAstHlsStreamProcDebugCode(ToHdlAstDebugHwt):

    def copy_hdl_doc(self, src, dst):
        if src.__doc__ != src.__class__.__doc__:
            dst.doc = " " + src.__doc__

    def as_hdl_statements(self, stm_list) -> iHdlStatement:
        res = ToHdlAstDebugHwt.as_hdl_statements(self, stm_list)
        if res is not None and hasattr(res, "in_preproc"):
            res.in_preproc = True
        return res
        
    def as_hdl_HlsStreamProcCodeBlock(self, o: HlsStreamProcCodeBlock):
        return self.as_hdl_HdlStmCodeBlockContainer(o)

    def as_hdl_HlsStreamProcIf(self, o: HlsStreamProcIf):
        return self.as_hdl_If(o)

    def as_hdl_HlsStreamProcWhile(self, o: HlsStreamProcWhile):
        res = HdlStmWhile()
        self.copy_hdl_doc(o, res)
        res.cond = self.as_hdl(o.cond)
        res.in_preproc = True
        res.body = self.as_hdl_statements((o.body))
        if isinstance(res.body, HdlStatement):
            res.body.in_preproc = True
        return res

    def as_hdl_HlsStreamProcBreak(self, o: HlsStreamProcBreak):
        res = HdlStmBreak()
        res.in_preproc = True
        return res

    def as_hdl_HlsStreamProcContinue(self, o: HlsStreamProcContinue):
        res = HdlStmContinue()
        res.in_preproc = True
        return res

    def as_hdl_If(self, o: IfContainer) -> HdlStmIf:
        res = ToHdlAstDebugHwt.as_hdl_If(self, o)
        self.copy_hdl_doc(o, res)
        res.in_preproc = True
        return res

    def as_hdl_HlsStreamProcWrite(self, o: HlsStreamProcWrite):
        return hdl_call(
            hdl_getattr(HdlValueId(getSignalName(o.dst)), "write"),
            [self.as_hdl(o._orig_src), ]
        )

    def as_hdl_HdlAssignmentContainer(self, o:HdlAssignmentContainer):
        res = ToHdlAstDebugHwt.as_hdl_HdlAssignmentContainer(self, o)
        res.in_preproc = True
        self.copy_hdl_doc(o, res)
        return res


class CopyBasicBlockLabelsToCode():

    def _visit(self, bb: SsaBasicBlock, doc: Dict[object, List[str]], seen: Set[SsaBasicBlock]):
        seen.add(bb)
        for o in bb.origins:
            doc[o].append(bb.label)
        for (_, t) in bb.successors.targets:
            if t not in seen:
                self._visit(t, doc, seen)

    def visit(self, bb: SsaBasicBlock):
        """
        First we need to construct reverse mapping of SSA basic blocks to code objects.
        Then we can resolve the labels for code objects with references on basic blocks.
        """
        seen = set()
        doc = defaultdict(list)
        self._visit(bb, doc, seen)
        for o, labels in doc.items():
            o.__doc__ = ", ".join(labels)


class HlsStreamProcDebugCodeSerializer(HwtDebugSerializer):
    """
    Serializer which translates HwtHls ASTs back to code text for debugging purposes.
    """
    TO_HDL_AST = ToHdlAstHlsStreamProcDebugCode
