
from _collections import deque
from typing import Optional, Type as TypingType, Sequence, Union

from hwt.hdl.const import HConst
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld, HdlType_to_HwIO, \
    HwIOStructRdVldAgent
from hwt.hwIOs.std import HwIORdVldSync
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_without_registration
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.llvm.llvmIr import HwtHlsIoMetadata, IOVectorizationMd, IOVectorizationType
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtSimApi.agents.base import NOP
from hwtSimApi.hdlSimulator import HdlSimulator


class HwIOStructVecRdVld(HwIOStructRdVld):
    """
    Vectorized variant of HwIOStructRdVld
    The vectorized variant have multiple data lanes with independent enable,
    but the valid/ready control signal is shared for all lanes.

    :note: for HLS purposes the LANE_CNT can be None before the IO is physically constructed (hwDeclr called),
        this also tells IoProxyScalar that the program can pick any vectorization factor.
        This is usefull in cases where vectorization factor is not known in advance and is infered from user code.
    :note: By default the user code should work with this IO on per segment data basis.
    :note: Data begins on segment[0], The packing preferences are not part of this HwIO because
        they are properties of connected consummer/producer.
    """

    @override
    def hwConfig(self):
        self.T: HdlType = HwParam(None)
        self.LANE_CNT: Optional[int] = HwParam(None)

    @override
    def hwDeclr(self):
        assert isinstance(self.T, HdlType), (self.__class__, self._name, "does not have correct initialization of T", self.T,)
        assert isinstance(self.LANE_CNT, int), (self.__class__, self._name, "does not have correct initialization of LANE_CNT", self.T,)
        self._dtype = HStruct(
            (self.T[self.LANE_CNT], "segment"),
            *((HBits(self.LANE_CNT), "segmentEn"),) if self.LANE_CNT > 1 else (),
        )

        self.data = HdlType_to_HwIO().apply(self._dtype)
        HwIORdVldSync.hwDeclr(self)

    @override
    def _initSimAgent(self, sim:HdlSimulator):
        self._ag = HwIOStructVecRdVldAgent(sim, self)


def splitConstBitsToLanes(concatedV: HBitsConst, laneCnt: int, segmentWidth: int) -> list[HBitsConst]:
    segmentEn = int(concatedV[:laneCnt * segmentWidth])  # must always be valid
    res: list[HBitsConst] = []
    for i in range(laneCnt):
        en = segmentEn & 1
        segmentEn >>= 1
        if en:
            d = concatedV[(i + 1) * segmentWidth: i * segmentWidth]
            res.append(d)
    return res


DequeAccessedAsVectorizedDataTuple = Union[
    tuple[tuple[HConst, ...], HBitsConst],  # # LANE_CNT > 1, tuple of data for each segment and segmentEn
    tuple[HConst],  # LANE_CNT == 1, data for single segment
]


class DequeAccessedAsVectorized(deque[DequeAccessedAsVectorizedDataTuple]):

    def __init__(self, laneCnt: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.laneCnt = laneCnt

    def append(self, v: DequeAccessedAsVectorizedDataTuple):
        """
        :note: called by Monitor in sim to store data from signals to agent
        """
        if self.laneCnt == 1:
            assert len(v) == 1, v
            assert len(v[0]) == 1, v[0]
            # struct HwIOStructVecRdVld {
            #    struct {
            #       DataTy segments[1];
            #    } data;
            # }
            super().append(v[0][0])
        else:
            # struct HwIOStructVecRdVld {
            #    struct {
            #       DataTy segments[N];
            #       HBits(N) segmentEn;
            #    } data;
            # }
            assert len(v) == 2, (self.laneCnt, v)
            segmentEn = int(v[1])
            assert len(v[0]) == self.laneCnt, (self.laneCnt, len(v[0]))
            for segmentData in v[0]:
                en = segmentEn & 1
                if en:
                    super().append(segmentData)
                segmentEn >>= 1

    def popleft(self) -> DequeAccessedAsVectorizedDataTuple:
        """
        :note: called by Driver to get data to write into signals from the sim
        """
        if self.laneCnt == 1:
            return ((super().popleft(),),)
        else:
            segmentData: Optional[HConst] = []
            segmentEn = 0
            for i in range(self.laneCnt):
                if not self and i != 0:
                    d = None  # data=Undef, segmentEn=0
                    en = 0
                else:
                    d = super().popleft()
                    if d is NOP:
                        d = None
                        en = 0
                    else:
                        d = d
                        en = 1
                segmentData.append(d)
                segmentEn <<= 1
                segmentEn |= en
            return (segmentData, segmentEn)


class HwIOStructVecRdVldAgent(HwIOStructRdVldAgent):
    """
    Simulation agent for :class:`HwIOStructVecRdVld`
    """

    def __init__(self, sim:HdlSimulator, hwIO:HwIOStructVecRdVld, allowNoReset=False):
        HwIOStructRdVldAgent.__init__(self, sim, hwIO, allowNoReset=allowNoReset)
        self.data = DequeAccessedAsVectorized(hwIO.LANE_CNT)


class HlsNetNodeWriteVectorized(HlsNetNodeWrite):

    @override
    def rtlAllocAsIO(self, allocator:"ArchElement") -> list[HdlStatement]:
        dst: HwIOStructVecRdVld = self.dst
        laneWidth = dst.T.bit_length() + 1
        allLanesWidth = self.dependsOn[self._portSrc.in_i]._dtype.bit_length()
        if allLanesWidth == laneWidth - 1:
            expectedLaneCnt = 1
        else:
            expectedLaneCnt = allLanesWidth // laneWidth
            # :note: Concat(en bits, lanedata) or just 1 lanedata
            assert allLanesWidth % laneWidth == 0, (self, allLanesWidth, laneWidth)
        
        if not self.rtlPortPhysicallyExits():
            assert self.dst is not None, self
            assert dst.LANE_CNT is None, (self, dst)
            dst.LANE_CNT = expectedLaneCnt
            u:HwModule = self.netlist.parentHwModule
            name = None
            if dst is not None:
                name = dst._name
            dst._name = name if name is not None else self.netlist.namePrefix + (self.name if self.name is not None else f"n{self._id}")
            self.dst = HwIO_without_registration(u, dst, dst._name)
        else:
            assert self.dst.LANE_CNT == expectedLaneCnt, (self.dst.LANE_CNT, expectedLaneCnt, self)
            
        return super().rtlAllocAsIO(allocator)


class HlsNetNodeReadVectorized(HlsNetNodeRead):
    pass
    # @override
    # def _rtlAllocDatapathIoCreateForDtype(self):
    #    hasValid = self._rtlUseValid
    #    hasReady = self._rtlUseReady
    #    mergedDtype = self._portDataOut._dtype
    #    proxy: HwIoProxyScalarVectorized = self.ioProxy
    #    dtype = proxy.getDataWordType()
    #
    #    if HdlType_isVoid(dtype):
    #        if hasValid and hasReady:
    #            raise NotImplementedError()
    #            src = HwIORdVldSync()
    #        elif hasValid:
    #            raise NotImplementedError()
    #            src = HwIOVldSync()
    #        elif hasReady:
    #            raise NotImplementedError()
    #            src = HwIORdSync()
    #        else:
    #            src = None
    #
    #    else:
    #        if hasValid and hasReady:
    #            src = HwIOStructVecRdVld()
    #
    #        elif hasValid:
    #            raise NotImplementedError()
    #            src = HwIOStructVld()
    #        elif hasReady:
    #            raise NotImplementedError()
    #            src = HwIOStructRd()
    #        else:
    #            raise NotImplementedError()
    #            src = HdlType_to_HwIO().apply(dtype)
    #
    #    src.T = dtype
    #    mergedWidth = mergedDtype.bit_length()
    #    segmentWidth = dtype.bit_length() + 1
    #    assert mergedWidth % segmentWidth == 0, (self, mergedWidth, segmentWidth)
    #    src.LANE_CNT = mergedWidth // segmentWidth
    #    return src


class HwIoProxyScalarVectorized(IoProxyScalar):
    """
    :note: write type is type of single element and there is optional argument of write segmentEn,
           read type is type of single element and there is and the returned read has non-data property segmentEn
           To read all segments at once in raw format simply use :class:`IoProxyScalar` instead of this.
    """

    @override
    def getDataTypeOfNativeWrite(self):
        return self.interface.T

    @override
    def updateLlvmHwtHlsIoMetadata(self, tr: "ToLlvmIrTranslator", md: HwtHlsIoMetadata) -> bool:
        # :note: LANE_CNT may be None, if this is the case it is set after LLVM part resolved it
        md.ioVectorization = IOVectorizationMd(IOVectorizationType.IOV_SCALAR_SPARSE, self.interface.LANE_CNT)
        return True

    @override
    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               *args,
                               readNodeCls: TypingType[HlsNetNodeRead]=HlsNetNodeReadVectorized) -> Sequence[HlsNetNode]:
        return super()._translateMirToNetlist_HWTFPGA_CLOAD(*args, readNodeCls=readNodeCls)

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self,
            *args,
            writeNodeCls: TypingType[HlsNetNodeWrite]=HlsNetNodeWriteVectorized,
            writeNodeConstructorKwArgs={}) -> Sequence[HlsNetNode]:
        return super()._translateMirToNetlist_HWTFPGA_CSTORE(
            *args, writeNodeCls=writeNodeCls,
            writeNodeConstructorKwArgs=writeNodeConstructorKwArgs)

    @staticmethod
    def getLaneCntFromWidth(ioMd: HwtHlsIoMetadata, segmentWidth: int, w: int, *dbgMsg) -> Optional[int]:
        if ioMd.ioVectorization is None:
            assert segmentWidth == w, (segmentWidth, dbgMsg)
            return None
        else:
            if w == segmentWidth:
                return None
                assert segmentWidth == w, (segmentWidth, dbgMsg)
            else:
                laneCnt = w // (segmentWidth + 1)
                assert laneCnt * (segmentWidth + 1) == w, (laneCnt, segmentWidth, laneCnt * (segmentWidth + 1), dbgMsg)
                return laneCnt
