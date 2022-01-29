from typing import List, Tuple, Optional, Union

from hwt.code import If
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.hdlType import HdlType
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    link_hls_nodes


class HlsNetNodeMux(HlsNetNodeOperator):
    """
    Multiplexer operation with one-hot encoded select signal
    """

    def __init__(self, parentHls: "HlsPipeline", dtype: HdlType, name: str=None):
        super(HlsNetNodeMux, self).__init__(
            parentHls, AllOps.TERNARY, 0, dtype, name=name)
        self.elifs: List[Tuple[Optional[HlsNetNode], HlsNetNode]] = []

    def allocateRtlInstance(self,
                          allocator: "HlsAllocator",
                          used_signals: SignalsOfStages
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        
        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass
        assert self.elifs, ("Mux has to have operands", self)
        name = self.name
        v0 = allocator.instantiateHlsNetNodeOutInTime(self.elifs[0][1], self.scheduledOut[0], used_signals)
        mux_out_s = allocator._sig(name, v0.data._dtype)
        if len(self.elifs) == 1:
            c, v = self.elifs[0]
            assert c is None, c
            v = allocator.instantiateHlsNetNodeOutInTime(
                    v,
                    self.scheduledIn[0],
                    used_signals)
            mux_out_s(v.data)       
        else:
            mux_top = None
            for elif_i, (c, v) in enumerate(self.elifs):
                if c is not None:
                    c = allocator.instantiateHlsNetNodeOutInTime(c, self.scheduledIn[elif_i * 2], used_signals)
                v = allocator.instantiateHlsNetNodeOutInTime(
                    v,
                    self.scheduledIn[elif_i * 2 + (1 if c is not None else 0)],
                    used_signals)
                    
                if mux_top is None:
                    mux_top = If(c.data, mux_out_s(v.data))
                elif c is not None:
                    mux_top.Elif(c.data, mux_out_s(v.data))
                else:
                    mux_top.Else(mux_out_s(v.data))
    
        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + epsilon
        mux_out_s = TimeIndependentRtlResource(mux_out_s, t, allocator)
        allocator._registerSignal(op_out, mux_out_s, used_signals.getForTime(self.scheduledOut[0]))

        return mux_out_s

    def _add_input_and_link(self, src: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self._add_input()
        link_hls_nodes(src, i)
        if isinstance(src, HlsNetNodeOutLazy):
            src.dependent_inputs.append(HlsNetNodeMuxInputRef(self, len(self.elifs), i.in_i, src))


class HlsNetNodeMuxInputRef():
    """
    An object which is used in HlsNetNodeOutLazy dependencies to update also HlsNetNodeMux object
    once the lazy output of some node on input is resolved.
    """

    def __init__(self, updated_obj: "HlsNetNodeMux", elif_i: int, in_i: int, obj: HlsNetNodeOutLazy):
        self.updated_obj = updated_obj
        self.elif_i = elif_i
        self.in_i = in_i
        self.obj = obj

    def replace_driver(self, new_obj: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        assert isinstance(new_obj, HlsNetNodeOut), ("Must be a final out port")
        c, v = self.updated_obj.elifs[self.elif_i]
        if c is self.obj:
            c = new_obj
        if v is self.obj:
            v = new_obj
        self.updated_obj.elifs[self.elif_i] = (c, v)
        self.updated_obj.dependsOn[self.in_i] = new_obj

        if isinstance(new_obj, HlsNetNodeOut):
            usedBy = new_obj.obj.usedBy[new_obj.out_i]
            i = self.updated_obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)

