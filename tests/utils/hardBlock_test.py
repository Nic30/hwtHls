from typing import Union, Sequence, Literal, List

from hwt.hdl.operatorDefs import AllOps
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.hardBlock import HardBlockUnit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.llvm.llvmIr import Attribute, CallInst, Function, AddDefaultFunctionAttributes
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.typingFuture import override
from tests.frontend.pyBytecode.stmWhile import TRUE


class ExampleHardBlockUnit_netlist_add1(HardBlockUnit):

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
                               syncTracker: InsideOfBlockSyncTracker,
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
        res = builder.buildOp(AllOps.ADD, i._dtype, i, builder.buildConstPy(i._dtype, 1))
        res.name = dstName
        valCache.add(mbSync.block, instrDstReg, res, True)


#class ExampleHardBlockUnit_arch_add1(HardBlockUnit):

class ExampleHardBlock_netlist(Unit):

    def _config(self) -> None:
        self.FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self):
        addClkRstn(self)
        self.clk._FREQ = self.FREQ
        w = self.DATA_WIDTH
        self.data_in = VectSignal(w)
        self.data_out = VectSignal(w)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            i = hls.read(self.data_in)
            ip1 = ExampleHardBlockUnit_netlist_add1(i._dtype)(i)
            hls.write(ip1, self.data_out)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    import sys

    sys.setrecursionlimit(int(1e6))
    u = ExampleHardBlock_netlist()
    u.DATA_WIDTH = 8

    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
