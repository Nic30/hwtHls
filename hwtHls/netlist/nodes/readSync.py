from typing import Union

from hwt.hdl.types.defs import BIT
from hwt.hdl.const import HConst
from hwt.hwIOs.std import HwIODataRdVld, HwIORdVldSync, HwIODataVld, HwIOSignal, \
    HwIODataRd, HwIOBramPort_noClk
from hwt.mainBases import RtlSignalBase
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwt.pyUtils.typingFuture import override
from hwtLib.amba.axi_common import Axi_hs


class HlsNetNodeReadSync(HlsNetNode):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal "valid" for handshaked input, signal "ready" for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, netlist: HlsNetlistCtx):
        HlsNetNode.__init__(self, netlist, None)
        self._addInput("io")
        self._addOutput(BIT, "ack")
        self.operator = "read_sync"

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        assert not self._isRtlAllocated
        raise AssertionError("This node is not intended for RTL and should be lowered to HlsNetNodeRead._validNB or HlsNetNodeWrite._readyNB")

    def _getRtlSigForInput(self, allocator: "ArchElement", i: HlsNetNodeIn):
        return allocator.rtlAllocHlsNetNodeOutInTime(i.obj.dependsOn[i.in_i], self.scheduledOut[0]).data

    def getRtlControlEn(self, allocator: "ArchElement") -> Union[RtlSignalBase, HConst]:
        d = self.dependsOn[0]
        dObj = d.obj
        if isinstance(dObj, HlsNetNodeRead):
            dObj: HlsNetNodeRead
            return dObj.getRtlValidSig(allocator)

        elif isinstance(dObj, HlsNetNodeWrite):
            dObj: HlsNetNodeWrite
            if isinstance(dObj, HlsNetNodeWriteBackedge) and dObj.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                return BIT.from_py(1)

            hwIO = dObj.dst
            if isinstance(hwIO, (HwIODataRdVld, HwIORdVldSync, HwIODataRd)):
                return hwIO.rd._sig
            elif isinstance(hwIO, (HwIOSignal, RtlSignalBase, HwIODataVld)):
                return BIT.from_py(1)
            elif isinstance(hwIO, Axi_hs):
                return hwIO.ready._sig
            elif isinstance(hwIO, HwIOBramPort_noClk):
                return BIT.from_py(1)
            else:
                raise NotImplementedError(hwIO)

        elif isinstance(dObj, HlsNetNodeExplicitSync):
            dObj: HlsNetNodeExplicitSync
            if dObj.extraCond is not None and dObj.skipWhen is not None:
                ec = self._getRtlSigForInput(allocator, dObj.extraCond)
                assert not (isinstance(ec, HConst) and int(ec) == 0), (self, ec, "This should already be optimized out and would cause deadlock", dObj)
                sw = self._getRtlSigForInput(allocator, dObj.skipWhen)
                assert not (isinstance(sw, HConst) and int(sw) == 1), (self, sw, "This should already be optimized out and would cause deadlock", dObj)
                res = ec & ~sw
                assert not (isinstance(res, HConst) and int(res) == 0), (self, res, "This should already be optimized out and would cause deadlock", dObj)
                return res
            elif dObj.extraCond is not None:
                ec = self._getRtlSigForInput(allocator, dObj.extraCond)
                assert not (isinstance(ec, HConst) and int(ec) == 0), (self, ec, "This should already be optimized out and would cause deadlock", dObj)
                return ec
            elif dObj.skipWhen is not None:
                sw = self._getRtlSigForInput(allocator, dObj.skipWhen)
                assert not (isinstance(sw, HConst) and int(sw) == 1), (self, sw, "This should already be optimized out and would cause deadlock", dObj)
                return ~sw
            else:
                return BIT.from_py(1)

        elif isinstance(dObj, HlsNetNodeConst):
            return BIT.from_py(1)
        else:
            raise NotImplementedError(d)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"

