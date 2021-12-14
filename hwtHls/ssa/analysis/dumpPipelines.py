from io import StringIO
import sys

from hdlConvertorAst.to.hdlUtils import AutoIndentingStream, Indent
from hwtHls.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline


class SsaPassDumpPipelines():

    def __init__(self, output:StringIO=sys.stdout, close=False):
        self.close = close
        self.output = AutoIndentingStream(output, "  ")

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa"):
        to_hw = SsaSegmentToHwPipeline(to_ssa.start, to_ssa.original_code_for_debug)
        to_hw.extract_pipeline()
        out = self.output
        out.write("########## pipeline ##########\n")
        with Indent(out):
            for b in to_hw.pipeline:
                m = to_hw.blockMeta[b]
                out.write(b.label)
                out.write(" ")
                out.write(repr(m))
                out.write("\n")

        out.write("########## backward_edges ##########\n")
        with Indent(out):
            for src, dst in sorted(to_hw.backward_edges, key=lambda x: (x[0].label, x[1].label)):
                out.write(f"{src.label:s} -> {dst.label:s}\n")

        if self.close:
            self.output.close()
