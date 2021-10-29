#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union, List

from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import Handshaked
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.ssa.analysis.consystencyCheck import SsaConsystencyCheck
from hwtHls.hlsStreamProc.ssa.analysis.liveness import ssa_liveness_edge_variables
from hwtHls.hlsStreamProc.ssa.transformation.expandControlSelfLoops import ExpandControlSelfloops
from hwtHls.hlsStreamProc.ssa.transformation.removeTrivialBlocks import RemoveTrivialBlocks
from hwtHls.hlsStreamProc.ssa.translation.astToSsa import AstToSsa, AnyStm
from hwtHls.hlsStreamProc.ssa.translation.toGraphwiz import SsaToGraphwiz
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.pipelineExtractor import PipelineExtractor
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, \
    HlsStreamProcWrite, HlsStreamProcWhile, HlsStreamProcCodeBlock
from hwtLib.amba.axis import AxiStream


class HlsStreamProc():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> SSA
    * packet level ops -> word ops
    * SSA optimizations (trivial block rm)
    * pipeline extraction
    * scheduling and materialization of pipelines
    * materialization of inter pipeline synchronization
    """

    def __init__(self, parent: Unit):
        self.parent = parent
        self.freq = parent.clk.FREQ
        self.ctx = RtlNetlist()

    def var(self, name:str, dtype:HdlType):
        return self.ctx.sig(name, dtype)

    def read(self,
             src: Union[AxiStream, Handshaked],
             type_or_size: Union[HdlType, RtlSignal, int]=NOT_SPECIFIED,
             buffer_size: int=0):
        """
        :param buffer_size: size of buffer for read data in bits
        """
        return HlsStreamProcRead(self, src, type_or_size, buffer_size)

    def write(self,
              src:Union[HlsStreamProcRead, Handshaked, AxiStream, bytes, HValue],
              dst:Union[AxiStream, Handshaked]):
        return HlsStreamProcWrite(self, src, dst)

    def While(self, cond: Union[RtlSignal, bool], *body: AnyStm):
        return HlsStreamProcWhile(self, cond, body)

    def _format_code(self, code: List[AnyStm], label:str="hls_top") -> HlsStreamProcCodeBlock:
        _code = HlsStreamProcCodeBlock(self)
        _code.name = label
        _code._sensitivity = UniqList()
        _code.statements.extend(flatten(code))
        return _code

    def thread(self, *code: AnyStm):
        _code = self._format_code(code)

        to_ssa = AstToSsa()
        to_ssa.visit_top_CodeBlock(_code)
        ssa = to_ssa.start
        # ssa = RemoveTrivialBlocks().visit(ssa)
        # ssa = ExpandControlSelfloops(to_ssa._createHlsTmpVariable).visit_SsaBasicBlock(ssa)
        SsaConsystencyCheck().visit(ssa)
        pe = PipelineExtractor()
        all_blocks = []
        for comp in pe.collect_pipelines(ssa):
            all_blocks.extend(comp)

        edge_var_live = ssa_liveness_edge_variables(ssa)
        #print("backward_edges", [(e[0].label, e[1].label) for e in pe.backward_edges])
        #print("pipeline", [n.label for n in all_blocks])

        # [debug]
        to_graphwiz = SsaToGraphwiz("top")
        with open("top.dot", "w") as f:
            to_graphwiz.construct(ssa, _code, [all_blocks, ], edge_var_live)
            f.write(to_graphwiz.dumps())

        SsaSegmentToHwPipeline(self.parent, self.freq)\
            ._construct_pipeline(ssa, all_blocks, pe.backward_edges, edge_var_live)

        # io = {}
        # interpret = SsaInterpret(io, ssa)
        # for _ in range(40):
        #     next(interpret)
        # print(io)

        # raise NotImplementedError("scheduling of ssa, allocation of circuit primitives")

