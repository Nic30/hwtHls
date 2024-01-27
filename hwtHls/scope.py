#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union, List, Optional, Literal

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
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.ast.thread import HlsThreadForSharedVar
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.pyBytecode.indexExpansion import PyObjectHwSubscriptRef
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.context import SsaContext
from hwtHls.thread import HlsThread, HlsThreadDoesNotUseSsa
from hwtLib.amba.axi_intf_common import Axi_hs


ANY_HLS_COMPATIBLE_IO = Union[Handshaked, HsStructIntf, HandshakeSync, Axi_hs, VldSynced, RdSynced, Signal, StructIntf, RtlSignal, PyObjectHwSubscriptRef]


class HlsScope():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> SSA -> LLVM SSA -> LLVM MIR -> HLS netlist -> RTL architecture -> RTL netlist

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
        self._private_interfaces = parentUnit._private_interfaces
        if freq is None:
            freq = parentUnit.clk.FREQ
        self.freq = freq
        self._ctx = RtlNetlist()
        self.ssaCtx = SsaContext()
        self._threads: List[HlsThread] = []

    @hlsLowLevel
    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, Literal[NOT_SPECIFIED]]=NOT_SPECIFIED) -> RtlSignal:
        """
        :note: only for forwarding purpose, use :meth:`~.HlsScope.var` instead.
        """
        return Unit._sig(self, name, dtype, def_val, nop_val)

    @hlsLowLevel
    def var(self, name:str, dtype:HdlType):
        """
        Create a thread local variable.
        """
        return Unit._sig(self, name, dtype)

    @hlsLowLevel
    def varShared(self, name:str, dtype:HdlType) -> HlsThreadForSharedVar:
        """
        Create a variable with own access management thread.
        """
        v = self.var(name, dtype)
        t = HlsThreadForSharedVar(self, v)
        self._threads.append(t)
        return t

    @hlsLowLevel
    def read(self, src: ANY_HLS_COMPATIBLE_IO, blocking:bool=True):
        """
        Create a read statement for simple interfaces.
        """
        if isinstance(src, (Handshaked, HsStructIntf, HandshakeSync, Axi_hs)):
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
            assert src.ctx is not self._ctx, ("Read should be used only for IO, it is not required for HLS variables")
            dtype = src._dtype

        elif isinstance(src, (Signal, StructIntf)):
            dtype = src._dtype

        elif isinstance(src, PyObjectHwSubscriptRef):
            src: PyObjectHwSubscriptRef
            assert isinstance(src.sequence, IoProxyAddressed), src.sequence
            mem: IoProxyAddressed = src.sequence
            return mem.READ_CLS(mem, self, mem.interface, src.index, mem.rWordT, blocking)

        else:
            raise NotImplementedError(src)

        return HlsRead(self, src, dtype, blocking)

    @hlsLowLevel
    def write(self, src: Union[HlsRead, bytes, int, HValue], dst: ANY_HLS_COMPATIBLE_IO):
        """
        Create a write statement for simple interfaces.
        """
        if isinstance(src, int):
            dtype = getattr(dst, "_dtype", None)
            if dtype is None:
                if isinstance(dst, PyObjectHwSubscriptRef):
                    dst: PyObjectHwSubscriptRef
                    mem: IoProxyAddressed = dst.sequence
                    assert isinstance(mem, IoProxyAddressed), (dst, mem)
                    dtype = mem.nativeType.element_t
                else:
                    dtype = dst.data._dtype
            src = dtype.from_py(src)
        else:
            dtype = src._dtype

        if isinstance(dst, PyObjectHwSubscriptRef):
            dst: PyObjectHwSubscriptRef
            mem: IoProxyAddressed = dst.sequence
            assert isinstance(mem, IoProxyAddressed), (dst, mem)
            return mem.WRITE_CLS(mem, self, src, mem.interface, dst.index, mem.wWordT)
        else:
            return HlsWrite(self, src, dst, dtype)

    def addThread(self, t: HlsThread) -> HlsThread:
        """
        Create a thread from a code which will be translated to HW.
        """
        self._threads.append(t)
        return t

    def compile(self):
        p: DefaultHlsPlatform = self.parentUnit._target_platform
        for t in self._threads:
            t: HlsThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            useSsa = True
            p.beforeThreadToSsa(t)
            try:
                t.compileToSsa()
            except HlsThreadDoesNotUseSsa:
                useSsa = False
            if useSsa:
                p.runSsaPasses(self, t.toSsa)

            t.compileToNetlist(p)
            for callback in t.netlistCallbacks:
                callback(self, t)

            p.runHlsNetlistPasses(self, t.toHw)

        for t in self._threads:
            p.runHlsNetlistToRtlNetlist(self, t.toHw)
            p.runRtlNetlistPasses(self, t.toHw)
