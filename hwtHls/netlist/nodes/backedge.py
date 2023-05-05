from enum import Enum
from itertools import chain
from math import ceil
from typing import Union, Optional, Generator

from hwt.code import If, Concat
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import HandshakeSync
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.orderable import HdlType_isVoid
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeReadBackedge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None):
        if HdlType_isVoid(dtype):
            src = HandshakeSync()
        else:
            src = HsStructIntf()
            src.T = dtype
        src._name = name
        HlsNetNodeRead.__init__(self, netlist, src, dtype=dtype, name=name)
        self.associatedWrite: Optional[HlsNetNodeWriteBackedge] = None
        self._rtlIoAllocated = False

    def _getSchedulingResourceType(self):
        return self

    def _allocateRtlIo(self):
        """
        Load declaration of the interface and construct its RTL signals.
        """
        if not self._rtlIoAllocated:
            u:Unit = self.netlist.parentUnit
            assert self.src is not None and self.src._ctx is None, (
                "Src interface must not be yet instantiated on parent Unit", self, self.src)
            w = self.associatedWrite
            assert w.dst is self.src or w.dst is None, (w, w.dst)

            self.src = Interface_without_registration(u, self.src, f"hls_{self.name:s}")
            # :note: getattr used to avoid cyclical deps in HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge classes
            if getattr(w, "allocationType", None) == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE:
                w.dst = self.src
            else:
                w.dst = Interface_without_registration(u, self.src.__copy__(), f"hls_{w.name:s}")

            self._rtlIoAllocated = True

    def getRtlValidSig(self, allocator: "ArchElement") -> Union[RtlSignalBase, HValue]:
        if self.associatedWrite.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            if isinstance(self, HlsNetNodeReadBackedge):
                o = self._outputs[0]
                vld = self._valid
                if vld is None:
                    vld = self._validNB
                if vld is None:
                    raise NotImplementedError()
                # assert HdlType_isVoid(o._dtype), (self, o._dtype)
                res = allocator.instantiateHlsNetNodeOutInTime(o, self.scheduledOut[vld.out_i])
                # assert res.data._dtype == BIT, (self, res._dtype)
                # return res.data
                return res
            else:
                return BIT.from_py(1)

        return HlsNetNodeRead.getRtlValidSig(self, allocator)

    def allocateRtlInstance(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid()
        try:
            cur = allocator.netNodeToRtl[op_out]
            if hasNoSpecialControl:
                return cur
            else:
                if op_out in allocator.netNodeToRtl:
                    return []
        except KeyError:
            pass

        self._allocateRtlIo()

        w: HlsNetNodeWriteBackedge = self.associatedWrite
        if w is None or w.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            # allocate as a read from buffer output interface
            return HlsNetNodeRead.allocateRtlInstance(self, allocator)
        else:
            # allocate as a register
            if self._dataVoidOut is not None:
                HlsNetNodeRead._allocateRtlInstanceDataVoidOut(self, allocator)

            init = self.associatedWrite.channelInitValues
            assert self.name is not None, self
            regName = f"{allocator.namePrefix:s}{self.name:s}"
            dtype = self._outputs[0]._dtype
            if not HdlType_isVoid(dtype):
                dtype = self.getRtlDataSig()._dtype

            requiresVld = self.hasValid() or self.hasValidNB() or self._rawValue is not None
            if w.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
                hadInit = bool(init)
                if init:
                    assert w.allocationType == BACKEDGE_ALLOCATION_TYPE.REG, w.allocationType
                    if len(init) > 1:
                        raise NotImplementedError(self, init)
                else:
                    init = ((0,),)

                if HdlType_isVoid(dtype):
                    # assert not self.usedBy[0], self
                    reg = []
                else:
                    _init = init[0][0]
                    reg = allocator._reg(regName, dtype, def_val=_init)
                    reg.hidden = False

                if requiresVld:
                    regVld = allocator._reg(f"{regName:s}_vld", BIT, def_val=int(hadInit))
                    regVld.hidden = False
            else:
                assert w.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, w.allocationType
                assert not init, init
                reg = allocator._sig(regName, dtype)
                if requiresVld:
                    regVld = allocator._sig(f"{regName:s}_vld", BIT)

            if requiresVld:
                self.src.vld(regVld)

            # create RTL signal expression base on operator type
            if HdlType_isVoid(dtype):
                # assert not self.usedBy[0], self
                regTir = []
            else:
                regTir = TimeIndependentRtlResource(reg, self.scheduledOut[0], allocator, False)

            allocator.netNodeToRtl[op_out] = regTir
            if self._rawValue is not None:
                allocator.netNodeToRtl[self._rawValue] = TimeIndependentRtlResource(
                    Concat(regVld, reg), self.scheduledOut[self._rawValue.out_i], allocator, False)

            for vld in (self._valid, self._validNB):
                if vld is None:
                    continue
                allocator.netNodeToRtl[vld] = TimeIndependentRtlResource(
                    regVld, self.scheduledOut[vld.out_i], allocator, False)

            return regTir if hasNoSpecialControl else []

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        if self.associatedWrite is not None:
            yield self.associatedWrite


class BACKEDGE_ALLOCATION_TYPE(Enum):
    """
    :cvar IMMEDIATE: The signal will be used as is without any buffer. This also means that the value of data is not stable and must be immediately used.
        An extra care must be taken to prove that this kind of buffer does not create a combinational loop.
    :cvar REG: Allocate as a DFF register. Used if it is proven that the size of buffer will be max 1 to spare HW resources and to simplify synchronization logic.
    :cvar BUFFER: Object allocates a buffer of length specified by time difference between read/write.
    """
    IMMEDIATE, REG, BUFFER = range(3)


class HlsNetNodeWriteBackedge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.

    :ivar channelInitValues: Optional tuple for value initialization.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 channelInitValues=(),
                 name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, None, name=name)
        self.associatedRead: Optional[HlsNetNodeReadBackedge] = None
        self.channelInitValues = channelInitValues
        self.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER
        self.buffName = None

    def associateRead(self, read: HlsNetNodeReadBackedge):
        assert isinstance(read, HlsNetNodeReadBackedge), read
        read.associatedWrite = self
        self.associatedRead = read
        #self.dst = read.src

    def _getSchedulingResourceType(self):
        return self

    def _extractEnableForNonBufferReg(self, allocator:"ArchElement"):
        """
        If this read-write pair is not instantiated as a buffer it means it does not have associated IO interface.
        In this specific case we have to explicitly resolve synchronization.
        A reg is writen to if it is enabled and not skipped and if every other IO in this clock is either enabled and receives ack from outside
        or it is skipped.
        """
        from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = self.netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)

        extraConds, skipWhen = allocator._copyChannelSync(self,
                  ioDiscovery.extraReadSync.get(self, None),
                  None,
                  None)
        # stI = self.scheduledIn[0] // self.netlist.normalizedClkPeriod - allocator._beginClkI
        # con: ConnectionsOfStage = allocator.connections[stI]
        if extraConds is not None or skipWhen is not None:
            if extraConds is not None:
                en = extraConds.resolve()
            else:
                en = BIT.from_py(1)
            if skipWhen is not None:
                sw = skipWhen.resolve()
                en = en & ~sw

            if isinstance(en, BitsVal):
                # current block en=1
                assert int(en) == 1, (en, self)
                return None
            else:
                assert isinstance(en, RtlSignal), (en, self)
                return en

        return None

    def allocateRtlInstance(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            pass

        dstRead: HlsNetNodeReadBackedge = self.associatedRead
        dstRead._allocateRtlIo()
        if self.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            res = HlsNetNodeWrite.allocateRtlInstance(self, allocator)
            allocator._afterNodeInstantiated(self, res)
            srcWrite = self
            assert dstRead is not None
            dst_t = dstRead.scheduledOut[0]
            src_t = srcWrite.scheduledIn[0]
            # assert dst_t <= src_t, ("This was supposed to be backward edge", dst_t, src_t, srcWrite, dstRead)
            # 1 register at minimum, because we need to break a combinational path
            # the size of buffer is derived from the latency of operations between the io ports
            if src_t <= dst_t:
                # forward edge
                regCnt = (dst_t - src_t) // allocator.netlist.normalizedClkPeriod
            else:
                regCnt = max(ceil((src_t - dst_t) / allocator.netlist.normalizedClkPeriod), 1)
                assert regCnt > 0, self

            assert srcWrite.dst is not dstRead.src, (srcWrite, dstRead)
            if regCnt == 0:
                dstRead.src(srcWrite.dst)
            else:
                assert regCnt >= 0, self
                # :note: latency is 1-2 to break ready chain (it is not always required, but the check is not implemented)
                buffs = HsBuilder(allocator.netlist.parentUnit, srcWrite.dst,
                                  self.buffName if self.buffName else "hls_backward_buff")\
                    .buff(regCnt, latency=(1, 2), init_data=self.channelInitValues)\
                    .end
                dstRead.src(buffs)
                for i in chain(dstRead.src._interfaces, buffs._interfaces):
                    i._sig.hidden = False

        else:
            assert self.associatedRead in allocator.allNodes, (self, allocator, "If this backedge is not buffer both write and read must be in same element")
            t0 = self.scheduledOut[0]
            hasVoidData = HdlType_isVoid(self.dependsOn[0]._dtype)
            if hasVoidData:
                dataDst = dataSrc = None
            else:
                reg: TimeIndependentRtlResource = allocator.instantiateHlsNetNodeOut(self.associatedRead._outputs[0])
                src = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
                if HdlType_isVoid(self.dependsOn[0]._dtype):
                    dataSrc = 1
                else:
                    dataSrc = src.get(t0).data

                dataDst = reg.valuesInTime[0].data
            en = self._extractEnableForNonBufferReg(allocator)
            # the value is not cleared properlz on read if it is not writen
            if dstRead.hasValid() or dstRead.hasValidNB():
                _vld = dstRead._valid
                if _vld is None:
                    _vld = dstRead._validNB
                    assert _vld is not None
                vldDst = allocator.netNodeToRtl[_vld].valuesInTime[0].data
            else:
                vldDst = None

            if en is not None:
                if self.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
                    if vldDst is not None and dataDst is not None:
                        res = If(en,
                                vldDst(1),
                                dataDst(dataSrc),
                              ).Else(
                                vldDst(0),
                                dataDst(None)
                              )
                    elif vldDst is not None:
                        res = vldDst(en)
                    elif dataDst is not None:
                        res = If(en,
                                dataDst(dataSrc),
                              ).Else(
                                dataDst(None)
                              )
                    else:
                        res = []

                else:
                    assert self.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, self.allocationType
                    if dataDst is None:
                        res = []
                    else:
                        assert dataDst._dtype == BIT, (dataDst, dataDst._dtype)
                        res = [dataDst(dataSrc & en)]

                    if vldDst is not None:
                        res.append(vldDst(en))

            else:
                res = []
                if vldDst is not None:
                    res.append(vldDst(1))
                if dataDst is not None:
                    res.append(dataDst(dataSrc))

        allocator.netNodeToRtl[self] = res

        return res
