from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


class ComponentGeneratorFABS(ComponentGenerator):
    INPUT_CNT = 1

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        # freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            assert len(node.dependsOn) == 1, node
            opIn = node.dependsOn[0]
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
            raise NotImplementedError()

        return True

