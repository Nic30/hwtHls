from typing import Union, Sequence, Literal, List

from hwt.hdl.operatorDefs import HwtOps
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.llvm.llvmIr import Attribute, CallInst, Function, AddDefaultFunctionAttributes
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from tests.frontend.pyBytecode.stmWhile import TRUE


class ExampleHardBlockHwModule_netlist_add1(HardBlockHwModule):

    @override
    def translateCallAttributesToLlvm(self, toLlvm:"ToLlvmIrTranslator", res:CallInst):
        res.setOnlyAccessesArgMemory()
        TheFn: Function = res.getCalledFunction()
        AddDefaultFunctionAttributes(TheFn)
        TheFn.addFnAttrKind(Attribute.Speculatable)
        return  res

    @override
    def translateMirToNetlist(self,
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               builder: HlsNetlistBuilder,
                               inputs: List[HlsNetNodeOut],
                               dstName: str
                               ):
        opRealizationMeta = self.operationRealizationMeta
        if opRealizationMeta:
            raise NotImplementedError()
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        instrDstReg = instr.getOperand(0).getReg()
        assert len(inputs) == 1, inputs
        i = inputs[0]
        res = builder.buildOp(HwtOps.ADD, None, i._dtype, i, builder.buildConstPy(i._dtype, 1))
        res.name = dstName
        valCache.add(mbSync.block, instrDstReg, res, True)


#class ExampleHardBlockHwModule_arch_add1(HardBlockHwModule):

class ExampleHardBlock_netlist(HwModule):

    @override
    def hwConfig(self) -> None:
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk._FREQ = self.FREQ
        w = self.DATA_WIDTH
        self.data_in = HwIOVectSignal(w)
        self.data_out = HwIOVectSignal(w)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            i = hls.read(self.data_in)
            ip1 = ExampleHardBlockHwModule_netlist_add1(i._dtype)(i)
            hls.write(ip1, self.data_out)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    import sys

    sys.setrecursionlimit(int(1e6))
    m = ExampleHardBlock_netlist()
    m.DATA_WIDTH = 8

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
