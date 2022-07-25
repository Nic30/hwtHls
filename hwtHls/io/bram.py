
from typing import Union, Literal, List

from hwt.hdl.constants import WRITE, READ
from hwt.hdl.statements.statement import HdlStatement
from hwt.interfaces.std import BramPort_withoutClk
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend. pyBytecode.addressedIo import AddressedIoProxy
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWrite, HlsWriteAddressed
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeWriteIndexed, HOrderingVoidT
from hwtHls.netlist.nodes.node import SchedulizationDict
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer


class HlsNetNodeWriteCommandBram(HlsNetNodeWriteIndexed):

    def __init__(self, netlist:"HlsNetlistCtx", src:BramPort_withoutClk, cmd: Union[Literal[READ], Literal[WRITE]]):
        HlsNetNodeWriteIndexed.__init__(self, netlist, NOT_SPECIFIED, src, addOrderingOut=False)
        self.cmd = cmd
        en = src.en
        if en._sig._nop_val is NOT_SPECIFIED:
            en._sig._nop_val = en._sig._dtype.from_py(0)
        if src.HAS_W:
            we = src.we
            if we._sig._nop_val is NOT_SPECIFIED:
                we._sig._nop_val = we._sig._dtype.from_py(0)
        self._addOutput(src.dout._dtype, "dout")
        self._addOutput(HOrderingVoidT, "orderingOut")
        
        if cmd == READ:
            # set write data to None
            xWrData = HlsNetNodeConst(netlist, src.dout._dtype.from_py(None))
            netlist.nodes.append(xWrData)
            link_hls_nodes(xWrData._outputs[0], self._inputs[0])

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        return self.scheduleAlapCompactionMultiClock(asapSchedule)

    def resolve_realization(self):
        re = OpRealizationMeta(
            inputWireDelay=0.0,
            inputClkTickOffset=0,
            outputWireDelay=epsilon,
            outputClkTickOffset=(1, *(0 for _ in range(len(self._outputs) - 1)))
        )
        self.assignRealization(re)

    def allocateRtlInstance(self,
                            allocator: "ArchElement",
                          ) -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 2, self.dependsOn
        # [0] - data, [1] - addr, [2:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HOrderingVoidT:
                allocator.instantiateHlsNetNodeOutInTime(sync, t)

        ram: BramPort_withoutClk = self.dst
        wData = self.dependsOn[0]
        addr = self.dependsOn[1]
        key = (ram, addr, wData)
        try:
            # skip instantiation of writes in the same mux
            return allocator.netNodeToRtl[key]
        except KeyError:
            pass
        _wData = allocator.instantiateHlsNetNodeOutInTime(wData, self.scheduledIn[0])
        _addr = allocator.instantiateHlsNetNodeOutInTime(addr, self.scheduledIn[1])

        rtlObj = []
        rtlObj.append(ram.addr(_addr.data))
        if ram.HAS_W:
            if ram.HAS_BE:
                raise NotImplementedError()
            rtlObj.append(ram.din(_wData.data))
            rtlObj.append(ram.we(0))
            
        allocator.netNodeToRtl[key] = rtlObj
        if ram.HAS_R:
            allocator.netNodeToRtl[self._outputs[0]] = TimeIndependentRtlResource(ram.dout, self.scheduledOut[0], allocator)

        return rtlObj


class HlsReadBram(HlsReadAddressed):

    @classmethod
    def _translateMirToNetlist(cls, mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbSync:MachineBasicBlockSyncContainer,
            instr:LoadInst,
            srcIo:Interface,
            index:Union[int, HlsNetNodeOutAny],
            cond:HlsNetNodeOutAny,
            instrDstReg:Register):
    
        valCache: MirToHwtHlsNetlistOpCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, BramPort_withoutClk), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeWriteCommandBram(netlist, srcIo, READ)
        link_hls_nodes(index, n.indexes[0])

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)
        valCache.add(mbSync.block, instrDstReg, n._outputs[0], True)


class HlsWriteBram(HlsWriteAddressed):

    @classmethod
    def _translateMirToNetlist(cls, mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockSyncContainer,
                               instr: MachineInstr,
                               srcVal: HlsNetNodeOutAny,
                               dstIo: Interface,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: HlsNetNodeOutAny):
    
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(dstIo, BramPort_withoutClk), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)

        n = HlsNetNodeWriteCommandBram(netlist, dstIo, WRITE)
        link_hls_nodes(srcVal, n._inputs[0])
        link_hls_nodes(index, n.indexes[0])

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)


class BramArrayProxy(AddressedIoProxy):
    READ_CLS = HlsReadBram
    WRITE_CLS = HlsWriteBram
