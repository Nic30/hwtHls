from hdlConvertorAst.to.hdlUtils import AutoIndentingStream, Indent
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline


class SsaPassDumpPipelines():

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa"):
        to_hw = SsaSegmentToHwPipeline(to_ssa.start, to_ssa.original_code_for_debug)
        to_hw.extract_pipeline()
        out, doClose = self.outStreamGetter(to_ssa.start.label)
        out = AutoIndentingStream(out, "  ")

        try:
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
        finally:
            if doClose:
                out.close()
