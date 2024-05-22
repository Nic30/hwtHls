from typing import Generator

from hwt.code import If
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.const import HConst
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.typingFuture import override


class HlsNetNodeMux(HlsNetNodeOperator):
    """
    Multiplexer operation with one-hot encoded select signal

    :note: inputs in format value, (condition, value)*
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name: str=None):
        super(HlsNetNodeMux, self).__init__(
            netlist, HwtOps.TERNARY, 0, dtype, name=name)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        assert len(self._outputs) == 1, self
        op_out = self._outputs[0]
        assert self._inputs, ("Mux has to have operands", self)
        name = self.name
        if name:
            name = f"{allocator.name:s}{name}"
        else:
            name = f"{allocator.name:s}mux{self._id:d}"

        v0 = allocator.rtlAllocHlsNetNodeOutInTime(self.dependsOn[0], self.scheduledIn[0])
        mux_out_s = allocator._sig(name, v0.data._dtype)
        if len(self._inputs) == 1:
            v = self.dependsOn[0]
            v = allocator.rtlAllocHlsNetNodeOutInTime(
                    v,
                    self.scheduledIn[0])
            mux_out_s(v.data)
        else:
            assert len(self._inputs) > 2, self
            mux_top = None
            for (v, c) in grouper(2, zip(self.dependsOn, self.scheduledIn), padvalue=None):
                if c is not None:
                    c, ct = c
                    c = allocator.rtlAllocHlsNetNodeOutInTime(c, ct)

                v, vt = v
                v = allocator.rtlAllocHlsNetNodeOutInTime(v, vt)

                if c is not None and isinstance(c.data, HConst):
                    # The value of condition was resolved to be a constant
                    if c.data:
                        if mux_top is None:
                            mux_top = mux_out_s(v.data)
                        else:
                            mux_top.Else(mux_out_s(v.data))
                        break
                    else:
                        # this case has condition always 0 so we can skip it
                        continue

                if mux_top is None:
                    mux_top = If(c.data, mux_out_s(v.data))
                elif c is not None:
                    mux_top.Elif(c.data, mux_out_s(v.data))
                else:
                    mux_top.Else(mux_out_s(v.data))
            assert mux_top is not None, (self, "Every case of MUX was optimized away")

        res = allocator.rtlRegisterOutputRtlSignal(op_out, mux_out_s, False, False, False)
        self._isRtlAllocated = True
        return res

    def _iterValueConditionInputPairs(self) -> Generator[HlsNetNodeIn, None, None]:
        for (v, c) in grouper(2, self._inputs, padvalue=None):
            yield (v, c)

    def _iterValueConditionDriverPairs(self) -> Generator[HlsNetNodeIn, None, None]:
        for (v, c) in grouper(2, self.dependsOn, padvalue=None):
            yield (v, c)

    def _iterValueConditionDriverInputPairs(self) -> Generator[HlsNetNodeIn, None, None]:
        for (v, c), (vI, cI) in zip(self._iterValueConditionDriverPairs(), self._iterValueConditionInputPairs()):
            yield (v, vI), (c, cI)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            deps = ", ".join([f"{o.obj._id:d}:{o.out_i}" if isinstance(o, HlsNetNodeOut) else repr(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} [{deps:s}]>"

