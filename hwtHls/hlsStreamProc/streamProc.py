#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from typing import Union, List, Optional, Tuple

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BOOL, BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import Handshaked, Signal
from hwt.pyUtils.arrayQuery import flatten
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.statements import HlsStreamProcWhile, HlsStreamProcCodeBlock, \
    HlsStreamProcIf, HlsStreamProcStm, HlsStreamProcFor, HlsStreamProcBreak, \
    HlsStreamProcContinue, HlsStreamProcSwitch
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcRead, \
    HlsStreamProcWrite, IN_STREAM_POS, HlsStreamProcReadAxiStream
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa, AnyStm
from hwtHls.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline
from hwtLib.amba.axis import AxiStream
from hwt.interfaces.hsStructIntf import HsStructIntf


class HlsStreamProc():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> SSA -> HLS netlist -> RTL netlist

    :ivar ctx: a RTL context for a signals used in input code
    """

    def __init__(self, parentUnit: Unit,
                 ssa_passes:Optional[List[SsaPass]]=None,
                 hlsnetlist_passes:Optional[List[HlsNetlistPass]]=None,
                 rtlnetlist_passes:Optional[List[RtlNetlistPass]]=None,
                 freq: Optional[Union[int, float]]=None):
        """
        :note: ssa_passes, hlsnetlist_passes, rtlnetlist_passes parameters are meant as an override to specification from target platform
        :param freq: override of the clock frequency, if None the frequency of clock associated with parent is used
        """
        self.parentUnit = parentUnit
        if freq is None:
            freq = parentUnit.clk.FREQ
        self.freq = freq
        self._ctx = RtlNetlist()
        self.ssaCtx = SsaContext()
        p = parentUnit._target_platform
        if ssa_passes is None:
            ssa_passes = p.ssa_passes
        self.ssa_passes = ssa_passes
        if hlsnetlist_passes is None:
            hlsnetlist_passes = p.hlsnetlist_passes
        self.hlsnetlist_passes = hlsnetlist_passes
        if rtlnetlist_passes is None:
            rtlnetlist_passes = p.rtlnetlist_passes
        self.rtlnetlist_passes = rtlnetlist_passes

    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, "NOT_SPECIFIED"]=NOT_SPECIFIED) -> RtlSignal:
        return Unit._sig(self, name, dtype, def_val, nop_val)
    
    def var(self, name:str, dtype:HdlType):
        """
        Create a thread local variable.
        """
        return Unit._sig(self, name, dtype)

    def read(self,
             src: Union[AxiStream, Handshaked],
             type_or_size: Union[HdlType, RtlSignal, int]=NOT_SPECIFIED,
             inStreamPos=IN_STREAM_POS.BODY):
        """
        Create a read statement in thread.
        """
        
        if isinstance(src, AxiStream):
            return HlsStreamProcReadAxiStream(self, src, type_or_size, inStreamPos)
        else:
            if isinstance(src, RtlSignal):
                assert src._ctx is not self._ctx, ("Read should be used only for IO, it is not required for hls variables")
            if isinstance(src, (Handshaked, HsStructIntf)):
                dtype = src.data._dtype
            elif isinstance(src, (Signal, RtlSignal)):
                dtype = src._dtype
            else:
                raise NotImplementedError(src)    

            if type_or_size is NOT_SPECIFIED:
                type_or_size = dtype
            else:
                assert type_or_size == dtype

            assert inStreamPos is IN_STREAM_POS.BODY
            return HlsStreamProcRead(self, src, dtype)

    def write(self,
              src:Union[HlsStreamProcRead, Handshaked, AxiStream, bytes, HValue],
              dst:Union[AxiStream, Handshaked]):
        """
        Create a write statement in thread.
        """
        return HlsStreamProcWrite(self, src, dst)

    def While(self, cond: Union[RtlSignal, bool], *body: AnyStm):
        """
        Create a while statement in thread.
        """
        return HlsStreamProcWhile(self, toHVal(cond, BOOL), list(body))

    def For(self,
            init: Union[AnyStm, Tuple[AnyStm, ...]],
            cond: Union[Tuple, RtlSignal],
            step: Union[AnyStm, Tuple[AnyStm, ...]],
            *body: AnyStm):
        if not isinstance(init, (tuple, list, deque)):
            assert isinstance(init, (HdlAssignmentContainer, HlsStreamProcStm)), init
            init = [init, ]
        cond = toHVal(cond, BOOL)
        if not isinstance(step, (tuple, list, deque)):
            assert isinstance(step, (HdlAssignmentContainer, HlsStreamProcStm)), step
            step = [step, ]

        return HlsStreamProcFor(self, init, cond, step, list(body))

    def Break(self):
        return HlsStreamProcBreak(self)

    def Continue(self):
        return HlsStreamProcContinue(self)

    def If(self, cond: Union[RtlSignal, bool], *body: AnyStm):
        return HlsStreamProcIf(self, toHVal(cond, BOOL), list(body))
    
    def Switch(self, switchOn):
        return HlsStreamProcSwitch(self, toHVal(switchOn))
    
    def _format_code(self, code: List[AnyStm], label:str="hls_top") -> HlsStreamProcCodeBlock:
        """
        Normalize an input code.
        """
        _code = HlsStreamProcCodeBlock(self)
        _code.name = label
        _code._sensitivity = UniqList()
        _code.statements.extend(flatten(code))
        return _code
    
    def _thread(self, to_ssa: AstToSsa, _code: HlsStreamProcCodeBlock):
        for ssa_pass in self.ssa_passes:
            ssa_pass.apply(self, to_ssa)

        to_hw = SsaSegmentToHwPipeline(to_ssa.start, _code)
        to_hw.extract_pipeline()

        to_hw.extract_hlsnetlist(self.parentUnit, self.freq)
        for hlsnetlist_pass in self.hlsnetlist_passes:
            hlsnetlist_pass.apply(self, to_hw)

        # some optimization could call scheduling and everything after could let
        # the netlist without modifications
        if not to_hw.is_scheduled:
            to_hw.schedulerRun()

        to_hw.construct_rtlnetlist()
        for rtlnetlist_pass in self.rtlnetlist_passes:
            rtlnetlist_pass.apply(self, to_hw)

        return to_hw

    def thread(self, *code: AnyStm):
        """
        Create a thread from a code which will be translated to hw.
        """
        _code = self._format_code(code)
        to_ssa = AstToSsa(self.ssaCtx, "top", _code)
        to_ssa.visit_top_CodeBlock(_code)
        to_ssa.finalize()
        self._thread(to_ssa, _code)
        
