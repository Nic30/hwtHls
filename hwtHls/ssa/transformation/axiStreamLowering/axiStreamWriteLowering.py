from collections import defaultdict
from math import ceil, floor
from typing import Dict, Union, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE, BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.ast.statements import HlsStm
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, HlsStmReadEndOfFrame
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame, \
    HlsWrite
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.io.amba.axiStream.stmWrite import HlsStmWriteAxiStream
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.axiStreamLowering.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtLib.amba.axis import AxiStream
from pyMathBitPrecise.bit_utils import mask


class SsaPassAxiStreamWriteLowering(SsaPassAxiStreamReadLowering):
    """
    """

    def _detectIoAccessStatements(self, startBlock: SsaBasicBlock) -> Tuple[UniqList[AxiStream], Dict[AxiStream, UniqList[HlsStm]], UniqList[HlsStm]]:
        ios: UniqList[HlsStm] = UniqList()
        for block in collect_all_blocks(startBlock, set()):
            for instr in block.body:
                if isinstance(instr, (HlsStmWriteAxiStream, HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame)):
                    ios.append(instr)

        intfs: UniqList[AxiStream] = UniqList()
        ioForIntf: Dict[AxiStream, UniqList[HlsStm]] = defaultdict(UniqList)
        for io in ios:
            intfs.append(io.dst)
            ioForIntf[io.dst].append(io)
        
        return intfs, ioForIntf, ios

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        intfs, ioForIntf, _ = self._detectIoAccessStatements(toSsa.start)
        memUpdater = toSsa.m_ssa_u
        for intf in intfs:
            intf: AxiStream
            cfg, predecessorsSeen, startBlock = self._parseCfg(toSsa, intf, ioForIntf)
            # offset variable to resolve where how many bits should be skipped from in current word when writing new part
            offsetVar = self._prepareOffsetVariable(hls, startBlock, intf, memUpdater)
            word_t = HlsStmReadAxiStream._getWordType(intf)
            curWordVar = hls.var(f"{intf._name:s}_curWord", word_t)
            ssaBuilder = toSsa.ssaBuilder
            self.rewriteAdtWriteToWriteOfWords(hls, memUpdater, ssaBuilder, startBlock, None, None, intf.DATA_WIDTH, cfg,
                                               predecessorsSeen, offsetVar, curWordVar, word_t)

    def _insertIntfWrite(self, exprBuilder: SsaExprBuilder,
                         memUpdater: MemorySSAUpdater,
                         originalWrite: Union[HlsStmWriteAxiStream, HlsStmWriteEndOfFrame],
                         curWordVar: StructIntf, word_t: HdlType):
        """
        Create a write of variable to output interface.
        """
        parts = [memUpdater.readVariable(v._sig, originalWrite.block) for v in curWordVar._interfaces]
        lastWordVal = exprBuilder.concat(*parts)
        lastWordWr = HlsWrite(originalWrite.parent, lastWordVal, originalWrite.dst, word_t)
        exprBuilder._insertInstr(lastWordWr)
    
    def _copyWordVariable(self, memUpdater, block, src: StructIntf, dst: StructIntf):
        for iSrc, iDst in zip(src._interfaces, dst._interfaces):
            iSrc: Signal
            iDst: Signal
            srcVal: Union[HValue, SsaInstr] = memUpdater.readVariable(iSrc._sig, block)
            memUpdater.writeVariable(iDst._sig, (), block, srcVal)
    
    def _setMask(self, memUpdater: MemorySSAUpdater, intf: AxiStream, DATA_WIDTH: int, offset: int, bitsToTake: int, curWordVar: StructIntf, block: SsaBasicBlock):
        """
        :param bitsToTake: how many bits are written in this word
        :param offset: number of bits in this word before part set in this function
        :param curWordVar: variable storing a bus word
        :param block: basic block where this set should be performed
        """
        if intf.USE_KEEP or intf.USE_STRB:
            usedBytes = floor(bitsToTake / 8)
            mLow = ceil(offset / 8)
            if mLow == 0 and usedBytes == DATA_WIDTH // 8:
                maskSlice = ()
            else:
                maskSlice = (SLICE.from_py(slice(DATA_WIDTH // 8, mLow, -1)),)
            masks = []
            if intf.USE_KEEP:
                masks.append(curWordVar.keep)
            if intf.USE_STRB:
                masks.append(curWordVar.strb)
            maskVal = Bits(DATA_WIDTH // 8 - mLow).from_py(mask(usedBytes))
            for m in masks:
                memUpdater.writeVariable(m._sig, maskSlice, block, maskVal)
    
    def rewriteAdtWriteToWriteOfWords(self,
                                      hls: "HlsScope",
                                      memUpdater: MemorySSAUpdater,
                                      ssaBuilder: SsaExprBuilder,
                                      startBlock: SsaBasicBlock,
                                      predecessorWrite: Union[HlsStmWriteAxiStream, HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame, None],
                                      write: Union[HlsStmWriteAxiStream, HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame, None],
                                      DATA_WIDTH: int,
                                      cfg: StreamReadWriteGraphDetector,
                                      predecessorsSeen: Dict[HlsStmReadAxiStream, int],
                                      currentOffsetVar: RtlSignal,
                                      curWordVar: StructIntf,
                                      word_t: HdlType):
        """
        Equivalent of :meth:`hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass.SsaPassAxiStreamReadLowering.rewriteAdtReadToReadOfWords`
        """
        writeIsMarker = write is None or isinstance(write, (HlsStmReadStartOfFrame, HlsStmReadEndOfFrame,
                                                           HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame))
        if write is not None:
            predecessorsSeen[write] += 1
            if len(cfg.predecessors[write]) != predecessorsSeen[write]:
                # not all predecessors have been seen and we run this function only after all predecessors were seen
                return
            else:
                # [todo] if the read has multiple predecessors and the last word from them is required and may differ we need o create
                # a phi to select it and then use it as a last word from previous read
                self._sealBlocksUntilStart(memUpdater, startBlock, write.block)

        possibleOffsets = cfg.inWordOffset[write]
        if not possibleOffsets:
            raise AssertionError("This is an accessible read, it should be already removed", write)
        
        if writeIsMarker:
            width = 0
            if write is None:
                pass
            elif isinstance(write, HlsStmWriteStartOfFrame):
                intf: AxiStream = write.dst
                # This is a beginning of the frame, we may have to set leading zeros in masks
                if possibleOffsets != [0, ]:
                    raise NotImplementedError("Set initial write mask", possibleOffsets)
                else:
                    memUpdater.writeVariable(currentOffsetVar, (), startBlock, currentOffsetVar._dtype.from_py(0))

            elif isinstance(write, HlsStmWriteEndOfFrame):
                intf: AxiStream = write.dst
                # all writes which may be the last must be postponed until we reach this or other write
                # because we need to the value of signal "last" and value of masks if end is not aligned
                if len(possibleOffsets) > 1:
                    raise NotImplementedError()
                else:
                    ssaBuilder.setInsertPoint(write.block, write.block.body.index(write))
                    assert len(possibleOffsets) == 1
                    endOffset = possibleOffsets[0]
                    assert endOffset % 8 == 0, (write, endOffset, "must be aligned to octet because AxiStream strb/keep works this way")
                    # set remaining mask bits to 0
                    memUpdater.writeVariable(curWordVar.last._sig, (), write.block, BIT.from_py(1))
                    self._insertIntfWrite(ssaBuilder, memUpdater, write, curWordVar, word_t)

            else:
                raise NotImplementedError(write)

        else:
            intf: AxiStream = write.dst
            sequelBlock = write.block
            src = write.getSrc()
            width = src._dtype.bit_length()
            ssaBuilder.setInsertPoint(write.block, write.block.body.index(write))
    
            # if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified 

            if len(possibleOffsets) > 1:
                # create branch for each offset variant
                offsetCaseCond = []
                _currentOffsetVar = memUpdater.readVariable(currentOffsetVar, write.block)
                for last, off in iter_with_last(possibleOffsets):
                    if last: 
                        # only option left, check not required
                        offEn = None
                    else:
                        offEn = ssaBuilder._binaryOp(_currentOffsetVar, AllOps.EQ,
                                                      currentOffsetVar._dtype.from_py(off % DATA_WIDTH))
                    offsetCaseCond.append(offEn)

                offsetBranches, sequelBlock = ssaBuilder.insertBlocks(offsetCaseCond)
                memUpdater.sealBlock(sequelBlock)
            
            else:
                # there is just a single offset variant 
                offsetBranches, sequelBlock = [write.block], write.block
            
            originalInsertPosition = ssaBuilder.position
            # [todo] aggregate rewrite for all writes in this same block to reduce number of branches because of offset
            #   * writes may sink into common successor (may be beneficial to do this before LLVM to simplify code in advance to improve debugability)
            for off, br in zip(possibleOffsets, offsetBranches):
                off: int
                br: SsaBasicBlock
                ssaBuilder.setInsertPoint(br, originalInsertPosition if br is write.block else None)
                    
                end = off + width
                inWordOffset = off % DATA_WIDTH
                srcOffset = 0
                wordCnt = ceil(max(0, end - 1) / DATA_WIDTH)
                # slice input part form original write input and write it to wordTmp variable
                for last, wordI in iter_with_last(range(wordCnt)):
                    availableBits = width - srcOffset
                    bitsToTake = min(availableBits, DATA_WIDTH - inWordOffset)

                    if bitsToTake == width:
                        _src = src
                    else:
                        _src = ssaBuilder.buildSliceConst(src, srcOffset + bitsToTake, srcOffset)
                        
                    if inWordOffset != 0 or inWordOffset + bitsToTake != DATA_WIDTH:
                        wordVarSlice = (SLICE.from_py(slice(inWordOffset + bitsToTake, inWordOffset, -1)),)
                        inWordOffset = 0
                    else:
                        wordVarSlice = ()

                    if predecessorWrite is not None and\
                            not isinstance(predecessorWrite, HlsStmWriteStartOfFrame) and\
                            wordI == 0 and\
                            off == 0:
                        # write word from previous write because we just resolved it will not be last
                        # the word itself is produced from previous write
                        memUpdater.writeVariable(curWordVar.last._sig, (), br, BIT.from_py(0))
                        self._insertIntfWrite(ssaBuilder, memUpdater, write, curWordVar, word_t)
                    else:
                        self._setMask(memUpdater, intf, DATA_WIDTH, off, bitsToTake, curWordVar, write.block)
                        memUpdater.writeVariable(curWordVar.data._sig, wordVarSlice, br, _src)
                        if not last:
                            self._insertIntfWrite(ssaBuilder, memUpdater, write, curWordVar, word_t)

                    srcOffset += bitsToTake
                # write offset in a specific branch
                memUpdater.writeVariable(currentOffsetVar, (), br, currentOffsetVar._dtype.from_py(end % DATA_WIDTH))

        if write is not None:
            write.block.body.remove(write)

        for _, suc in cfg.cfg[write]:
            self.rewriteAdtWriteToWriteOfWords(hls, memUpdater, ssaBuilder, startBlock, write, suc,
                                               DATA_WIDTH, cfg, predecessorsSeen,
                                               currentOffsetVar, curWordVar, word_t)
