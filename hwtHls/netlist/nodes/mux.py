from typing import Union

from hwt.code import If
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
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

    def allocateRtlInstance(self,
                          allocator: "AllocatorArchitecturalElement",
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        
        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass
        assert self._inputs, ("Mux has to have operands", self)
        name = self.name
        v0 = allocator.instantiateHlsNetNodeOutInTime(self.dependsOn[1], self.scheduledIn[1])
        mux_out_s = allocator._sig(name, v0.data._dtype)
        if len(self._inputs) == 2:
            c, v = self._inputs
            assert c is None, c
            v = allocator.instantiateHlsNetNodeOutInTime(
                    v,
                    self.scheduledIn[0])
            mux_out_s(v.data)       
        else:
            assert len(self._inputs) > 2, self
            mux_top = None
            for (c, v) in grouper(2, zip(self.dependsOn, self.scheduledIn), padvalue=None):
                if v is None:
                    # handle the case where the is only value without condition at the end
                    v = c
                    c = None
                
                if c is not None:
                    c, ct = c
                    c = allocator.instantiateHlsNetNodeOutInTime(c, ct)
                
                v, vt = v
                v = allocator.instantiateHlsNetNodeOutInTime(v, vt)
                    
                if mux_top is None:
                    mux_top = If(c.data, mux_out_s(v.data))
                elif c is not None:
                    mux_top.Elif(c.data, mux_out_s(v.data))
                else:
                    mux_top.Else(mux_out_s(v.data))
    
        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + epsilon
        mux_out_s = TimeIndependentRtlResource(mux_out_s, t, allocator)
        allocator.netNodeToRtl[op_out] = mux_out_s

        return mux_out_s

    def _add_input_and_link(self, src: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self._add_input()
        link_hls_nodes(src, i)
        if isinstance(src, HlsNetNodeOutLazy):
            src.dependent_inputs.append(HlsNetNodeMuxInputRef(self, i.in_i, src))


class HlsNetNodeMuxInputRef():
    """
    An object which is used in HlsNetNodeOutLazy dependencies to update also HlsNetNodeMux object
    once the lazy output of some node on input is resolved.
    """

    def __init__(self, updated_obj: "HlsNetNodeMux", in_i: int, obj: HlsNetNodeOutLazy):
        self.updated_obj = updated_obj
        self.in_i = in_i
        self.obj = obj

    def replace_driver(self, new_obj: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        assert isinstance(new_obj, HlsNetNodeOut), ("Must be a final out port")
        self.updated_obj.dependsOn[self.in_i] = new_obj

        if isinstance(new_obj, HlsNetNodeOut):
            usedBy = new_obj.obj.usedBy[new_obj.out_i]
            i = self.updated_obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)

