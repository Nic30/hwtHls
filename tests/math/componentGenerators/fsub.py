from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat
from tests.math.componentGenerators.fadd import ComponentGeneratorFADD
from tests.math.hFloatTmp.hFloatTmpOps import OP_FADD, OP_FNEG, OP_FSUB


# @hlsBytecode
# def IEEE754FpSub(a: IEEE754FpValue, b: IEEE754FpValue, isSim=False):
#    b.sign = ~b.sign
#    return PyBytecodeInline(IEEE754FpAdd)(a, b, isSim=isSim)
class ComponentGeneratorFSUB_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(a: float, b: float) -> float:
        return a - b


class ComponentGeneratorFSUB(ComponentGeneratorFADD):
    HWT_OPERATOR = HwtOps.SUB
    opDef = OP_FSUB

    @override
    @staticmethod
    def FP_HWMODULE_CLS():
        # :note: using special component just to implement substract would prevent early logic sharing with FADD
        raise AssertionError("This should have been lowered to a+(-b) in HwtHlsInstCombiner::tryReduceHwtHlsFpSub_to_addNeg")

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node:HlsNetNodeOperator, worklist:SetList[HlsNetNode]):
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            return ComponentGeneratorFADD.toHwtCompatibleOperatorBeforeScheduling(self, node, worklist)
        else:
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            op0, op1 = node.dependsOn
            op1neg = builder.buildOp(OP_FNEG, cfg, node._outputs[0]._dtype, op1)
            res = builder.buildOp(OP_FADD, cfg, node._outputs[0]._dtype, op0, op1neg)
            debugTracer = node.netlist.dbgSubmoduleBuidTracer
            with debugTracer.scoped(self, node):
                debugTracer.log(("replacing with", res))
                replaceOperatorNodeWith(node, res, worklist)
            return True

        return False
