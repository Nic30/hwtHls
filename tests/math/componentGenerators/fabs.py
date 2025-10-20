import math

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.code import OP_ABS
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary


class ComponentGeneratorFABS_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @staticmethod
    def evalFn(x: float):
        return math.fabs(x)


class ComponentGeneratorFABS(ComponentGeneratorFp):
    opDef = OP_ABS

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        # freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)

        opIn = node.dependsOn[0]
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            # create a mux to switch between normal and negated value to obtain abs(x)
            assert len(node.dependsOn) == 1, node
            isNeg = builder.buildGetMsb(opIn)
            res = builder.buildMux(opIn._dtype,
                (builder.buildOp(HwtOps.MINUS_UNARY, None, opIn._dtype, opIn),
                 isNeg,
                 opIn))

            debugTracer = node.netlist.dbgSubmoduleBuidTracer
            with debugTracer.scoped(self, node):
                debugTracer.log(("replacing with x<0?-x:x", res))
                replaceOperatorNodeWith(node, res, worklist)
        else:
            assert cfg.hasSign, (node, cfg)
            # clear sign bit
            valueWidth = cfg.getBitWidth() - 1
            opVal = builder.buildIndexConstSlice(HBits(valueWidth), opIn, valueWidth, 0)
            res = builder.buildConcat(opVal, builder.buildConstBit(0))
            debugTracer = node.netlist.dbgSubmoduleBuidTracer
            with debugTracer.scoped(self, node):
                debugTracer.log(("replacing with (same with cleared sign bit)", res))
                replaceOperatorNodeWith(node, res, worklist)
                return True

        return True

