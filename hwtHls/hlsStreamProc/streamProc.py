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
from hwt.interfaces.structIntf import Interface_to_HdlType, StructIntf
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.statements import HlsStreamProcWhile, \
    HlsStreamProcIf, HlsStreamProcStm, HlsStreamProcFor, HlsStreamProcBreak, \
    HlsStreamProcContinue, HlsStreamProcSwitch
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcRead, \
    HlsStreamProcWrite, IN_STREAM_POS, HlsStreamProcReadAxiStream
from hwtHls.hlsStreamProc.thread import HlsStreamProcThread, \
    HlsStreamProcSharedVarThread, HlsStreamProcThreadFromAst
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.translation.fromAst.astToSsa import AnyStm, AstToSsa
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.amba.axis import AxiStream
from hwtHls.platform.platform import DefaultHlsPlatform


        
class HlsStreamProc():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> SSA -> LLVM SSA -> LLVM MIR -> HLS netlist -> RTL netlist

    :ivar parentUnit: A RTL object where this HLS thread are being synthetized in.
    :ivar freq: Default target frequency for circuit synthesis
    :ivar ctx: a RTL context for a signals used in input code
    :ivar ssaCtx: context for building of SSA
    :ivar passConfig: An object which holds info about all transformations which should be performed.
    :ivar _threads: a list of threads which are being synthetized by this HLS synthetizer
    """

    def __init__(self, parentUnit: Unit,
                 freq: Optional[Union[int, float]]=None):
        """
        :note: ssaPasses, hlsNetlistPasses, rtlNetlistPasses parameters are meant as an override to specification from target platform
        :param freq: override of the clock frequency, if None the frequency of clock associated with parent is used
        """
        self.parentUnit = parentUnit
        if freq is None:
            freq = parentUnit.clk.FREQ
        self.freq = freq
        self._ctx = RtlNetlist()
        self.ssaCtx = SsaContext()
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

    def varShared(self, name:str, dtype:HdlType) -> HlsStreamProcSharedVarThread:
        """
        Create a variable with own access management thread.
        """
        v = self.var(name, dtype)
        t = HlsStreamProcSharedVarThread(self, v)
        self._threads.append(t)
        return t

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

        elif isinstance(src, (Signal, StructIntf)):
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
        Create a thread from a code which will be translated to HW.
        """
        if len(code) == 1 and isinstance(code[0], HlsStreamProcThread):
            t = code[0]
        else:
            t = HlsStreamProcThreadFromAst(self, code, self.parentUnit._name)

        self._threads.append(t)
        return t

    def compile(self):
        for t in self._threads:
            t: HlsStreamProcThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            t.compileToSsa()
            toSsa = t.toSsa
            #code = t.code
            
            p: DefaultHlsPlatform = self.parentUnit._target_platform
            p.runSsaPasses(self, toSsa)

            # t.toHw = toHw = SsaSegmentToHwPipeline(toSsa.start, code)
            # toHw.extract_pipeline()

            #toHw.extract_hlsnetlist(self.parentUnit, self.freq)
            t.toHw = netlist = p.runSsaToNetlist(self, toSsa)
            p.runHlsNetlistPasses(self, netlist)

            # if not toHw.is_scheduled:
            #     toHw.schedulerRun()

            # some optimization could call scheduling and everything after could let
            # the netlist without modifications
        
        for t in self._threads:
            t.toHw.allocate()
            p.runRtlNetlistPasses(self, t.toHw)

    def pragma(self, pragmaObj):
        """
        This function does nothing, it is meant for frontend to to patch when compiling
        the code. 
        """
