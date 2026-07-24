
from dataclasses import dataclass
from typing import Optional

from hwt.code import split_to_segments
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.hardBlock import ComponentGeneratorForHardBlock
from hwtHls.llvm.llvmIr import Instruction, \
    MachineInstr, MachineRegisterInfo, InstructionToCallInst, CallInst
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import mask
from tests.math.addMasked import AddMaskedHardblock
from tests.math.addTree import OP_ADD_TREE
from tests.math.maskSegments import OP_MASK_SEGMENTS


@dataclass(frozen=True)
class AddMaskedProps():
    stateWidth: int
    inputWidth: int
    inputCnt: int
    hasStateIn: bool


class ComponentGeneratorAddMasked(ComponentGeneratorForHardBlock):
    """
    Component generator for :class:`tests.math.addTreeMasked.AddMaskedHardblock`
    """

    def __init__(self, platform:DefaultHlsPlatform, genNamePrefix:str, moduleName:str):
        super().__init__(platform, genNamePrefix, moduleName)
        self.schedulingCache: dict[AddMaskedProps,
                                   (ComponentRealizationMeta,
                                    ComponentRealizationMeta)
                                   # the list hold in, out time and number of inputs for each layer (relative to schedZero)
                                   ] = {}

    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, stateIn: HBitsConst, dataIn: HBitsConst, maskIn: Optional[HBitsConst]) -> HBitsConst:
        if stateIn is not None and not stateIn._is_full_valid():
            return resUndefVal

        itemCnt = maskIn._dtype.bit_length()
        dataItemWidth = dataIn._dtype.bit_length() // itemCnt
        res = int(stateIn if stateIn is not None else 0)
        # print("_evalFn", maskIn, dataIn, list(split_to_segments(dataIn, dataItemWidth)))
        for d, m in zip(split_to_segments(dataIn, dataItemWidth), maskIn):
            if not m._is_full_valid():
                return resUndefVal
            else:
                if m:
                    if d._is_full_valid():
                        res = res + int(d)
                    else:
                        return resUndefVal
                else:
                    break
        T = stateIn._dtype
        res = T.from_py(res & mask(T.bit_length()))
        return res

    @override
    def getOperationSpecialization(self, *args):
        return None

    @staticmethod
    def getStateWidthInputWidthAndInputCnt(node: HlsNetNode) -> AddMaskedProps:
        if node.operatorSpecialization:
            # this is node which is split on layers, original props are stored in operatorSpecialization
            res = node.operatorSpecialization[0]
            assert isinstance(res, AddMaskedProps), (node, res)
            return res
        else:
            # state?, data, mask
            hasStateIn = len(node.dependsOn) == 3
            outWidth = node._outputs[0]._dtype.bit_length()
            if hasStateIn:
                stateWidth = node.dependsOn[0]._dtype.bit_length()
                assert stateWidth == outWidth
                stateInIndex = 0
            else:
                assert len(node.dependsOn) == 2, (node)
                stateInIndex = -1
                stateWidth = outWidth
                
            inputCnt = node.dependsOn[stateInIndex + 2]._dtype.bit_length()  # width of the mask
            inputWidth = node.dependsOn[stateInIndex + 1]._dtype.bit_length() // inputCnt
            assert inputWidth % inputCnt == 0
            return AddMaskedProps(stateWidth, inputWidth, inputCnt, hasStateIn)

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction,
                              pyObjectPlaceholder: AddMaskedHardblock) -> LlvmIrInstrFunction:
        instr: CallInst = InstructionToCallInst(instr)
        assert instr
        # e.g. placeholderId, stateIn, dataIn, maskIn
        ops = interpret._decodeInstArguments((o.get() for o in tuple(instr.args())[1:]))
        resTy = HBits(instr.getType().getIntegerBitWidth())
        resUndefVal = resTy.from_py(None)

        def _intrinsic_addMasked(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]) -> LlvmIrInstrFunction:
            inArgs = interpret._prepareInstrArguments(ops, regs)
            res = self._evalFn(resUndefVal, *inArgs)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _intrinsic_addMasked

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                               pyObjectPlaceholder: AddMaskedHardblock) -> LlvmMirInstrFunction:
        ops = interpret._decodeInstArguments(MRI, instr, instr.operands())[:-1]
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)
        # e.g. dst, fnId, dstWidth, stateIn, dataIn, maskIn, stateInWidth, dataWidth, maskInWidth, enCond
        inArgCnt = (len(ops) - 3) // 2
        assert inArgCnt == 3, instr
        dst, _, dstWidth = ops[:3]
        resTy = HBits(dstWidth)
        inArgs = tuple(ops[3:3 + inArgCnt])
        inArgsIsConst = tuple(isinstance(a, HConst) for a in inArgs)
        resUndefVal = resTy.from_py(None)

        def _intrinsic_addMasked(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndefVal
            else:
                res = self._evalFn(resUndefVal, *(a if isConst else regs[a]
                                                  for isConst, a in zip(inArgsIsConst, inArgs)))
            regs[dst] = res

        return _intrinsic_addMasked

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        with debugTracer.scoped(self, node):

            assert len(node._outputs) == 1, self

            ops = node.dependsOn
            if len(ops) == 2:
                stateIn = None
                dataIn, maskIn = ops
            else:
                stateIn, dataIn, maskIn = ops
                
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            stateT = node._outputs[0]._dtype
            assert stateT.bit_length() == dataIn._dtype.bit_length() // maskIn._dtype.bit_length(), (node, stateT, dataIn._dtype, maskIn._dtype)
            outCnt = maskIn._dtype.bit_length()
            hasName = node.name is not None
            maskLayer = builder.buildOpManyDst(OP_MASK_SEGMENTS, None,
                                               tuple(stateT for _ in range(outCnt)),
                                               dataIn,
                                               maskIn,
                                               name=node.name + "_mask" if hasName else None)
            adderTreeLayer = builder.buildOp(OP_ADD_TREE, None, stateT, *maskLayer._outputs, name=node.name + "_add" if hasName else None)
    
            if stateIn is not None:
                finalAdd = builder.buildAdd(adderTreeLayer, stateIn, name=node.name + "_finAdd" if hasName else None)
                debugTracer.log(("replacing with", maskLayer, adderTreeLayer.obj, finalAdd.obj))
            else:
                debugTracer.log(("replacing with", maskLayer, adderTreeLayer.obj))
                finalAdd = adderTreeLayer
            
            replaceOperatorNodeWith(node, finalAdd, worklist)
            return True


class ComponentGeneratorAdd1sComplMasked(ComponentGeneratorAddMasked):

    @override
    @staticmethod
    def _evalFn(resUndefVal: HBitsConst, stateIn: HBitsConst, dataIn: HBitsConst, maskIn: Optional[HBitsConst]) -> HBitsConst:
        if stateIn is not None and not stateIn._is_full_valid():
            return resUndefVal

        itemCnt = maskIn._dtype.bit_length()
        dataItemWidth = dataIn._dtype.bit_length() // itemCnt
        res = int(stateIn if stateIn is not None else 0)
        # print("_evalFn", maskIn, dataIn, list(split_to_segments(dataIn, dataItemWidth)))
        for d, m in zip(split_to_segments(dataIn, dataItemWidth), maskIn):
            if not m._is_full_valid():
                return resUndefVal
            else:
                if m:
                    if d._is_full_valid():
                        res = res + int(d)
                    else:
                        return resUndefVal
                else:
                    break

        T = stateIn._dtype
        w = T.bit_length()
        m = mask(w)
        while True:
            overflow = res >> w
            if overflow == 0:
                break
            else:
                res = (res & m) + overflow
            
        res = T.from_py(res)
        return res
    
    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        """
        Conceptionally similar to "FPGA-based TCP/IP Checksum Offloading Engine for 100 Gbps Networks" "Reduction tree version 3"
        * https://doi.org/10.1109/RECONFIG.2018.8641729 
        * https://github.com/R-EAjks-Compute/FPGA-Based-TCP-IP-Checksum-Offloading-Engine-for-100-Gbps-Networks/
        but this generator instantiates only adder trees using OP_ADD_TREE and the decision about adder implementation
        is done in component generator for it.
        """
    
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        with debugTracer.scoped(self, node):
            assert len(node._outputs) == 1, self
            ops = node.dependsOn
            if len(ops) == 2:
                stateIn = None
                dataIn, maskIn = ops
            else:
                stateIn, dataIn, maskIn = ops
                
            builder = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklist)
            stateT = node._outputs[0]._dtype
            inBitwidth = dataIn._dtype.bit_length() // maskIn._dtype.bit_length()
            assert stateT.bit_length() >= inBitwidth, (node, stateT, dataIn._dtype, maskIn._dtype)
            outCnt = maskIn._dtype.bit_length()
            name = node.name
            hasName = node.name is not None
            
            maskLayer = builder.buildOpManyDst(OP_MASK_SEGMENTS, None,
                                               tuple(stateT for _ in range(outCnt)),
                                               dataIn,
                                               maskIn,
                                               name=name + "_mask" if hasName else None)
            
            # build adder tree which will sum the values without overflowing
            minNoOverflowWidthForIn = inBitwidth + log2ceil(outCnt + 1)
            terms: list[HlsNetNodeOut] = []
            for term in maskLayer._outputs:
                term = builder.buildZExt(term, minNoOverflowWidthForIn)
                terms.append(term)
            
            adderTreeLayer = builder.buildOp(OP_ADD_TREE, None, HBits(minNoOverflowWidthForIn), *terms, name=name + "_add" if hasName else None)
            
            # buid adder tree for, sum, overflow and stateIn (to implement ones complement addition)
            terms = []
            outWidth = stateT.bit_length()
            minNoOverflowWidthForOut = max(outWidth, minNoOverflowWidthForIn) + log2ceil(len(terms) + 1 + 1)
            off = 0
            res = adderTreeLayer
            assert res._dtype.bit_length() == minNoOverflowWidthForIn
            while True:
                w = min(minNoOverflowWidthForIn - off, outWidth)
                if w <= 0:
                    del res
                    break
    
                overflow = builder.buildIndexConstSlice(HBits(w), res, off + w, off)
                overflow = builder.buildZExt(overflow, minNoOverflowWidthForOut)
                terms.append(overflow)
                off += w
    
            if stateIn is not None:
                terms.append(builder.buildZExt(stateIn, minNoOverflowWidthForOut))
            
            if len(terms) == 2:
                add2 = builder.buildAdd(terms[0], terms[1], name=name + "_add2" if hasName else None)
            else:
                assert len(terms) > 2, (node, len(terms))
                add2 = builder.buildOp(OP_ADD_TREE, None, terms[0]._dtype, *terms, name=name + "_add2" if hasName else None)
            
            leftoverWidth = minNoOverflowWidthForOut - outWidth
            if leftoverWidth > outWidth:
                raise NotImplementedError("[todo] must repeat previous step to reduce number of add operands") 
            
            # .. code-block::vhld
            #   -- https://doi.org/10.1109/RECONFIG.2018.8641729 
            #   L5(0) = L4(1) + L4(0);
            #   L5(1) = L4(1) + L4(0) + 1;
            #   sumFinal = L5(0) when (L5(0)(16) = '0') else L5(1);
            #
            # [todo] maybe it would be better to create class AddTree1sComplHwModule(AddTreeHwModule) instead
            #        doing this there (readability and code sharing would improve)

            addL = builder.buildTrunc(add2, outWidth, name=name + "_addL0" if hasName else None)
            addH = builder.buildIndexConstSlice(HBits(leftoverWidth), add2, outWidth + leftoverWidth, outWidth, name=name + "_addH0" if hasName else None)
            addH = builder.buildZExt(addH, outWidth)
            addP0 = builder.buildAdd(addL, addH, name=name + "_addP0" if hasName else None)

            addL, addH = (builder.buildConcat(builder.buildConstBit(1), builder.buildZExt(addL, outWidth + 1, name=name + "_addL1" if hasName else None))
                          for term, name in ((addL, "_addL1"), (addH, "_addH1"),)
                          )
            addP1 = builder.buildAdd(addL, addH, name=name + "_addP1" if hasName else None)
            addP1val = builder.buildIndexConstSlice(stateT, addP1, stateT.bit_length() + 1, 1)
            sumFinal = builder.buildMux(stateT, (addP1val, builder.buildGetMsb(addP1), addP0), name=name)
            
            debugTracer.log(("replacing with", sumFinal.obj))
            replaceOperatorNodeWith(node, sumFinal, worklist)
            return True
