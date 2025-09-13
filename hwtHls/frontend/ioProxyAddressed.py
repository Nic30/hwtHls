from typing import Union, Optional, Sequence, Type as TypingType

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.indexExpansion import PyObjectHwSubscriptRef
from hwtHls.frontend.ioProxy import IoProxy
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.frontend.statementsRead import HlsReadAddressed
from hwtHls.frontend.statementsWrite import HlsWriteAddressed
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import Register, MachineInstr, Type, PointerType, \
    HwtHlsIoMetadata
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from ipCorePackager.constants import INTF_DIRECTION
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


class IoProxyAddressed(IoProxy):
    """
    An base class for object which allow to use memory mapped interface as if it was an array.
    """
    READ_CLS = HlsReadAddressed
    WRITE_CLS = HlsWriteAddressed

    def __getitem__(self, addr):
        return PyObjectHwSubscriptRef(None, self, addr)

    def __setitem__(self, key, newvalue):
        raise AssertionError("This should never be called, instead a frontend should translate this operation")

    @hlsLowLevel
    def read(self, index: Union[AnyHBitsValue], dtype: HdlType, isVolatile:bool=True) -> HlsReadAddressed:
        if dtype.bit_length() != self.rWordT.bit_length():
            raise NotImplementedError()

        return self.READ_CLS(self,
                              self.hls,
                              self.interface,
                              index,
                              self.rWordT,
                              isBlocking=True,
                              isVolatile=isVolatile,
                              )

    @hlsLowLevel
    def write(self, index: Union[AnyHBitsValue], src: AnyHBitsValue, mask=NOT_SPECIFIED, isVolatile:bool=True, mayBecomeFlushable=True) -> HlsWriteAddressed:
        if src is None or isinstance(src, int):
            dtype = self.getDataTypeOfNativeWrite()
            src = dtype.from_py(src)
        else:
            assert src._dtype.bit_length() == self.getDataTypeOfNativeWrite().bit_length(), (
                "For a normal write the width of src and dst must match", dtype, "->",  self.getDataTypeOfNativeWrite(), src, self.interface)

        if isinstance(self.interface, HwIO):
            assert self.interface._direction != INTF_DIRECTION.MASTER, (self.interface, "Can not write to input")

        if mask is not NOT_SPECIFIED:
            raise NotImplementedError()

        if self.mayBecomeFlushable is None:
            self.mayBecomeFlushable = mayBecomeFlushable
        else:
            assert self.mayBecomeFlushable == mayBecomeFlushable, (
                self.interface, "mayBecomeFlushable flag must be the same for all writes to same IO")

        return self.WRITE_CLS(self,
                              self.hls,
                              src,
                              self.interface,
                              index,
                              self.wWordT,
                              isVolatile=isVolatile,
                              mayBecomeFlushable=mayBecomeFlushable
                              )

    @override
    def _getInterfaceTypeForLlvmFnArg(self, toLlvm: 'ToLlvmIrTranslator', ioIndex: int) -> tuple[Type, Type]:
        """
        Get llvm pointer and item type to represent this this IO in argument os functions
        and load/gep/store and alike instructions.
        """
        width = max(self.getDataTypeOfNativeRead().bit_length(), 1)
        if self.hasBlockingRead is not None and not self.hasBlockingRead:
            width += 1

        width = max(width, self.getDataTypeOfNativeWrite().bit_length())

        ptrT = PointerType.get(toLlvm.ctx, ioIndex + 1)
        hwio = getFirstInterfaceInstance(self.interface)
        addrWidth = hwio.ADDR_WIDTH
        arrTy = HBits(width)[int(2 ** hwio.ADDR_WIDTH)]
        elmT = toLlvm._translateArrayType(arrTy)

        return ptrT, elmT, addrWidth

    @override
    def _translateMirToNetlist_HWTFPGA_CLOAD(self,
                               mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: HwIO,
                               srcIoMd: HwtHlsIoMetadata,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, HwIO), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeReadIndexed(netlist, srcIo, name=f"ld_r{instr.getOperand(0).getReg().virtRegIndex()}")
        index.connectHlsIn(n.indexes[0])
        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)
        o = n._portDataOut
        assert isinstance(o._dtype, HBits)
        sign = o._dtype.signed
        if sign is None:
            pass
        elif sign:
            raise NotImplementedError()
        else:
            raise NotImplementedError()
        valCache.add(mbMeta.block, instrDstReg, o, True)

        return [n, ]

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self,
            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Union[HwIO, RtlSignal],
            dstIoMd: HwtHlsIoMetadata,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],
            bufferCapacity: Optional[int],
            writeNodeCls: TypingType[HlsNetNodeWriteIndexed]=HlsNetNodeWriteIndexed) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.IoProxy._translateMirToNetlist_HWTFPGA_CLOAD`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, HwIO), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
        n = writeNodeCls(netlist, dstIo, mayBecomeFlushable=self.mayBecomeFlushable)
        assert bufferCapacity == 0, bufferCapacity
        index.connectHlsIn(n.indexes[0])
        srcVal.connectHlsIn(n._inputs[0])

        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)
        return [n, ]
