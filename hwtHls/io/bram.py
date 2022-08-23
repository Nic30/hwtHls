
from collections import deque
from inspect import isgenerator
from typing import Union, Literal, List, Tuple

from hwt.hdl.constants import WRITE, READ
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import BramPort_withoutClk
from hwt.pyUtils.arrayQuery import single
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.llvm.llvmIr import LoadInst, Register
from hwtHls.llvm.llvmIr import MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeWriteIndexed, HOrderingVoidT
from hwtHls.netlist.nodes.node import SchedulizationDict
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwtHls.ssa.value import SsaValue


class HlsNetNodeWriteCommandBram(HlsNetNodeWriteIndexed):
    """
    A netlist node which is used to represent write of read or write command to BRAM port.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dst:BramPort_withoutClk, cmd: Union[Literal[READ], Literal[WRITE]]):
        HlsNetNodeWriteIndexed.__init__(self, netlist, NOT_SPECIFIED, dst, addOrderingOut=False)
        self.cmd = cmd
        en = dst.en
        if en._sig._nop_val is NOT_SPECIFIED:
            en._sig._nop_val = en._sig._dtype.from_py(0)
        if dst.HAS_W:
            # we can still does not have to be present, it can be replaced by just en on write only ports
            we = getattr(dst, "we", None)
            if we is not None and we._sig._nop_val is NOT_SPECIFIED:
                we._sig._nop_val = we._sig._dtype.from_py(0)
        if dst.HAS_R:
            self._addOutput(dst.dout._dtype, "dout")
        self._addOutput(HOrderingVoidT, "orderingOut")
        
        if cmd == READ:
            assert dst.HAS_R, dst
            # set write data to None
            xWrData = HlsNetNodeConst(netlist, dst.dout._dtype.from_py(None))
            netlist.nodes.append(xWrData)
            link_hls_nodes(xWrData._outputs[0], self._inputs[0])

        elif cmd == WRITE:
            assert dst.HAS_W, dst

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        if self.dst.HAS_R:
            oo = self._outputs[1]
        else:
            oo = self._outputs[0]
        assert oo._dtype is HOrderingVoidT, oo
        return oo 

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
            we = getattr(ram, "we", None)
            if we is not None:
                rtlObj.append(ram.we(0))
            
        allocator.netNodeToRtl[key] = rtlObj
        if ram.HAS_R:
            allocator.netNodeToRtl[self._outputs[0]] = TimeIndependentRtlResource(ram.dout, self.scheduledOut[0], allocator)

        return rtlObj


class HlsReadBram(HlsReadAddressed):

    def __init__(self,
                 parentProxy: "BramArrayProxy",
            parent:"HlsScope",
            src:Union[BramPort_withoutClk, Tuple[BramPort_withoutClk]], index:RtlSignal, element_t:HdlType):
        if isinstance(src, (list, deque)) or isgenerator(src):
            src = tuple(src)

        if isinstance(src, tuple):
            src = single(src, lambda x: x.HAS_R)  # else not implemented
        else:
            assert src.HAS_R

        HlsReadAddressed.__init__(self, parent, src, index, element_t)
        self.parentProxy = parentProxy

    @classmethod
    def _translateMirToNetlist(cls,
            representativeReadStm: "HlsReadBram",
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            mbSync:MachineBasicBlockSyncContainer,
            instr:LoadInst,
            srcIo:Interface,
            index:Union[int, HlsNetNodeOutAny],
            cond:HlsNetNodeOutAny,
            instrDstReg:Register):
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
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

    def __init__(self,
                 parentProxy: "BramArrayProxy",
            parent:"HlsScope",
            src:Union[SsaValue, RtlSignal, HValue],
            dst:Union[BramPort_withoutClk, Tuple[BramPort_withoutClk]],
            index:Union[SsaValue, RtlSignal, HValue],
            element_t:HdlType):
        if isinstance(dst, (list, deque)) or isgenerator(dst):
            dst = tuple(dst)

        if isinstance(dst, tuple):
            dst = single(dst, lambda x: x.HAS_W)  # else not implemented
        else:
            assert dst.HAS_W

        HlsWriteAddressed.__init__(self, parent, src, dst, index, element_t)
        self.parentProxy = parentProxy

    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbSync: MachineBasicBlockSyncContainer,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Interface,
            index: Union[int, HlsNetNodeOutAny],
            cond: HlsNetNodeOutAny):
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
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


class BramArrayProxy(IoProxyAddressed):

    def __init__(self, hls:"HlsScope", interface:BramPort_withoutClk):
        if interface.HAS_W:
            if interface.HAS_BE:
                raise NotImplementedError()
            wordType = interface.din._dtype

        else:
            assert interface.HAS_R, ("Must have atleast one (read/write)", interface)
            wordType = interface.dout._dtype
        
        nativeType = wordType[int(2 ** interface.ADDR_WIDTH)]
        IoProxyAddressed.__init__(self, hls, interface, nativeType)

    READ_CLS = HlsReadBram
    WRITE_CLS = HlsWriteBram
