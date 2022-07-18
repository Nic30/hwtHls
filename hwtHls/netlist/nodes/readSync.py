from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked, HandshakeSync, VldSynced, Signal, \
    RdSynced
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.io import IO_COMB_REALIZATION, HlsNetNodeRead, \
    HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtLib.amba.axi_intf_common import Axi_hs


class HlsNetNodeReadSync(HlsNetNode, InterfaceBase):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal valid for handshaked input, signal ready for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, None)
        self._add_input()
        self._add_output(BIT)
        self.operator = "read_sync"

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self,
                          allocator: "AllocatorArchitecturalElement",
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
        _o = TimeIndependentRtlResource(
            self.getRtlControlEn(),
            t,
            allocator)
        allocator.netNodeToRtl[r_out] = _o
        return _o

    def getRtlControlEn(self):
        d = self.dependsOn[0]
        if isinstance(d.obj, HlsNetNodeRead):
            if isinstance(d.obj, HlsNetNodeReadBackwardEdge) and not d.obj.associated_write.allocateAsBuffer:
                return BIT.from_py(1)

            intf = d.obj.src
            if isinstance(intf, (Handshaked, HandshakeSync, VldSynced)):
                return intf.vld
            elif isinstance(intf, (Signal, RtlSignalBase, RdSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, Axi_hs):
                return intf.valid
            else:
                raise NotImplementedError(intf)

        elif isinstance(d.obj, HlsNetNodeWrite):
            if isinstance(d.obj, HlsNetNodeWriteBackwardEdge) and not d.obj.allocateAsBuffer:
                return BIT.from_py(1)

            intf = d.obj.dst
            if isinstance(intf, (Handshaked, HandshakeSync, RdSynced)):
                return intf.rd
            elif isinstance(intf, (Signal, RtlSignalBase, VldSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, Axi_hs):
                return intf.ready
            else:
                raise NotImplementedError(intf)

        else:
            raise NotImplementedError(d)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"

