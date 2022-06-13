#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union, List, Optional

from hwt.hdl.types.defs import  BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Handshaked, Signal, HandshakeSync, VldSynced, \
    RdSynced
from hwt.interfaces.structIntf import Interface_to_HdlType, StructIntf
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.statementsIo import HlsRead, \
    HlsWrite, IN_STREAM_POS, HlsReadAxiStream
from hwtHls.frontend.ast.thread import HlsThreadForSharedVar
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.context import SsaContext
from hwtHls.thread import HlsThread
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.amba.axis import AxiStream


class HlsScope():
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
        self._threads: List[HlsThread] = []

    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, "NOT_SPECIFIED"]=NOT_SPECIFIED) -> RtlSignal:
        """
        :note: only for forwarding purpose, use :meth:`~HlsScope.var` instead.
        """
        return Unit._sig(self, name, dtype, def_val, nop_val)
    
    def var(self, name:str, dtype:HdlType):
        """
        Create a thread local variable.
        """
        return Unit._sig(self, name, dtype)

    def varShared(self, name:str, dtype:HdlType) -> HlsThreadForSharedVar:
        """
        Create a variable with own access management thread.
        """
        v = self.var(name, dtype)
        t = HlsThreadForSharedVar(self, v)
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
            return HlsReadAxiStream(self, src, type_or_size, inStreamPos)

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
        return HlsRead(self, src, dtype)

    def write(self,
              src:Union[HlsRead, Handshaked, AxiStream, bytes, HValue],
              dst:Union[AxiStream, Handshaked]):
        """
        Create a write statement in thread.
        """
        return HlsWrite(self, src, dst)

    def addThread(self, t):
        """
        Create a thread from a code which will be translated to HW.
        """
        self._threads.append(t)
        return t

    def compile(self):
        for t in self._threads:
            t: HlsThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            t.compileToSsa()
            toSsa = t.toSsa
            # code = t.code
            
            p: DefaultHlsPlatform = self.parentUnit._target_platform
            p.runSsaPasses(self, toSsa)

            # t.toHw = toHw = SsaSegmentToHwPipeline(toSsa.start, code)
            # toHw.extract_pipeline()

            # toHw.extract_hlsnetlist(self.parentUnit, self.freq)
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