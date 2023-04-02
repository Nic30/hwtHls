from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.value import HValue
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.typeUtils import dtypeEqualSignIgnore
from hwtHls.netlist.nodes.orderable import HdlType_isVoid


class HlsNetNodeOperator(HlsNetNode):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hls operator
    :ivar _dtype: RTL data type of output

    :note: CONCAT operands are in lowest bits first format
    """

    def __init__(self, netlist: "HlsNetlistCtx",
                 operator: OpDefinition,
                 operand_cnt: int,
                 dtype: Bits,
                 name=None):
        super(HlsNetNodeOperator, self).__init__(netlist, name=name)
        self.operator = operator
        for _ in range(operand_cnt):
            self._addInput(None)
        # add containers for io pins
        self._addOutput(dtype, None)

    def resolveRealization(self):
        netlist = self.netlist
        input_cnt = len(self.dependsOn)

        bit_length = self.getInputDtype(0).bit_length()
        if self.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        r = netlist.platform.get_op_realization(
            self.operator, bit_length,
            input_cnt, netlist.realTimeClkPeriod)
        self.assignRealization(r)

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        if HdlType_isVoid(op_out._dtype):
            assert self.operator == AllOps.CONCAT, self
            res = []
            allocator.netNodeToRtl[op_out] = res
            return res

        operands = []
        for (dep, t) in zip(self.dependsOn, self.scheduledIn):
            _o = allocator.instantiateHlsNetNodeOutInTime(dep, t)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        s = None
        if self.operator == AllOps.CONCAT:
            if HdlType_isVoid(op_out._dtype):
                s = op_out._dtype.from_py(None)
            operands = reversed(operands)

        if s is None:
            s = self.operator._evalFn(*(o.data for o in operands))

        if isinstance(s, HValue):
            t = INVARIANT_TIME

        else:
            # create RTL signal expression base on operator type
            t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
            if s.hasGenericName:
                if self.name is not None:
                    s.name = self.name
                else:
                    s.name = f"v{self._id:d}"

        if dtypeEqualSignIgnore(s._dtype, op_out._dtype):
            if HdlType_isVoid(s._dtype):
                assert HdlType_isVoid(op_out._dtype)
            elif s._dtype.signed != op_out._dtype.signed:
                s = s._convSign(op_out._dtype.signed)
        else:
            raise AssertionError("The ", self.__class__.__name__,
                                 " signals of wrong type", s, op_out, s._dtype, op_out._dtype)
        tis = TimeIndependentRtlResource(s, t, allocator, False)

        allocator.netNodeToRtl[op_out] = tis

        return tis

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s}>"
        else:
            deps = ", ".join([f"{o.obj._id:d}:{o.out_i}" if isinstance(o, HlsNetNodeOut) else repr(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s} [{deps:s}]>"

