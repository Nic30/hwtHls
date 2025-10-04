#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import islice
from typing import Union, List, Optional, Literal, Dict

from hwt.constants import NOT_SPECIFIED
from hwt.hObjList import HObjList
from hwt.hdl.const import HConst
from hwt.hdl.types.defs import  BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld, HdlType_to_HwIO
from hwt.hwIOs.std import HwIODataRdVld, HwIOSignal, HwIORdVldSync, HwIODataVld, \
    HwIODataRd
from hwt.hwModule import HwModule
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_without_registration
from hwt.synthesizer.interfaceLevel.utils import HwIO_walkSignals
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.indexExpansion import PyObjectHwSubscriptRef
from hwtHls.frontend.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.hwIOMeta import HwIOMeta
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistChannels
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.thread import HlsThread, HlsThreadDoesNotUseSsa
from hwtLib.amba.axi_common import Axi_hs


# type representing HwIO and alike classes which are natively supported by HlsScope read/write
ANY_HLS_COMPATIBLE_IO = Union[HwIODataRdVld, HwIOStructRdVld,
                              HwIORdVldSync, Axi_hs,
                              HwIODataVld, HwIODataRd, HwIOSignal,
                              HwIOStruct, RtlSignal,
                              PyObjectHwSubscriptRef]


def HObjList_toTupleRec(v):
    if isinstance(v, HObjList):
        return tuple(HObjList_toTupleRec(i) for i in v)
    else:
        return v


class HlsScope():
    """
    A HLS synthetizer with support for loops and packet level operations

    * code -> LLVM IR SSA -> LLVM MIR non-SSA -> HLS netlist -> RTL netlist

    :ivar parentHwModule: A RTL object where this HLS thread are being synthetized in.
    :ivar freq: Default target frequency for circuit synthesis
    :ivar ctx: a RTL context for a signals used in input code
    :ivar ssaCtx: context for building of SSA
    :ivar passConfig: An object which holds info about all transformations which should be performed.
    :ivar _threads: a list of threads which are being synthetized by this HLS synthetizer
    :ivar _currentThread: a thread which is being currently translated
    :ivar hwIOMeta: a dictionary of meta information about hardware IO interfaces
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
        self._rtlCtx = RtlNetlist()
        self._threads: List[HlsThread] = []
        self._currentThread: Optional[HlsThread] = None
        self._ioProxyForIo: dict[ANY_HLS_COMPATIBLE_IO, IoProxyScalar] = {}
        self.hwIOMeta: Dict[ANY_HLS_COMPATIBLE_IO, HwIOMeta] = {}

    @hlsLowLevel
    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, Literal[NOT_SPECIFIED]]=NOT_SPECIFIED) -> Union[RtlSignal, HwIO]:
        """
        :note: only for forwarding purpose, use :meth:`~.HlsScope.var` instead.
        """
        toLlvm = self._currentThread.toLlvm
        sig = HwModule._sig(self, name, dtype, def_val, nop_val)
        # generate allocas for new variable
        if isinstance(dtype, HStruct):
            pass  # HwModule._sig uses HwIO_without_registration which automatically calls this method in recurse
        elif isinstance(sig, RtlSignal):
            toLlvm._getOrCreateAllocaForTmpVariable(sig, allocaKnownToBeMissing=True)
        elif isinstance(sig, HObjList):
            for _var in sig:
                toLlvm._getOrCreateAllocaForTmpVariable(_var._sig, allocaKnownToBeMissing=True)
        else:
            assert isinstance(sig, HwIO)
            for _var in HwIO_walkSignals(sig):
                toLlvm._getOrCreateAllocaForTmpVariable(_var._sig, allocaKnownToBeMissing=True)

        return sig

    @hlsLowLevel
    def var(self, name:str, dtype:HdlType, arrayPartitionComplete=False) -> Union[RtlSignal, HwIO]:
        """
        Create a thread local variable.
        :ivar arrayPartitionComplete: if true an items of the array will be treated as separate variable.
        """
        if arrayPartitionComplete:
            intf = HdlType_to_HwIO().apply(dtype)
            return HObjList_toTupleRec(HwIO_without_registration(self, intf, name))
        else:
            return self._sig(name, dtype)

    @hlsLowLevel
    def read(self, src: ANY_HLS_COMPATIBLE_IO, blocking:bool=True, isVolatile:bool=True, dtype: Optional[HdlType]=None) -> HlsRead:
        """
        Create a read statement for simple interfaces.
        :param volatile: if true the read has side-effect and must be performed in original code order
        """

        if isinstance(src, PyObjectHwSubscriptRef):
            src: PyObjectHwSubscriptRef
            assert isinstance(src.sequence, IoProxyAddressed), src.sequence
            mem: IoProxyAddressed = src.sequence
            if dtype is not None and dtype != mem.rWordT:
                raise NotImplementedError()
            return mem.READ_CLS(mem, mem.interface, src.index, mem.getDataTypeOfNativeRead(), blocking, isVolatile=isVolatile)
        else:
            proxy = self._ioProxyForIo.get(src)
            if proxy is None:
                proxy = IoProxyScalar(self, src, dtype=dtype)

            r = proxy.read(blocking=blocking, isVolatile=isVolatile)
            if dtype is not None:
                assert dtype == r._dtypeOrig, (dtype, r._dtypeOrig)
            return r

    @hlsLowLevel
    def write(self, src: Union[HlsRead, bytes, int, HConst], dst: ANY_HLS_COMPATIBLE_IO, isVolatile:bool=True, mayBecomeFlushable=True) -> HlsWrite:
        """
        Create a write statement for simple interfaces.
        """
        if isinstance(dst, PyObjectHwSubscriptRef):
            dst: PyObjectHwSubscriptRef
            mem: IoProxyAddressed = dst.sequence
            assert isinstance(mem, IoProxyAddressed), (dst, mem)
            return mem.WRITE_CLS(mem, src, mem.interface, dst.index, mem.getDataTypeOfNativeWrite(),
                                 isVolatile=isVolatile, mayBecomeFlushable=mayBecomeFlushable)
        else:
            proxy = self._ioProxyForIo.get(dst)
            if proxy is None:
                proxy = IoProxyScalar(self, dst)

            w = proxy.write(src, isVolatile=isVolatile, mayBecomeFlushable=mayBecomeFlushable)
            return w

    def addThread(self, t: HlsThread) -> HlsThread:
        """
        Create a thread from a code which will be translated to HW.
        """
        self._threads.append(t)
        return t

    def _mergeNetlists(self, threads: List[HlsThread]):
        # merge content of all netlist to the first one and return it
        assert threads
        netlist: "HlsNetlistCtx" = threads[0].netlist
        netlist.merge(self.hwIOMeta, [t.netlist for t in islice(threads, 1, None)])

        return netlist

    def getPlatform(self) -> DefaultHlsPlatform:
        return self.parentHwModule._target_platform

    def compile(self):
        p = self.getPlatform()
        channels = HlsNetlistChannels(self.hwIOMeta)
        isThread0 = True
        for t in self._threads:
            t: HlsThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            self._currentThread = t
            useSsa = True
            p.beforeThreadToSsa(t)
            try:
                t.compileToSsa()
            except HlsThreadDoesNotUseSsa:
                useSsa = False

            if useSsa:
                p.runSsaPasses(self, t.toLlvm)

            t.compileToNetlist(p)
            # assert t.netlist.subNodes, ("Thread produced empty netlist", t)

        for t in self._threads:
            t: HlsThread
            # we have to wait with compilation until here
            # because we need all IO and sharing constraints specified
            self._currentThread = t
            for callback in t.netlistCallbacks:
                callback(self, t)

            if not isThread0:
                channels.propagateChannelTimingConstraints(t.netlist)

            if t.netlist.subNodes:
                p.runHlsNetlistPasses(self, t.netlist)

            if isThread0:
                isThread0 = False
                t.netlist.scheduler.normalizeSchedulingTime(t.netlist.normalizedClkPeriod)
                if len(self._threads) > 1:
                    channels.propagateChannelTimingConstraints(t.netlist)

        for t in self._threads:
            self._currentThread = t
            if t.netlist.subNodes:
                p.runHlsNetlistToArchNetlist(self, t.netlist)
            for callback in t.archNetlistCallbacks:
                callback(self, t)

        self._currentThread = None  # things after this point are no longer directly associated with a specific thread
        netlist: "HlsNetlistCtx" = self._mergeNetlists(self._threads)
        if len(self._threads) > 1:
            channels.assertAllResolved()

        # drop all analysis except scheduling
        for a in tuple(netlist._analysis_cache.keys()):
            if a is not HlsNetlistAnalysisPassRunScheduler:
                netlist.invalidateAnalysis(a)

        if netlist.subNodes:
            p.runArchNetlistToRtlNetlist(self, netlist)
            p.runHlsAndRtlNetlistPasses(self, netlist)

