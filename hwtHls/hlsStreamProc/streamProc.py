#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from typing import Union, List, Optional, Tuple

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BOOL, BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Handshaked, Signal, HandshakeSync, VldSynced, \
    RdSynced
from hwt.interfaces.structIntf import Interface_to_HdlType
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
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.amba.axis import AxiStream
from hwt.synthesizer.interface import Interface
from ipCorePackager.constants import DIRECTION


class HlsStreamProcThread():
    """
    A container of a thread which will be compiled later.
    """

    def __init__(self, hls: "HlsStreamProc", code: List[AnyStm]):
        self.hls = hls
        self.code = code
        self.toSsa: Optional[AstToSsa] = None
        self.toHw: Optional[SsaSegmentToHwPipeline] = None
        self._imports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = [] 
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = [] 
    
    def addImport(self, var: Union[RtlSignal, Interface], direction:DIRECTION):
        self._imports.append((var, direction))

    def addExport(self, var: Union[RtlSignal, Interface], direction:DIRECTION):
        self._exports.append((var, direction))
            
    def _formatCode(self, code: List[AnyStm], label:str="hls_top") -> HlsStreamProcCodeBlock:
        """
        Normalize an input code.
        """
        _code = HlsStreamProcCodeBlock(self)
        _code.name = label
        _code._sensitivity = UniqList()
        _code.statements.extend(flatten(code))
        return _code

    def compileToSsa(self):
        _code = self._formatCode(self.code)
        toSsa = AstToSsa(self.hls.ssaCtx, "top", _code)
        toSsa._onAllPredecsKnown(toSsa.start)
        toSsa.visit_top_CodeBlock(_code)
        toSsa.finalize()
        self.toSsa = toSsa


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
        self._threads: List[HlsStreamProcThread] = []

    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, "NOT_SPECIFIED"]=NOT_SPECIFIED) -> RtlSignal:
        """
        :note: only for forwarding purpose, use :meth:`~HlsStreamProc.var` instead.
        """
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

        elif isinstance(src, (Handshaked, HsStructIntf, HandshakeSync, Axi_hs)):
            if len(src._interfaces) == 3 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                if isinstance(src, Axi_hs):
                    exclude = (src.ready, src.valid)
                else:
                    exclude = (src.rd, src.vld)
                dtype = Interface_to_HdlType().apply(src, exclude=exclude)

        elif isinstance(src, VldSynced):
            if len(src._interfaces) == 2 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                dtype = Interface_to_HdlType().apply(src, exclude=(src.vld,))

        elif isinstance(src, RdSynced):
            if len(src._interfaces) == 2 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                dtype = Interface_to_HdlType().apply(src, exclude=(src.rd,))

        elif isinstance(src, RtlSignal):
            assert src._ctx is not self._ctx, ("Read should be used only for IO, it is not required for hls variables")
            dtype = src._dtype

        elif isinstance(src, Signal):
            dtype = src._dtype

        else:
            raise NotImplementedError(src)    

        if type_or_size is not NOT_SPECIFIED:
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

    def thread(self, *code: Union[AnyStm, HlsStreamProcThread]):
        """
        Create a thread from a code which will be translated to hw.
        """
        if len(code) == 1 and isinstance(code[0], HlsStreamProcThread):
            t = code[0]
        else:
            t = HlsStreamProcThread(self, code)

        self._threads.append(t)
        return t
    
    def compile(self):
        for t in self._threads:
            t: HlsStreamProcThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            t.compileToSsa()
            to_ssa = t.toSsa
            code = t.code
            for ssa_pass in self.ssa_passes:
                ssa_pass.apply(self, to_ssa)
    
            t.toHw = to_hw = SsaSegmentToHwPipeline(to_ssa.start, code)
            to_hw.extract_pipeline()
    
            to_hw.extract_hlsnetlist(self.parentUnit, self.freq)
            for hlsnetlist_pass in self.hlsnetlist_passes:
                hlsnetlist_pass.apply(self, to_hw)
    
            if not to_hw.is_scheduled:
                to_hw.schedulerRun()

            # some optimization could call scheduling and everything after could let
            # the netlist without modifications
        
        for t in self._threads:
            t.toHw.construct_rtlnetlist()
            for rtlnetlist_pass in self.rtlnetlist_passes:
                rtlnetlist_pass.apply(self, t.toHw)
              
