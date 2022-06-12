from typing import Set

from hdlConvertorAst.to.hdlUtils import Indent, \
    AutoIndentingStream
from hwt.hdl.value import HValue
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcRead, \
    HlsStreamProcWrite
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaToLl():
    """
    Convert SSA to LLVM IR text for debugging and visualization.

    Output example:
    .. code-block::llvm

        define dso_local i32 @main() #0 {
        entry:
          br label %while.cond

        while.cond:                                       ; preds = %while.body, %entry
          %i.0 = phi i32 [ 0, %entry ], [ %inc, %while.body ]
          br label %while.body

        while.body:                                       ; preds = %while.cond
          %inc = add nsw i32 %i.0, 1
          br label %while.cond
        }
    """

    def __init__(self, output:AutoIndentingStream):
        self.output = output
        self.seenBlocks: Set[SsaBasicBlock] = set()

    def construct(self, begin: SsaBasicBlock):
        w = self.output.write
        w("define dso_local i32 @main() #0 {\n")
        self._node_from_SsaBasicBlock(begin)
        w("}")

    def _node_from_SsaBasicBlock(self, bb: SsaBasicBlock):
        if bb in self.seenBlocks:
            return
        self.seenBlocks.add(bb)

        w = self.output.write
        # construct new node
        w(f"{bb.label:s}:\n")
        with Indent(self.output):
            for phi in bb.phis:
                phi: SsaPhi
                ops = ", ".join(
                    f"[{self._escape(o._name if isinstance(o, SsaInstr) else repr(o))}, {b.label:s}]"
                    for (o, b) in phi.operands
                )
                w(f"{self._escape(phi._name)} = phi {self._escape(repr(phi._dtype))} {ops:s}\n")

            for stm in bb.body:
                if isinstance(stm, HlsStreamProcRead):
                    w(stm._name)
                    w(" = call ")
                    w(self._escape(repr(stm._dtype)))
                    w(" @hls.read(")
                    w(getSignalName(stm._src))
                    w(")\n")
                elif isinstance(stm, HlsStreamProcWrite):
                    w("void call ")
                    w(self._escape(repr(stm._dtype)))
                    w(" @hls.write(")
                    if isinstance(stm._orig_src, HValue):
                        w(repr(stm._orig_src))
                    else:
                        w(getSignalName(stm._orig_src))
                    w(")\n")
                else:
                    w(self._escape(repr(stm)))
                    w("\n")
            if bb.successors.targets:
                w("br ")
            for cond, dst_bb in bb.successors.targets:
                cond_str = "" if cond is None else self._escape(cond._name)
                w(f"[label %{dst_bb.label:s} {cond_str:s}]")
                w("\n")

        for (_, dst_bb) in bb.successors.targets:
            self._node_from_SsaBasicBlock(dst_bb)

    @staticmethod
    def _escape(s: str) -> str:
        return s


class SsaPassDumpToLl():

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsStreamProc", to_ssa: "HlsAstToSsa"):
        output, doClose = self.outStreamGetter(to_ssa.label) 
        output = AutoIndentingStream(output, "  ")
        try:
            if isinstance(to_ssa.start, SsaBasicBlock):
                toLl = SsaToLl(output)
                toLl.construct(to_ssa.start)
            elif isinstance(to_ssa.start, ToLlvmIrTranslator):
                toLlvmIr: ToLlvmIrTranslator = to_ssa.start
                main = toLlvmIr.llvm.main
                assert main is not None
                output.write(str(main))
            else:
                raise NotImplementedError(to_ssa.start)
        finally:
            if doClose:
                output.close()
