from math import ceil
from typing import Union, Tuple, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE, BIT
from hwt.interfaces.structIntf import StructIntf
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame
from hwtHls.io.amba.axiStream.stmWrite import HlsStmWriteAxiStream
from hwtHls.ssa.analysis.axisDetectIoAccessGraph import SsaAnalysisAxisDetectIoAccessGraph
from hwtHls.ssa.analysis.axisDetectWriteStatements import SsaAnalysisAxisDetectWriteStatements
from hwtHls.ssa.analysis.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamSsaFsmUtils import AxiStreamSsaFsmUtils, \
    StreamChunkLastMeta
from hwtLib.amba.axis import AxiStream
from ipCorePackager.constants import DIRECTION


class SsaPassAxiStreamWriteLowering(SsaPassAxiStreamReadLowering):
    """
    Same as :class:`hwtHls.ssa.transformation.axiStreamLowering.axiStreamReadLoweringPass.SsaPassAxiStreamReadLowering` just for writes.
    
    The output word is written if the word is completed and it is know if this word is last or not.
    Or if data for next word are stacked or on end of frame marker.
    """

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        wStms: SsaAnalysisAxisDetectWriteStatements = toSsa.getAnalysis(SsaAnalysisAxisDetectWriteStatements)
        for intf in wStms.intfs:
            intf: AxiStream
            intfCfg: SsaAnalysisAxisDetectIoAccessGraph = toSsa.getAnalysis(SsaAnalysisAxisDetectIoAccessGraph(toSsa, intf, DIRECTION.OUT))
            cfg = intfCfg.cfg
            # offset variable to resolve where how many bits should be skipped from in current word when writing new part
            ssaUtils = AxiStreamSsaFsmUtils(hls, toSsa.ssaBuilder, toSsa.m_ssa_u, intf, intfCfg.startBlock)
            curOffsetVar = ssaUtils._prepareOffsetVariable()
            predWordPendingVar = ssaUtils._preparePendingVariable()
            curWordVar = hls.var(f"{intf._name:s}_curWord", ssaUtils.word_t)
            ssaUtils.resetBlockSeals(toSsa.start)
            ssaUtils.prepareLastExpressionForWrites(cfg)
            self.rewriteAdtAccessToWordAccess(ssaUtils, toSsa.start, cfg, curOffsetVar, predWordPendingVar, curWordVar)
            # assert that all original reads were removed from SSA
            self._checkAllInstructionsRemoved(cfg.allStms)

    @classmethod
    def _optionallyConsumePendingWord(cls, ssaUtils: AxiStreamSsaFsmUtils,
                                      predWordPendingVar: RtlSignal,
                                      predWordVar: StructIntf,
                                      condition: SsaInstr,
                                      curWrite: HlsStmWriteAxiStream):
        # write word from previous write because we just resolved it will not be last
        # the word itself is produced from previous write
        assert isinstance(condition, SsaInstr), (
            "The value should not be constant, because "
            "if it is a constant it this should not be generated in the first place", condition)
        # original read should be moved to sequel
        # because now we are just preparing the data for it
        ssaBuilder = ssaUtils.ssaBuilder
        extraWriteBranches, sequelBlock = ssaBuilder.insertBlocks([
            (condition, f"{predWordVar._name}ConsumePending"),
            (None, f"{predWordVar._name}NoConsumePending")
        ])
        ssaBuilder.setInsertPoint(extraWriteBranches[0], 0)
        ssaUtils._insertIntfWrite(predWordVar, curWrite)  # curWrite is there for dst and parent scope
        memUpdater = ssaUtils.memUpdater

        # :note: it is not required to write offset because it does not change
        for br in extraWriteBranches:
            memUpdater.sealBlock(br)

        # append read of new word
        memUpdater.sealBlock(sequelBlock)
        ssaBuilder.setInsertPoint(sequelBlock, 0)  # just at the original place where we cut the orignal block and inserted the optional write before
        memUpdater.writeVariable(predWordPendingVar, (), sequelBlock, BIT.from_py(0))

        return sequelBlock

    def _rewriteAdtAccessToWordAccessInstruction(self,
                                      ssaUtils: AxiStreamSsaFsmUtils,
                                      cfg: StreamReadWriteGraphDetector,
                                      write: Union[HlsStmWriteAxiStream, HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame, None],
                                      curOffsetVar: RtlSignal,
                                      predWordPendingVar: RtlSignal,
                                      curWordVar: StructIntf) -> Tuple[SsaBasicBlock, Optional[int]]:
        """
        Equivalent of :meth:`hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass.SsaPassAxiStreamReadLowering.rewriteAdtReadToReadOfWords`
        """
        writeIsMarker = write is None or isinstance(write, (HlsStmWriteStartOfFrame, HlsStmWriteEndOfFrame))
        memUpdater = ssaUtils.memUpdater
        possibleOffsets = cfg.inWordOffset[write]
        if not possibleOffsets:
            raise AssertionError("This is an accessible read, it should be already removed", write)

        ssaBuilder = ssaUtils.ssaBuilder
        sequelBlock = None
        if writeIsMarker:
            if write is None:
                pass
            elif isinstance(write, HlsStmWriteStartOfFrame):
                # This is a beginning of the frame, we may have to set leading zeros in masks
                for startOffset in possibleOffsets:
                    assert startOffset % 8 == 0, (write, startOffset, "must be aligned to octet because AxiStream strb/keep works this way")

                if len(possibleOffsets) != 1:
                    raise NotImplementedError("Multiple positions of frame start", possibleOffsets)
                else:
                    memUpdater.writeVariable(predWordPendingVar, (), write.block, BIT.from_py(0))
                    ssaBuilder.setInsertPoint(write.block, write.block.body.index(write))
                    ssaUtils._setWriteLast(curWordVar, 0)
                    ssaUtils._setWriteMask(curWordVar, possibleOffsets[0] // 8, 0)
                    ssaUtils._setWriteData(curWordVar, (), 0)

            elif isinstance(write, HlsStmWriteEndOfFrame):
                # all writes which may be the last must be postponed until we reach this or other write
                # because we need to the value of signal "last" and value of masks if end is not aligned
                if not ssaUtils.instrMeta[write].inlinedToPredecessors:
                    ssaBuilder.setInsertPoint(write.block, write.block.body.index(write))
                    for endOffset in possibleOffsets:
                        assert endOffset % 8 == 0, (write, endOffset, "must be aligned to octet because AxiStream strb/keep works this way")
                    # :note: remaining bits in mask should be set to 0 from the start
                    ssaUtils._setWriteLast(curWordVar, 1)
                    ssaUtils._insertIntfWrite(curWordVar, write)
                    memUpdater.writeVariable(predWordPendingVar, (), write.block, BIT.from_py(0))

            else:
                raise NotImplementedError("stream marker of unknown type", write)

        else:
            src = write.getSrc()
            width = src._dtype.bit_length()
            ssaBuilder.setInsertPoint(write.block, write.block.body.index(write))

            # if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
            # :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

            DATA_WIDTH = ssaUtils.DATA_WIDTH
            offsetBranches, sequelBlock = self._createBranchForEachOffsetVariant(
                memUpdater, ssaBuilder, possibleOffsets, DATA_WIDTH, curOffsetVar, write.block)

            originalInsertPosition = ssaBuilder.position
            # [todo] aggregate rewrite for all writes in this same block to reduce number of branches because of offset
            #   * writes may sink into common successor (may be beneficial to do this before LLVM to simplify code in advance to improve debugability)
            for off, br in zip(possibleOffsets, offsetBranches):
                off: int
                br: SsaBasicBlock
                ssaBuilder.setInsertPoint(br, originalInsertPosition if br is write.block else None)

                inWordOffset = off % DATA_WIDTH
                srcOffset = 0
                end = off + width
                wordCnt = ceil(max(0, end - 1) / DATA_WIDTH)
                # slice input part form original write input and write it to wordTmp variable
                for last, wordI in iter_with_last(range(wordCnt)):
                    availableBits = width - srcOffset
                    bitsToTake = min(availableBits, DATA_WIDTH - inWordOffset)

                    _src = ssaBuilder.buildSliceConst(src, srcOffset + bitsToTake, srcOffset)
                    dataHi = inWordOffset + bitsToTake
                    if dataHi != DATA_WIDTH:
                        # pad with X to match DATA_WIDTH
                        _src = ssaBuilder.concat(_src, Bits(DATA_WIDTH - dataHi).from_py(None))

                    if inWordOffset != 0 or dataHi != DATA_WIDTH:
                        wordVarSlice = (SLICE.from_py(slice(DATA_WIDTH, inWordOffset, -1)),)
                        inWordOffset = 0
                    else:
                        wordVarSlice = ()

                    if wordI == 0 and off == 0 and ssaUtils.instrMeta[write].prevWordMayBePending:
                        # if there is complete word pending flush it because we just resolved the last flag (0)
                        _predWordPendingVar = ssaUtils.memUpdater.readVariable(predWordPendingVar, ssaBuilder.block)
                        sequelBlock = self._optionallyConsumePendingWord(
                            ssaUtils, predWordPendingVar, curWordVar, _predWordPendingVar, write)
                    # else it is guaranteed that there is "bitsToTake" bits in last word which we can fill

                    # fill current chunk to current word
                    ssaUtils._setWriteMask(curWordVar, off if wordI == 0 else 0, bitsToTake)
                    ssaUtils._setWriteData(curWordVar, wordVarSlice, _src)
                    if not last:
                        # write word somewhere in the middle of packet and in the middle of this chunk
                        ssaUtils._setWriteLast(curWordVar, 0)
                        ssaUtils._insertIntfWrite(curWordVar, write)
                        memUpdater.writeVariable(predWordPendingVar, (), ssaBuilder.block, BIT.from_py(0))
                    else:
                        meta: StreamChunkLastMeta = ssaUtils.instrMeta[write]
                        if meta.isLast is None:
                            # this word must be written once we resolve next successor because it is not
                            # possible to resolve last yet
                            if end % DATA_WIDTH == 0:
                                memUpdater.writeVariable(predWordPendingVar, (), ssaBuilder.block, BIT.from_py(1))

                        elif isinstance(meta.isLast, bool):
                            # it is possible to resolve last, so we can output word immediately
                            ssaUtils._setWriteLast(curWordVar, int(meta.isLast))
                            if meta.isLast or end % DATA_WIDTH == 0:
                                ssaUtils._insertIntfWrite(curWordVar, write)
                                memUpdater.writeVariable(predWordPendingVar, (), ssaBuilder.block, BIT.from_py(0))

                        else:
                            # the condition for EoF is known in advance, we can use it and output word inmmediately
                            ssaUtils._setWriteLast(curWordVar, meta.isLast)
                            if end % DATA_WIDTH == 0:
                                # if ending word always output word
                                ssaUtils._insertIntfWrite(curWordVar, write)
                                memUpdater.writeVariable(predWordPendingVar, (), ssaBuilder.block, BIT.from_py(0))
                            else:
                                # if not ending word output word only if isLast
                                self._optionallyConsumePendingWord(
                                    ssaUtils, predWordPendingVar, curWordVar, meta.isLast, write)

                    srcOffset += bitsToTake
                # write offset in a specific branch
                memUpdater.writeVariable(curOffsetVar, (), br, curOffsetVar._dtype.from_py(end % DATA_WIDTH))

        if write is None:
            sequelBlock = None
            sequelBlockPosition = 0
        elif sequelBlock is None or sequelBlock is write.block:
            sequelBlock = write.block
            sequelBlockPosition = write.block.body.index(write)
        else:
            sequelBlockPosition = 0

        if write is not None:
            write.block.body.remove(write)
            write.block = None

        return sequelBlock, sequelBlockPosition
