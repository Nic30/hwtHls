from typing import Union

from hwt.code import If
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.netlist.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    link_hls_nodes


class HlsNetNodeMux(HlsNetNodeOperator):
    """
    Multiplexer operation with one-hot encoded select signal
    
    :note: inputs in format value, (condition, value)*
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name: str=None):
        super(HlsNetNodeMux, self).__init__(
            netlist, AllOps.TERNARY, 0, dtype, name=name)

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
        v0 = allocator.instantiateHlsNetNodeOutInTime(self.dependsOn[0], self.scheduledIn[0])
        mux_out_s = allocator._sig(name, v0.data._dtype)
        if len(self._inputs) == 1:
            v = self.dependsOn[0]
            v = allocator.instantiateHlsNetNodeOutInTime(
                    v,
                    self.scheduledIn[0])
            mux_out_s(v.data)       
        else:
            assert len(self._inputs) > 2, self
            mux_top = None
            for (v, c) in grouper(2, zip(self.dependsOn, self.scheduledIn), padvalue=None):
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
        t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
        mux_out_s = TimeIndependentRtlResource(mux_out_s, t, allocator)
        allocator.netNodeToRtl[op_out] = mux_out_s

        return mux_out_s

    def _add_input_and_link(self, src: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self._add_input()
        link_hls_nodes(src, i)
        return i


    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            deps = ", ".join([f"{o.obj._id:d}:{o.out_i}" if isinstance(o, HlsNetNodeOut) else repr(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} [{deps:s}]>"

