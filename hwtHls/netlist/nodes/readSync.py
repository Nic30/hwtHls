from typing import Union

from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.interfaces.std import Handshaked, HandshakeSync, VldSynced, Signal, \
    RdSynced, BramPort_withoutClk
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.amba.axi_intf_common import Axi_hs


class HlsNetNodeReadSync(HlsNetNode):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal "valid" for handshaked input, signal "ready" for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, None)
        self._addInput("io")
        self._addOutput(BIT, "ack")
        self.operator = "read_sync"

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self,
                          allocator: "ArchElement",
                          ) -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        try:
            return allocator.netNodeToRtl[r_out]
        except KeyError:
            pass

        t = self.scheduledOut[0]
        en = self.getRtlControlEn(allocator)
        _o = TimeIndependentRtlResource(
            en,
            INVARIANT_TIME if isinstance(en, HValue) else t,
            allocator,
            False)
        allocator.netNodeToRtl[r_out] = _o
        return _o

    def _getRtlSigForInput(self, allocator: "ArchElement", i: HlsNetNodeIn):
        return allocator.instantiateHlsNetNodeOutInTime(i.obj.dependsOn[i.in_i], self.scheduledOut[0]).data
        
    def getRtlControlEn(self, allocator: "ArchElement") -> Union[RtlSignalBase, HValue]:
        d = self.dependsOn[0]
        dObj = d.obj
        if isinstance(dObj, HlsNetNodeRead):
            dObj: HlsNetNodeRead
            return dObj.getRtlValidSig(allocator)

        elif isinstance(dObj, HlsNetNodeWrite):
            dObj: HlsNetNodeWrite
            if isinstance(dObj, HlsNetNodeWriteBackedge) and dObj.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                return BIT.from_py(1)

            intf = dObj.dst
            if isinstance(intf, (Handshaked, HandshakeSync, RdSynced)):
                return intf.rd._sig
            elif isinstance(intf, (Signal, RtlSignalBase, VldSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, Axi_hs):
                return intf.ready._sig
            elif isinstance(intf, BramPort_withoutClk):
                return BIT.from_py(1)
            else:
                raise NotImplementedError(intf)

        elif isinstance(dObj, HlsNetNodeExplicitSync):
            dObj: HlsNetNodeExplicitSync
            if dObj.extraCond is not None and dObj.skipWhen is not None:
                ec = self._getRtlSigForInput(allocator, dObj.extraCond)
                assert not (isinstance(ec, HValue) and int(ec) == 0), (self, ec, "This should already be optimized out and would cause deadlock", dObj)
                sw = self._getRtlSigForInput(allocator, dObj.skipWhen)
                assert not (isinstance(sw, HValue) and int(sw) == 1), (self, sw, "This should already be optimized out and would cause deadlock", dObj)
                res = ec & ~sw
                assert not (isinstance(res, HValue) and int(res) == 0), (self, res, "This should already be optimized out and would cause deadlock", dObj)
                return res
            elif dObj.extraCond is not None:
                ec = self._getRtlSigForInput(allocator, dObj.extraCond)
                assert not (isinstance(ec, HValue) and int(ec) == 0), (self, ec, "This should already be optimized out and would cause deadlock", dObj)
                return ec
            elif dObj.skipWhen is not None:
                sw = self._getRtlSigForInput(allocator, dObj.skipWhen)
                assert not (isinstance(sw, HValue) and int(sw) == 1), (self, sw, "This should already be optimized out and would cause deadlock", dObj)
                return ~sw
            else:
                return BIT.from_py(1)

        elif isinstance(dObj, HlsNetNodeConst):
            return BIT.from_py(1)
        else:
            raise NotImplementedError(d)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"

