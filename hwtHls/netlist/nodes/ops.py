from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.value import HValue
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    _reprMinify
from hwtHls.netlist.typeUtils import dtypeEqualSignIgnore


class HlsNetNodeOperator(HlsNetNode):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hsl operator
    :ivar _dtype: RTL data type of output
    :ivar _usedDummyRtlDeclr: when True the outputs signals are just dummy signals and the body of this node was not allocated yet
    """

    def __init__(self, parentHls: "HlsPipeline",
                 operator: OpDefinition,
                 operand_cnt: int,
                 dtype: Bits,
                 name=None):
        super(HlsNetNodeOperator, self).__init__(parentHls, name=name)
        self.operator = operator
        for i in range(operand_cnt):
            self.dependsOn.append(None)
            self._inputs.append(HlsNetNodeIn(self, i))
        # add containers for io pins
        self._add_output(dtype)
        self._usedDummyRtlDeclr = False

    def resolve_realization(self):
        hls = self.hls
        clk_period = hls.clk_period
        input_cnt = len(self.dependsOn)

        if self.operator is AllOps.TERNARY:
            bit_length = self.getInputDtype(1).bit_length()
            input_cnt = input_cnt // 2 + 1
        else:
            bit_length = self.getInputDtype(0).bit_length()

        r = hls.platform.get_op_realization(
            self.operator, bit_length,
            input_cnt, clk_period)
        self.assignRealization(r)

    def allocateRtlInstanceOutDeclr(self, allocator: "HlsAllocator", o: HlsNetNodeOut):
        # [todo] the output dtype is unknown, it is probably best if we add dtype to each output/input
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", o)
        s = allocator._sig(f"forwardDeclr{self.name}_{o.out_i:d}", o._dtype)
        allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, self.scheduledOut[0] + epsilon, allocator)
        self._usedDummyRtlDeclr = True

    def allocateRtlInstance(self,
                          allocator: "HlsAllocator",
                          used_signals: SignalsOfStages
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        if not self._usedDummyRtlDeclr:
            try:
                return allocator.netNodeToRtl[op_out]
            except KeyError:
                pass

        operands = []
        for (dep, t) in zip(self.dependsOn, self.scheduledIn):
            _o = allocator.instantiateHlsNetNodeOutInTime(dep, t, used_signals)
            operands.append(_o)
        
        s = self.operator._evalFn(*(o.data for o in operands))
        if isinstance(s, HValue):
            t = TimeIndependentRtlResource.INVARIANT_TIME

        else:
            # create RTL signal expression base on operator type
            t = self.scheduledOut[0] + epsilon
            if s.hasGenericName:
                if self.name is not None:
                    s.name = self.name
                else:
                    s.name = f"v{self._id:d}"
        if self._usedDummyRtlDeclr:
            tis = allocator.netNodeToRtl[op_out]
            raise NotImplementedError()
        else:
            if dtypeEqualSignIgnore(s._dtype, op_out._dtype):
                if s._dtype.signed != op_out._dtype.signed:
                    s = s._convSign(op_out._dtype.signed)
            else:
                raise AssertionError("The HlsNetNode a signals of wrong type", s, op_out, s._dtype, op_out._dtype)
            tis = TimeIndependentRtlResource(s, t, allocator)
        allocator._registerSignal(op_out, tis, used_signals.getForTime(t))
        self._usedDummyRtlDeclr = False
        return tis

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s}>"
        else:
            deps = ", ".join([_reprMinify(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s} [{deps:s}]>"

