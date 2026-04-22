import math
from typing import Optional, Union

from hwt.code import Concat
from hwt.code_utils import rename_signal
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps, COMPARE_OPS
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setDeque import SetDeque
from hwt.pyUtils.typingFuture import override
from hwt.serializer.generic.ops import HWT_TO_HDLCONVERTOR_OPS
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.code import OP_LSHR, OP_ASHR, OP_SHL, OP_ROL, OP_ROR
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.analysis.hlsNetlistSimHandler import HlsNetlistSimHandler
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimStateT
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.netlist.typeUtils import dtypeEqualSignIgnore
from hwtHls.platform.opRealizationMeta import OpRealizationMeta,\
    EMPTY_OP_REALIZATION
from pyMathBitPrecise.bit_utils import mask


OP_INDEX_CONST = HOperatorDef(None, False, "OP_INDEX_CONST")
OpSpecialization_t = Optional[HFloatTmpConfig]


def getNumberOfConstBitsInDriver(o: HlsNetNodeOut):
    n = o.obj
    if isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT:
        return sum(getNumberOfConstBitsInDriver(dep) for dep in n.dependsOn)
    elif isinstance(n, HlsNetNodeConst):
        return n._outputs[0]._dtype.bit_length()
    else:
        return 0


def getConstBitsInDriverMask(o: HlsNetNodeOut):
    n = o.obj
    if isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT:
        res = 0
        offset = 0
        for dep in n.dependsOn:
            res |= getNumberOfConstBitsInDriver(dep) << offset
            offset += dep._dtype.bit_length()

    elif isinstance(n, HlsNetNodeConst):
        return mask(n._outputs[0]._dtype.bit_length())
    else:
        return 0


class HlsNetNodeOperator(HlsNetNode):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this HLS operator
    :ivar operatorSpecialization: optional object holding details about operator implementation
    :ivar _rtlAddName: an override flag which forces name to be present in output HDL
    
    :note: CONCAT operands are in lowest bits first format (Same as LLVM MERGE_VALUES)
    """
    NATIVE_HWT_OPS = {
        *HWT_TO_HDLCONVERTOR_OPS.keys(),
        OP_LSHR,
        OP_ASHR,
        OP_SHL,
        OP_ROL,
        OP_ROR,
        HwtOps.INDEX,
        OP_INDEX_CONST,
    }

    def __init__(self, netlist: "HlsNetlistCtx",
                 operator: HOperatorDef,
                 operandCnt: int,
                 dtype: HBits,
                 name=None,
                 operatorSpecialization:OpSpecialization_t=None):
        """
        :param _dtype: RTL data type of output
        """
        super(HlsNetNodeOperator, self).__init__(netlist, name=name)
        assert operator is not None
        self.operator = operator
        self.operatorSpecialization = operatorSpecialization
        for _ in range(operandCnt):
            self._addInput(None)
        # add containers for io pins
        self._addOutput(dtype, None)
        self._rtlAddName: bool = False

    @override
    def resolveRealization(self):
        netlist = self.netlist
        input_cnt = len(self.dependsOn)
        assert self.operator is not (HwtOps.TERNARY, "Mux has own class HlsNetNodeMux")

        gen = netlist.platform._componentGenerators.get(self.operator)
        if gen is not None:
            gen: ComponentGenerator
            if netlist.dbgSubmoduleBuidTracer is not None:
                with netlist.dbgSubmoduleBuidTracer.scoped(gen, self):
                    r = gen.resolveRealizationOfNode(self)
            else:
                r = gen.resolveRealizationOfNode(self)

            assert isinstance(r, OpRealizationMeta), ("ComponentGenerator.resolveRealizationOfNode must return OpRealizationMeta", self, r, gen)
        else:
            if self.operator in (OP_SHL, OP_ASHR, OP_LSHR, OP_ROL, OP_ROR):
                bit_length = self.getInputDtype(1).bit_length() - getNumberOfConstBitsInDriver(self.dependsOn[1])
            elif self.operator in COMPARE_OPS or self.operator in (HwtOps.ADD, HwtOps.SUB):
                # realization is specified for operator version where all bits are non-constant
                # if some bits are constant the circuit can be simplified, e.g. if one operand is
                # constant this is practicaly the case as the operands have half width
                bit_length = self.getInputDtype(0).bit_length()
                bit_length = math.ceil(((2 * bit_length)
                                         -getNumberOfConstBitsInDriver(self.dependsOn[0])
                                         -getNumberOfConstBitsInDriver(self.dependsOn[1])
                                         ) / 2)
    
            else:
                bit_length = self.getInputDtype(0).bit_length()
            if bit_length == 0:
                # this may happen for example constant operands
                r = EMPTY_OP_REALIZATION
            else:
                try:
                    r = netlist.platform.get_op_realization(
                        self.operator, self.operatorSpecialization, bit_length,
                        input_cnt, netlist.realTimeClkPeriod)
                except TimeConstraintError as e:
                    raise TimeConstraintError(*e.args, self.operator, self._id)

        self.assignRealization(r)

    def hlsNetlistSimGetHandler(self, sim: "HlsNetlistSimulator") -> HlsNetlistSimHandler:
        return HlsNetlistSimHandlerOperator()

    def _rtlAlloc_default(self, allocator:"ArchElement") -> Union[TimeIndependentRtlResourceItem, list[TimeIndependentRtlResourceItem]]:
        op_out = self._outputs[0]
        if HdlType_isVoid(op_out._dtype):
            assert self.operator == HwtOps.CONCAT, self
            res = []
            allocator.netNodeToRtl[op_out] = res
            return res

        operands: list[TimeIndependentRtlResourceItem] = []
        for (dep, t) in zip(self.dependsOn, self.scheduledIn):
            assert dep is not None, ("All inputs must be connected", self, self.dependsOn)
            _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        assert not self._isRtlAllocated, ("After allocation of dependencies this node become allocated,"
                                          " that means that there is a cycle in netlist "
                                          "(immediate backedge should be used to provide forward declaration of RtlSignal if cycle is intentional)", self)

        s = None
        assert self.operator in self.NATIVE_HWT_OPS, ("The operator must be lowered to HWT native form", self)
        if self.operator == HwtOps.CONCAT:
            if HdlType_isVoid(op_out._dtype):
                s = op_out._dtype.from_py(None)
            operands = reversed(operands)
            evalFn = Concat
        else:
            evalFn = self.operator._evalFn

        if s is None:
            if self.operator in (OP_SHL, OP_ASHR, OP_LSHR):
                s = evalFn(*(o.data for o in operands), zextShift=False)  # zextShift=True is only required for LLVM
            elif self.operator in (OP_ROL, OP_ROR):
                # because evalFn would create FSHL/FSHR
                s = HOperatorNode.withRes(self.operator, tuple(o.data for o in operands), op_out._dtype)
            else:
                s = evalFn(*(o.data for o in operands))

        res = self._rtlAlloc_registerOutput(allocator, op_out, s)
        self._isRtlAllocated = True
        return res

    def _rtlAlloc_registerOutput(self, allocator: "ArchElement", op_out: HlsNetNodeOut, s: Union[RtlSignal, HConst])\
            ->Union[TimeIndependentRtlResourceItem, list[TimeIndependentRtlResourceItem]]:
        # create RTL signal expression base on operator type
        if not isinstance(s, HConst) and s._hasGenericName:
            if self.name is not None:
                s._name = f"{allocator.namePrefix:s}{self.name:s}"
            else:
                s._name = f"{allocator.name:s}n{self._id:d}"
            s._hasGenericName = False

            if s._isUnnamedExpr and (self._rtlAddName or self.netlist._dbgAddSignalNamesToData):
                # create an explicit rename of this potentially hidden signal
                s = rename_signal(allocator.netlist.parentHwModule, s, s._name)

        if dtypeEqualSignIgnore(s._dtype, op_out._dtype):
            if HdlType_isVoid(s._dtype):
                assert HdlType_isVoid(op_out._dtype)
            elif s._dtype.signed != op_out._dtype.signed:
                s = s._cast_sign(op_out._dtype.signed)
        else:
            raise AssertionError("The ", self.__class__.__name__,
                                 " signals of wrong type", s, op_out, s._dtype, op_out._dtype)

        return allocator.rtlRegisterOutputRtlSignal(op_out, s, False, False, False)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResourceItem, list[TimeIndependentRtlResourceItem]]:
        assert not self._isMarkedRemoved, self
        assert not self._isRtlAllocated, self
        netlist = self.netlist
        platform = netlist.parentHwModule._target_platform
        gen = platform._componentGenerators.get(self.operator)
        if gen:
            gen: ComponentGenerator
            return gen.toRtlForNode(self, allocator)

        return self._rtlAlloc_default(allocator)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s}>"
        else:
            deps = ", ".join([f"{o.obj._id:d}:{o.out_i}" if isinstance(o, HlsNetNodeOut) else repr(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s} [{deps:s}]>"


class HlsNetlistSimHandlerOperator(HlsNetlistSimHandler):

    @override
    def simCombStep(self, sim:"HlsNetlistSimulator", state:HlsNetlistSimStateT, worklist:SetDeque[HlsNetNode], n:HlsNetNode):
        op = n.operator
        if op == HwtOps.TERNARY:
            res = None
            for v, c in n._iterValueConditionDriverPairs():
                if c is None:
                    res = state[v]
                    break
                c = state[c]
                if not c._is_full_valid():
                    res = state[v]._dtype.from_py(None)
                    break
                if c:
                    res = state[v]
                    break
            assert res is not None
        else:
            deps = []
            for dep in n.dependsOn:
                v = state[dep]
                deps.append(v)

            if op == OP_INDEX_CONST:
                assert len(deps) == 1
                res = deps[0][n.operatorSpecialization]
            else:
                if op == HwtOps.CONCAT:
                    deps = reversed(deps)
                assert n.operator._evalFn is not None, n.operator
                res = n.operator._evalFn(*deps)

        assert len(n._outputs) == 1, n
        o = n._outputs[0]
        prev = state[o]
        if not (prev == res):  # using not ==, instead of != because it is not overloaded
            state[o] = res
            # print(o, res)
            worklist.extend(n.iterOutUserNodes())
