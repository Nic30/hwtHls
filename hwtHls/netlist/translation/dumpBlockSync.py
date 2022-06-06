from io import StringIO
from typing import Dict

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineFunction
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer


class HlsNetlistPassDumpBlockSync(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def _printBlockSync(self, mf: MachineFunction, blockSync: Dict[MachineBasicBlock, MachineBasicBlockSyncContainer], out: StringIO):
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockSyncContainer = blockSync[mb]
            out.write(f"{mb.getName().str():s}: {mbSync}\n")
        
    def apply(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        toNetlist: HlsNetlistAnalysisPassMirToNetlist = netlist.requestAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            self._printBlockSync(toNetlist.mf, toNetlist.blockSync, out)
        finally:
            if doClose:
                out.close()

