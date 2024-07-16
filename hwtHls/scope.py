#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import islice
from typing import Union, List, Optional, Literal, Dict

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.types.defs import  BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType, HwIOStruct
from hwt.hwIOs.std import HwIODataRdVld, HwIOSignal, HwIORdVldSync, HwIODataVld, \
    HwIODataRd
from hwt.hwModule import HwModule
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.ast.thread import HlsThreadForSharedVar
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.pyBytecode.indexExpansion import PyObjectHwSubscriptRef
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.hwIOMeta import HwIOMeta
from hwtHls.io.portGroups import getFirstInterfaceInstance
from hwtHls.netlist.context import HlsNetlistChannels
from hwtHls.netlist.hdlTypeVoid import HVoidExternData
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.context import SsaContext
from hwtHls.thread import HlsThread, HlsThreadDoesNotUseSsa
from hwtLib.amba.axi_common import Axi_hs
from ipCorePackager.constants import INTF_DIRECTION

ANY_HLS_COMPATIBLE_IO = Union[HwIODataRdVld, HwIOStructRdVld,
                              HwIORdVldSync, Axi_hs,
                              HwIODataVld, HwIODataRd, HwIOSignal,
                              HwIOStruct, RtlSignal,
                              PyObjectHwSubscriptRef]


class HlsScope():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> SSA -> LLVM SSA -> LLVM MIR -> HLS netlist -> RTL architecture -> RTL netlist

    :ivar parentHwModule: A RTL object where this HLS thread are being synthetized in.
    :ivar freq: Default target frequency for circuit synthesis
    :ivar ctx: a RTL context for a signals used in input code
    :ivar ssaCtx: context for building of SSA
    :ivar passConfig: An object which holds info about all transformations which should be performed.
    :ivar _threads: a list of threads which are being synthetized by this HLS synthetizer
    """

    def __init__(self, parentHwModule: HwModule,
                 freq: Optional[Union[int, float]]=None,
                 namePrefix:str="hls_"):
        """
        :param freq: override of the clock frequency, if None the frequency of clock associated with parent is used
        """
        self.parentHwModule = parentHwModule
        self.namePrefix = namePrefix
        self._private_hwIOs = parentHwModule._private_hwIOs if parentHwModule else []
        if freq is None:
            freq = parentHwModule.clk.FREQ
        self.freq = freq
        self._ctx = RtlNetlist()
        self.ssaCtx = SsaContext()
        self._threads: List[HlsThread] = []
        self.hwIOMeta: Dict[ANY_HLS_COMPATIBLE_IO, HwIOMeta] = {}

    @hlsLowLevel
    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, Literal[NOT_SPECIFIED]]=NOT_SPECIFIED) -> RtlSignal:
        """
        :note: only for forwarding purpose, use :meth:`~.HlsScope.var` instead.
        """
        return HwModule._sig(self, name, dtype, def_val, nop_val)

    @hlsLowLevel
    def var(self, name:str, dtype:HdlType):
        """
        Create a thread local variable.
        """
        return HwModule._sig(self, name, dtype)

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
    def read(self, src: ANY_HLS_COMPATIBLE_IO, blocking:bool=True) -> HlsRead:
        """
        Create a read statement for simple interfaces.
        """
        _src = src
        src = getFirstInterfaceInstance(src)

        if isinstance(src, (HwIODataRdVld, HwIOStructRdVld, HwIORdVldSync, Axi_hs)):
            if len(src._hwIOs) == 3 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                if isinstance(src, Axi_hs):
                    exclude = (src.ready, src.valid)
                else:
                    exclude = (src.rd, src.vld)
                dtype = HwIO_to_HdlType().apply(src, exclude=exclude)

        elif isinstance(src, HwIODataVld):
            if len(src._hwIOs) == 2 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                dtype = HwIO_to_HdlType().apply(src, exclude=(src.vld,))

        elif isinstance(src, HwIODataRd):
            if len(src._hwIOs) == 2 and hasattr(src, "data"):
                dtype = src.data._dtype
            else:
                dtype = HwIO_to_HdlType().apply(src, exclude=(src.rd,))

        elif isinstance(src, RtlSignal):
            assert src.ctx is not self._ctx, ("Read should be used only for IO, it is not required for HLS variables")
            dtype = src._dtype

        elif isinstance(src, (HwIOSignal, HwIOStruct)):
            dtype = src._dtype

        elif isinstance(src, PyObjectHwSubscriptRef):
            src: PyObjectHwSubscriptRef
            assert isinstance(src.sequence, IoProxyAddressed), src.sequence
            mem: IoProxyAddressed = src.sequence
            return mem.READ_CLS(mem, self, mem.interface, src.index, mem.rWordT, blocking)

        else:
            raise NotImplementedError(src)

        if dtype.bit_length() == 0:
            # if there is no data, the dtype will be empty struct
            dtype = HVoidExternData

        assert _src._direction != INTF_DIRECTION.SLAVE, (_src, "Can not read from output")
        return HlsRead(self, _src, dtype, blocking)

    @hlsLowLevel
    def write(self, src: Union[HlsRead, bytes, int, HConst], dst: ANY_HLS_COMPATIBLE_IO) -> HlsWrite:
        """
        Create a write statement for simple interfaces.
        """
        if src is None or isinstance(src, int):
            dtype = getattr(dst, "_dtype", None)
            if dtype is None:
                if isinstance(dst, PyObjectHwSubscriptRef):
                    dst: PyObjectHwSubscriptRef
                    mem: IoProxyAddressed = dst.sequence
                    assert isinstance(mem, IoProxyAddressed), (dst, mem)
                    dtype = mem.nativeType.element_t
                else:
                    data = getattr(dst, "data", None)
                    if data is None:
                        dtype = HVoidExternData
                    else:
                        dtype = data._dtype
            src = dtype.from_py(src)
        else:
            dtype = src._dtype

        if isinstance(dst, PyObjectHwSubscriptRef):
            dst: PyObjectHwSubscriptRef
            mem: IoProxyAddressed = dst.sequence
            assert isinstance(mem, IoProxyAddressed), (dst, mem)
            return mem.WRITE_CLS(mem, self, src, mem.interface, dst.index, mem.wWordT)
        else:
            assert dst._direction != INTF_DIRECTION.MASTER, (dst, "Can not write to input")
            return HlsWrite(self, src, dst, dtype)

    def addThread(self, t: HlsThread) -> HlsThread:
        """
        Create a thread from a code which will be translated to HW.
        """
        self._threads.append(t)
        return t

    def _mergeNetlists(self, threads: List[HlsThread]):
        # merge content of all netlist to the first one and return it
        assert threads
        netlist: "HlsNetlistCtx" = threads[0].toHw
        netlist.merge(self.hwIOMeta, [t.toHw for t in islice(threads, 1, None)])

        return netlist

    def compile(self):
        p: DefaultHlsPlatform = self.parentHwModule._target_platform
        channels = HlsNetlistChannels(self.hwIOMeta)
        isThread0 = True
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

            if not isThread0:
                channels.propagateChannelTimingConstraints(t.toHw)

            p.runHlsNetlistPasses(self, t.toHw)

            if isThread0:
                isThread0 = False
                t.toHw.scheduler.normalizeSchedulingTime(t.toHw.normalizedClkPeriod)
                if len(self._threads) > 1:
                    channels.propagateChannelTimingConstraints(t.toHw)

        for t in self._threads:
            p.runHlsNetlistToArchNetlist(self, t.toHw)
            for callback in t.archNetlistCallbacks:
                callback(self, t)

        netlist = self._mergeNetlists(self._threads)
        if len(self._threads) > 1:
            channels.assertAllResolved()

        p.runArchNetlistToRtlNetlist(self, netlist)
        p.runHlsAndRtlNetlistPasses(self, netlist)

