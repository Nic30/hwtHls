from typing import Generator, Optional

from hwt.code import If
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.arrayQuery import grouper
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput


class HlsNetNodeMux(HlsNetNodeOperator):
    """
    Multiplexer operation with one-hot encoded select signal

    :note: inputs in format value, (condition, value)*
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType, name: str=None,
                 operatorSpecialization:Optional[HFloatTmpConfig]=None):
        super(HlsNetNodeMux, self).__init__(
            netlist, HwtOps.TERNARY, 0, dtype, name=name, operatorSpecialization=operatorSpecialization)
        self._rtlAddName = True  # True by default because there is named RtlSignal implementing this node in RTL

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        assert len(self._outputs) == 1, self
        op_out = self._outputs[0]
        assert self._inputs, ("Mux has to have operands", self)
        name = self.name
        if name:
            name = f"{allocator.namePrefix:s}{name}"
        else:
            name = f"{allocator.namePrefix:s}mux{self._id:d}"

        mux_out_s = allocator._sig(name, self._outputs[0]._dtype)
        if len(self._inputs) == 1:
            v = allocator.rtlAllocHlsNetNodeOutInTime(
                    self.dependsOn[0],
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

