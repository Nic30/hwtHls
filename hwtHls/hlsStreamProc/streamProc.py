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
from hwtHls.hlsStreamProc.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.hlsStreamProc.ssa.transformation.expandControlSelfLoops import SsaPassExpandControlSelfloops
from hwtHls.hlsStreamProc.ssa.transformation.removeTrivialBlocks import SsaPassRemoveTrivialBlocks
from hwtHls.hlsStreamProc.ssa.translation.fromAst.astToSsa import AstToSsa, AnyStm
from hwtHls.hlsStreamProc.ssa.translation.toGraphwiz import HlsNetlistPassToDot
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, \
    HlsStreamProcWrite, HlsStreamProcWhile, HlsStreamProcCodeBlock
from hwtHls.netlist.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.toTimeline import HwtHlsNetlistToTimeline, \
    RtlNetlistPassShowTimeline
from hwtHls.netlist.transformations.mergeExplicitSync import HlsnetlistPassMergeExplicitSync
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

    def __init__(self, parent: Unit,
                 ssa_passes=[
                    SsaPassConsystencyCheck(),
                    # SsaPassExpandControlSelfloops()
                 ],
                 hlsnetlist_passes=[
                    HlsNetlistPassToDot("top.dot"),
                    HlsNetlistPassDumpToDot("top_p.dot"),
                    HlsnetlistPassMergeExplicitSync(),
                 ],
                 rtlnetlist_passes=[
                     RtlNetlistPassShowTimeline(),
                 ]):
        self.parent = parent
        self.freq = parent.clk.FREQ
        self.ctx = RtlNetlist()
        self.ssa_passes = ssa_passes
        self.hlsnetlist_passes = hlsnetlist_passes
        self.rtlnetlist_passes = rtlnetlist_passes

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
        for ssa_pass in self.ssa_passes:
            ssa_pass.apply(to_ssa)

        to_hw = SsaSegmentToHwPipeline(self.parent, self.freq, to_ssa.start, _code)
        to_hw.extract_pipeline()

        to_hw.extract_netlist()
        for hlsnetlist_pass in self.hlsnetlist_passes:
            hlsnetlist_pass.apply(to_hw)

        to_hw.construct_rtlnetlist()
        for rtlnetlist_pass in self.rtlnetlist_passes:
            rtlnetlist_pass.apply(to_hw)

        return to_hw

        # [debug]
        # io = {}
        # interpret = SsaInterpret(io, ssa)
        # for _ in range(40):
        #     next(interpret)
        # print(io)

