from typing import Union, Optional, List

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.array import HArray
from hwt.hdl.types.function import HFunctionConst, HFunction
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.constants import NOT_SPECIFIED
from hwtHls.llvm.llvmIr import MachineInstr, CallInst, AddDefaultFunctionAttributes, Register
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


class HardBlockHwModule(HFunctionConst):
    """
    A container for part of the circuit inlined later during compilation.
    :note: this class inherits from HFunctionConst because the object represents a constant function pointer
    
    [todo] maybe it is better to implement inlining on arch level using processes
    There are multiple ways how to inline function in hwtHls:
       * call normal python function which produces expression/ast and analyze this expression.
       * call hlsBytecode with PyBytecodeInline which inlines function in frontend
       * use :meth:`HardBlockHwModule.translateMirToNetlist` to merge with netlist of parent function on netlist level
       * use :meth:`HardBlockHwModule.translateNetlistToArch` to merge with netlist of parent function on architecture level
    
    :cvar __hlsIsLowLevelFn: a constant flag which tells pybytecode frontend that this object call will translate this object
    :cvar _dtype: constant attribute holding type of HFunction
    :ivar val: name used for user to better identify object in LLVM and netlist
    :ivar hwInputT: type of hardware inputs
    :ivar hwOutputT: type of hardware outputs
    :ivar vld_mask: constant 1 to complete  HFunctionConst attributes
    :ivar placeholderObjectId: index of this in placeholder list
    """

    __hlsIsLowLevelFn = True
    _dtype = HFunction()

    def __init__(self,
                 hwInputT: HdlType,
                 hwOutputT: Union[HdlType, NOT_SPECIFIED]=NOT_SPECIFIED,
                 name: Optional[str]=None,
                 operationRealizationMeta: Optional[OpRealizationMeta]=None):
        if name is None:
            name = self.__class__.__name__
        assert isinstance(hwInputT, HdlType), hwInputT
        if hwOutputT is NOT_SPECIFIED:
            hwOutputT = hwInputT
        else:
            assert isinstance(hwOutputT, HdlType), hwOutputT
        self.hwInputT = hwInputT
        self.hwOutputT = hwOutputT
        self.hasManyInputs = isinstance(hwInputT, (HStruct, HArray))
        self.hasManyOutputs = isinstance(hwOutputT, (HStruct, HArray))
        # there is a single instance of this const and we can not use self as a val because it would result
        # in infinite cycle during cmp
        self.val = name
        self.vld_mask = 1
        self.placeholderObjectId: Optional[int] = None
        self.operationRealizationMeta = operationRealizationMeta

    def __call__(self, *args, **kwargs):
        """
        Construct the HWT call expression for later translation to LLVM
        """
        if self.hasManyInputs:
            raise NotImplementedError()
        else:
            assert not kwargs, kwargs
            assert len(args) <= 1, args

        if self.hasManyOutputs:
            raise NotImplementedError()
        else:
            return HOperatorNode.withRes(HwtOps.CALL, [self, *args], self.hwOutputT)

    def translateCallAttributesToLlvm(self, toLlvm: "ToLlvmIrTranslator", res: CallInst):
        fn = res.getCalledFunction()
        AddDefaultFunctionAttributes(fn)
        res.setOnlyAccessesArgMemory()
        return res

    def translateMirToNetlist(self,
                              mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                              syncTracker: InsideOfBlockSyncTracker,
                              mbSync: MachineBasicBlockMeta,
                              instr: MachineInstr,
                              builder: HlsNetlistBuilder,
                              inputs: List[HlsNetNodeOut],
                              instrDstReg: Register,
                              dstName: str
                              ):
        """
        This method is called to generated HlsNetlist nodes from LLVM MIR.
        Produces netlist (DAG) + input output delays
        * Products of this block will be subject of ArchElement extraction algorithm.
        * internal IO will be realized as normal HlsNetlistNodePortIn/Out links.

        :note: If this method succeeds this object is no longer a part of netlist or any code to process.

        :param mirToNetlist: Main object form LLVM MIR to HlsNetlist translation.
        :param instr: LLVM MIR instruction which is being translated
        """
        opRealizationMeta = self.operationRealizationMeta
        assert opRealizationMeta is not None, ("If this function has no override this default function will construct black box, and needs scheduling info")
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist

        raise NotImplementedError("[todo] construct aggregate  with assigned opRealizationMeta")

        # n = HlsNetNodeRead(netlist, srcIo, name=f"ld_r{instr.getOperand(0).getReg().virtRegIndex():d}")
        #
        # _cond = syncTracker.resolveControlOutput(cond)
        #
        # o = n._outputs[0] if representativeReadStm._isBlocking else n.getRawValue()
        # assert not o._dtype.signed, o
        # valCache.add(mbSync.block, instrDstReg, o, True)
        #
        # return [n, ]
        # res.obj.name = name
        # valCache.add(mb, dst, res, True)

    def translateNetlistToArch(self, n: HlsNetNodeAggregate):
        """
        Produces scheduled ArchElement(s).
        * Product will be subject of synchronization resolution algorithm.
        * internal IO will be realized using channels. 

        :note: If this method succeeds the node is replaced with ArchElement
            and this object is no longer part of any input code.
        """
        raise NotImplementedError()
