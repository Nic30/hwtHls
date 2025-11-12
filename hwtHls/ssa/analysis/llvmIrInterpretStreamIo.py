from collections import deque
from typing import Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import Concat
from hwt.hdl.commonConstants import b0
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import Argument, BasicBlock, ValueToConstantInt, ValueToInstruction, \
    Instruction, ValueToArgument, ValueToUndefValue, CallInst, IsStreamRead, \
    IsStreamReadStartOfFrame, IsStreamReadEndOfFrame, IsStreamWrite, IsStreamWriteStartOfFrame, \
    IsStreamWriteEndOfFrame, streamReadGetOrigChunkBitWidth, streamWriteGetOrigChunkBitWidth, \
    streamWriteGetWriteData, streamWriteGetWriteMaskOrEmpty, streamWriteGetWriteEoF, StreamChannelFormatInfo, \
    Value, ByteEnableEncoding, streamReadGetBehavior, streamWriteGetBehavior, StreamWriteBehaviorType, StreamReadBehaviorType, \
    IsStreamTmpAllocaTmpSetterPlaceholder, MetadataToValueAsMetadata, MDNode, LoadInst, AllocaInst, Function
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr, \
    LlvmIrInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter

StreamTmpWord_t = (
    tuple[HBitsConst, ...] |  # the case that the bus word is not segmented
    list[tuple[HBitsConst, ...]]  # the case that the bus word is segmented
)


class LlvmIrInterpretStreamIo():
    """
    :ivar _streamIoTmpWords: stream words which were not yet entirely written or read,
        the format of tuple corresponds to bus word format for specified stream interface. (e.g. data, strb, last for Axi4Stream),
        if interface has multiple segments a list of segment words is used instead just a single word
    """

    def __init__(self, interpret: "LlvmIrInterpret"):
        self.interpret = interpret
        self._streamIoTmpWords: dict[Argument, StreamTmpWord_t | None] = {}
        self._streamProps: dict[Argument, StreamChannelFormatInfo] = {}

    def _runLlvmIrFunctionInstrStreamRead_popSegment(self, instr: CallInst,
                                                     curTmpWord: Optional[StreamTmpWord_t],
                                                     ioSimStream: deque[HBitsConst],
                                                     streamProps: StreamChannelFormatInfo,
                                                     byteEnableEncoding: ByteEnableEncoding,
                                                     segmentCnt:int,
                                                     hasMask:bool,
                                                     hasEnable:bool,
                                                     hasEmpty:bool,
                                                     hasError:bool,
                                                     hasSoF:bool,
                                                     hasEoF:bool,
                                                     supportZLP:bool):
        OptionalBits_t = HBitsConst | None
        data: OptionalBits_t = None
        enable: OptionalBits_t = None
        mask: OptionalBits_t = None
        empty: OptionalBits_t = None
        sof: OptionalBits_t = None
        eof: OptionalBits_t = None
        error: OptionalBits_t = None
        if curTmpWord is not None:
            # return from curTmpWord first before loading any new segments
            if segmentCnt:
                assert isinstance(curTmpWord, list), (instr, curTmpWord)
                assert len(curTmpWord) <= segmentCnt, (instr, curTmpWord)
                curTmpSegmentWord = curTmpWord[0]
                if len(curTmpWord) == 1:
                    curTmpWord = None
                else:
                    curTmpWord = curTmpWord[1:]
            else:
                assert isinstance(curTmpWord, (tuple, HBits)), (instr, curTmpWord)
                curTmpSegmentWord = curTmpWord
                curTmpWord = None

            if byteEnableEncoding == ByteEnableEncoding.BEE_MASK or byteEnableEncoding == ByteEnableEncoding.BEE_NONE:
                # data, mask?, error?, sof?, eof?
                if not hasMask and not hasError and not hasSoF and not hasEoF:
                    data = curTmpSegmentWord
                else:
                    curTmpWordIt = iter(curTmpSegmentWord)
                    data = next(curTmpWordIt)
                    if hasMask:
                        mask = next(curTmpWordIt)
                        assert mask is not None, instr
                    if hasError:
                        error = next(curTmpWordIt)
                        assert error is not None, instr
                    if hasSoF:
                        sof = next(curTmpWordIt)
                        assert enable is not None, sof
                    if hasEoF:
                        eof = next(curTmpWordIt)
                        assert eof is not None, instr
                    assert next(curTmpWordIt, None) is None, ("unexpected number of members in segment tuple", instr, curTmpSegmentWord)
            elif byteEnableEncoding == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
                # data, enable?, sof?, eof?, err?, empty?
                curTmpWordIt = iter(curTmpSegmentWord)
                data = next(curTmpWordIt)
                if hasEnable:
                    enable = next(curTmpWordIt)
                    assert enable is not None, instr
                if hasSoF:
                    sof = next(curTmpWordIt)
                    assert enable is not None, sof
                if hasEoF:
                    eof = next(curTmpWordIt)
                    assert eof is not None, instr
                if hasError:
                    error = next(curTmpWordIt)
                    assert error is not None, instr
                if hasEmpty:
                    empty = next(curTmpWordIt)
                    assert empty is not None, instr

                assert next(curTmpWordIt, None) is None, ("unexpected number of members in segment tuple", instr, curTmpSegmentWord)
            else:
                raise NotImplementedError(byteEnableEncoding)
        else:
            # no data in tmp word, load new segment data from io
            try:
                # :note: Function argumets are sorted, if this fails you may specified interpert args in wrong order
                streamWord = next(ioSimStream)
            except StopIteration:
                raise SimIoUnderflowErr()

            # parse members of stream word concatenated value
            assert isinstance(streamWord, HBitsConst), (instr, streamWord)
            assert streamWord._dtype.bit_length() == streamProps.getWidthOfBusWord(), (instr, streamWord._dtype.bit_length(), streamProps.getWidthOfBusWord())
            if segmentCnt <= 1:
                leftoverSegments = None
            else:
                leftoverSegments = []

            dataWidth = streamProps.dataWidth
            # :note: reversed so the data from first segment will remain in variables for segment membes (data, sof, eof, mas, empty ...)
            for segmentI in reversed(range(max(segmentCnt, 1))):
                if segmentCnt == 0:
                    segmentI = None

                # data, enable?, sof?, eof?, err?, empty?  or
                # data{n}, (enable?, sof?, eof?, err?, empty?){n}
                data = streamWord[(segmentI + 1) * dataWidth:segmentI * dataWidth]
                if hasMask:
                    assert streamWord._dtype.bit_length() == streamProps.getWidthOfBusWord(), ("The stream word must have correct size",
                                                             instr, streamWord, streamProps.getWidthOfBusWord())
                    off = streamProps.getOffsetOfMask(segmentI)
                    mask = streamWord[off + streamProps.getWidthOfMask(): off]

                if hasEnable:
                    enable = streamWord[streamProps.getOffsetOfEnable(segmentI)]
                    assert enable._is_full_valid()

                if hasEmpty:
                    off = streamProps.getOffsetOfEmpty(segmentI)
                    empty = streamWord[off + streamProps.getWidthOfEmpty():off]

                if hasSoF:
                    sof = streamWord[streamProps.getOffsetOfSoF(segmentI)]
                if hasEoF:
                    eof = streamWord[streamProps.getOffsetOfEoF(segmentI)]

                if hasError:
                    error = streamWord[streamProps.getOffsetOfError(segmentI)]

                if segmentCnt > 1:
                    newTmpWord = [data, ]
                    if byteEnableEncoding == ByteEnableEncoding.BEE_MASK or byteEnableEncoding == ByteEnableEncoding.BEE_NONE:
                        # data, mask?, error?, sof?, eof?
                        if hasMask:
                            newTmpWord.append(mask)
                        if hasError:
                            newTmpWord.append(error)
                        if hasSoF:
                            newTmpWord.append(sof)
                        if hasEoF:
                            newTmpWord.append(eof)

                    elif byteEnableEncoding == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
                        # data, enable, sof?, eof?, err?, empty?
                        if hasEnable:
                            newTmpWord.append(enable)
                        if hasSoF:
                            newTmpWord.append(sof)
                        if hasEoF:
                            newTmpWord.append(eof)
                        if hasError:
                            newTmpWord.append(error)
                        if hasEmpty:
                            newTmpWord.append(empty)

                    else:
                        raise NotImplementedError(streamProps.byteEnableEncoding)
                    newTmpWord = tuple(newTmpWord)
                    leftoverSegments.append(newTmpWord)

            if segmentCnt > 1:
                assert len(leftoverSegments) == segmentCnt
                # restore values of the first segment
                leftoverSegments.pop()
                leftoverSegments.reverse()
            else:
                assert leftoverSegments is None
            curTmpWord = leftoverSegments

        return (curTmpWord, data, enable, mask, empty, sof, eof, error)

    def _runLlvmIrFunctionInstrStreamRead_buildReturnVal(self,
                                                         instr: CallInst,
                                                         bee: ByteEnableEncoding,
                                                         hasMask:bool,
                                                         hasEnable:bool,
                                                         hasEmpty:bool,
                                                         hasError:bool,
                                                         hasSoF:bool,
                                                         hasEoF:bool,
                                                         isUnreliable:bool,
                                                         data, mask, error, sof, eof, enable, empty):
        retValMembers = [data, ]
        if bee == ByteEnableEncoding.BEE_MASK or bee == ByteEnableEncoding.BEE_NONE:
            # data, mask?, error?, sof?, eof?
            if isUnreliable and hasMask:
                assert mask is not None, instr
                retValMembers.append(mask)
            if hasError:
                assert error is not None, instr
                retValMembers.append(error)
            if hasSoF:
                assert sof is not None, instr
                retValMembers.append(sof)
            if hasEoF:
                assert eof is not None, instr
                retValMembers.append(eof)

        elif bee == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
            # data, enable, sof?, eof?, err?, empty?
            if hasEnable:
                assert enable is not None, instr
                retValMembers.append(enable)
            if hasSoF:
                assert sof is not None, instr
                retValMembers.append(sof)
            if hasEoF:
                assert eof is not None, instr
                retValMembers.append(eof)
            if hasError:
                assert error is not None, instr
                retValMembers.append(error)
            if isUnreliable and hasEmpty:
                assert empty is not None, instr
                retValMembers.append(empty)
        else:
            raise NotImplementedError(bee.byteEnableEncoding)

        # print("   StreamRead", instr, retValMembers)
        retVal = Concat(*reversed(retValMembers))
        assert retVal._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (instr, retVal, retValMembers)

        return retVal

    def _runLlvmIrFunctionInstrStreamRead(self, instr: CallInst, ioArg: Argument, w: int,
                                          behaviorType: StreamReadBehaviorType,
                                          streamProps: StreamChannelFormatInfo) -> None:
        # try return value from tmp word, else read from input until the required amount
        # of data is collected and then return it

        # variables for members of stream segment word
        data: Optional[HBitsConst] = None
        enable: Optional[HBitsConst] = None
        mask: Optional[HBitsConst] = None
        empty: Optional[HBitsConst] = None
        sof: Optional[HBitsConst] = None
        eof: Optional[HBitsConst] = None
        error: Optional[HBitsConst] = None

        hasMask = streamProps.hasMask()
        hasEnable = streamProps.hasEnable()
        hasEmpty = streamProps.hasEmpty()
        hasError = streamProps.hasError()
        hasSoF = streamProps.hasSoF()
        hasEoF = streamProps.hasEoF()
        supportZLP = streamProps.supportZLP
        if streamProps.hasError():
            raise NotImplementedError(instr)
        bee = streamProps.byteEnableEncoding
        isUnreliable = behaviorType != StreamReadBehaviorType.RELIABLE
        if behaviorType == StreamReadBehaviorType.ALIGNING:
            raise NotImplementedError(str)

        segmentCnt = streamProps.segmentCnt
        byteWidth = streamProps.byteWidth
        ioSimStream = self.interpret.fnArgs[ioArg.getArgNo()]
        curTmpWord: Optional[StreamTmpWord_t] = self._streamIoTmpWords.get(ioArg, None)
        while data is None or data._dtype.bit_length() < w:
            # accumulate data until we have enough, more or eof
            (curTmpWord, newData, newEnable, newMask, newEmpty, newSof, newEof, newError) = \
                self._runLlvmIrFunctionInstrStreamRead_popSegment(
                    instr, curTmpWord, ioSimStream, streamProps, bee, segmentCnt,
                    hasMask, hasEnable, hasEmpty, hasError, hasSoF, hasEoF, supportZLP)
            if hasEnable:
                assert newEnable is not None, instr

            if data is None:
                # this is the first data chunk seen
                data = newData
                if hasMask:
                    mask = newMask
                if hasEnable:
                    if not bool(newEnable):
                        continue  # skip empty segments at beginning
                    enable = newEnable
                if hasEmpty:
                    empty = newEmpty
                if hasError:
                    error = newError
            else:
                # there is some data from previous word and merging is required
                data = Concat(newData, data)
                if hasMask:
                    mask = Concat(newMask, mask)
                if hasEnable:
                    assert bool(newEnable), ("no holes in frame alowed, but there is a dissabled segment inside of frame", instr)
                    enable = newEnable
                if hasEmpty:
                    newEmptyWidth = streamProps.getWidthOfEmptyForData(
                        data._dtype.bit_length(),
                        byteWidth,
                        supportZLP or isUnreliable)
                    empty = HBits(newEmptyWidth).from_py(int(empty) + int(newEmpty))
                if hasError:
                    error = error | newError
            if hasSoF:
                if sof is None:
                    sof = newSof
                else:
                    assert not newSof, "Frame can not have SoF in the middle of frame"

            if hasEoF:
                eof = newEof
                if eof is not None and (not hasEnable or newEnable) and eof:
                    break  # stream underflow or end in last word

        if hasEnable and enable is None:
            # all segments were empty
            raise SimIoUnderflowErr()

        if hasEmpty:
            newEmptyWidth = streamProps.getWidthOfEmptyForData(w, byteWidth, supportZLP or isUnreliable)
            if empty is not None and isUnreliable:
                empty = empty._zext(newEmptyWidth)

        # truncate data and optionaly store leftover to tmp word
        actualWidth = data._dtype.bit_length()
        if actualWidth == w:
            # stream read ends exactly at the end of stream word
            newTmpWord = None
        elif actualWidth < w:
            # stream underflow, pad return value
            newTmpWord = None
            assert eof, instr
            data = Concat(HBits(w - actualWidth).from_py(None), data)
            assert (w - actualWidth) % byteWidth == 0, (instr, w, actualWidth)
            padByteCnt = (w - actualWidth) // byteWidth
            if hasMask:
                mask = Concat(HBits(padByteCnt).from_py(0), mask)
            if hasEmpty:
                empty = HBits(newEmptyWidth).from_py(int(empty) + padByteCnt)
        else:
            # the read ends somewhere in the middle of the stream word
            assert w % byteWidth == 0, (instr, w, byteWidth)

            if hasMask and eof & ~mask[w // byteWidth]:
                # the stream word does not contain any other valid bit, this is end of stream and remaining
                # data is discarded and any streamRead should check for eof to prevent reading further
                newTmpWord = None

            elif hasEmpty and eof & (int(empty) >= ((actualWidth - w) // byteWidth)):
                # rest of the word is empty we can discard it
                newTmpWord = None
            else:
                # there is a leftover data in stream word, store if for later
                dataTmp = data[:w]
                newTmpWord = [dataTmp, ]
                if bee == ByteEnableEncoding.BEE_MASK or bee == ByteEnableEncoding.BEE_NONE:
                    # data, mask?, error?, sof?, eof?
                    if hasMask:
                        maskTmp = mask[:w // byteWidth]
                        newTmpWord.append(maskTmp)
                        # compute mask for remaining leftover data
                        mask = mask[w // byteWidth:]
                    if hasError:
                        newTmpWord.append(error)
                    if hasSoF:
                        newTmpWord.append(b0)  # this is leftover and thus it can not contain first byte with sof
                    if hasEoF:
                        newTmpWord.append(eof)
                    newTmpWord = tuple(newTmpWord)

                elif bee == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
                    # data, enable, sof?, eof?, err?, empty?
                    if hasEnable:
                        newTmpWord.append(enable)
                    if hasSoF:
                        newTmpWord.append(sof)  # this is leftover and thus it can not contain first byte with sof
                    if hasEoF:
                        newTmpWord.append(eof)
                    if hasError:
                        newTmpWord.append(error)
                    if hasEmpty:
                        leftoverByteCnt = (actualWidth - w) // byteWidth
                        empty = int(empty)
                        # compute new empty for remaining bytes
                        newEmptyLeftoverWidth = streamProps.getWidthOfEmptyForData(actualWidth - w, byteWidth, supportZLP or isUnreliable)
                        emptyLeftover = HBits(newEmptyLeftoverWidth).from_py(min(empty, leftoverByteCnt))
                        newTmpWord.append(emptyLeftover)
                        empty = HBits(newEmptyWidth).from_py(max(0, empty - leftoverByteCnt))

                    newTmpWord = tuple(newTmpWord)

                else:
                    raise NotImplementedError(streamProps.byteEnableEncoding)

                if hasEoF:
                    # this can not have eof set because we verified that there are
                    # some leftover bytes in this word
                    eof = b0

            data = data[w:]
            if hasMask:
                if mask._dtype.bit_length() == 1:
                    assert w == byteWidth
                else:
                    mask = mask[w // byteWidth:]

        if newTmpWord is not None:
            if segmentCnt != 0:
                if curTmpWord is None:
                    curTmpWord = [newTmpWord, ]
                else:
                    curTmpWord = [newTmpWord, *curTmpWord]
            else:
                assert curTmpWord is None, instr

        self._streamIoTmpWords[ioArg] = curTmpWord

        if not isUnreliable:
            mask = None
            enable = None
            empty = None
            hasMask = False
            hasEmpty = False
            hasEnable = False

        return self._runLlvmIrFunctionInstrStreamRead_buildReturnVal(
            instr, bee, hasMask, hasEnable, hasEmpty, hasError, hasSoF, hasEoF, isUnreliable,
            data, mask, error, sof, eof, enable, empty)

    def _decodeLlvmIrLoadOfSingleSegmentFromSegmentedBus(self, interpret: "LlvmIrInterpret", instr: LoadInst, ioArg: Argument, streamProps: StreamChannelFormatInfo):
        hasMask = streamProps.hasMask()
        hasEnable = streamProps.hasEnable()
        hasEmpty = streamProps.hasEmpty()
        hasError = streamProps.hasError()
        hasSoF = streamProps.hasSoF()
        hasEoF = streamProps.hasEoF()
        supportZLP = streamProps.supportZLP
        byteEnableEncoding: ByteEnableEncoding = streamProps.byteEnableEncoding
        segmentCnt:int = streamProps.segmentCnt

        ioSimStream = self.interpret.fnArgs[ioArg.getArgNo()]

        def _opcode_LoadOfSingleSegmentFromSegmentedBus(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            curTmpWord: Optional[StreamTmpWord_t] = self._streamIoTmpWords.get(ioArg, None)
            while True:
                (curTmpWord, newData, newEnable, newMask, newEmpty, newSof, newEof, newError) = \
                    self._runLlvmIrFunctionInstrStreamRead_popSegment(
                        instr, curTmpWord, ioSimStream, streamProps, byteEnableEncoding, segmentCnt,
                        hasMask, hasEnable, hasEmpty, hasError, hasSoF, hasEoF, supportZLP)
                if newEnable is None or bool(newEnable):
                    break
            self._streamIoTmpWords[ioArg] = curTmpWord
            isUnreliable = True
            v = self._runLlvmIrFunctionInstrStreamRead_buildReturnVal(
                instr, byteEnableEncoding, hasMask, hasEnable, hasEmpty, hasError, hasSoF, hasEoF, isUnreliable,
                newData, newMask, newError, newSof, newEof, newEnable, newEmpty)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, v)

        return _opcode_LoadOfSingleSegmentFromSegmentedBus

    @staticmethod
    def _streamIoInstrOpHBits(regs: dict[Instruction, HConst], v: Value):
        vAsConst = ValueToConstantInt(v)
        if vAsConst is not None:
            pyT = HBits(vAsConst.getType().getScalarSizeInBits())
            v = int(vAsConst.getValue())
            if v < 0:  # convert to unsigned
                v = pyT.all_mask() + v + 1
            v = pyT.from_py(v)
            return v

        vAsUndef = ValueToUndefValue(v)
        if vAsUndef is not None:
            pyT = HBits(vAsUndef.getType().getScalarSizeInBits())
            return pyT.from_py(None)

        vAsInstr = ValueToInstruction(v)
        if vAsInstr is not None:
            return regs[vAsInstr]

        raise ValueError(v)

    def _runLlvmIrFunctionInstrStreamWrite(self, regs: dict[Instruction, HConst],
                     instr: CallInst, ioArg: Argument, streamProps: StreamChannelFormatInfo,
                     wWidth: int, behaviorType: StreamWriteBehaviorType, ioSimStream: list) -> None:
        hasMask = streamProps.hasMask()
        if hasMask:
            if behaviorType == StreamWriteBehaviorType.ALLVALID:
                mask = HBits(wWidth // streamProps.byteWidth).getAllOnesValue()
            else:
                mask = self._streamIoInstrOpHBits(regs, streamWriteGetWriteMaskOrEmpty(instr))

        if streamProps.hasEnable():
            raise NotImplementedError(instr)
        if streamProps.hasEmpty():
            raise NotImplementedError(instr)

        curTmp = self._streamIoTmpWords.get(ioArg, None)
        data = self._streamIoInstrOpHBits(regs, streamWriteGetWriteData(instr))
        eof = self._streamIoInstrOpHBits(regs, streamWriteGetWriteEoF(instr))
        # print("streamWrite", instr, data, mask, eof)
        if curTmp is not None:
            data = Concat(data, curTmp[0])
            if hasMask:
                mask = Concat(mask, curTmp[1])

        dataWidth = streamProps.dataWidth
        byteWidth = streamProps.byteWidth
        if hasMask:
            maskWidth = dataWidth // byteWidth
        dataToWriteWidth = data._dtype.bit_length()
        dataLeftoverWidth = dataToWriteWidth % dataWidth
        fullWordCnt = dataToWriteWidth // dataWidth
        for isLastWord, wordI in iter_with_last(range(dataToWriteWidth // dataWidth)):
            # transmit complete bus words
            wordData = data[(wordI + 1) * dataWidth:wordI * dataWidth]
            if hasMask:
                if wordI == 0 and mask._dtype.bit_length() == 1:
                    assert maskWidth == 1
                    wordMask = mask
                else:
                    wordMask = mask[(wordI + 1) * maskWidth:wordI * maskWidth]
            wordEoF = eof if isLastWord and dataLeftoverWidth == 0 else b0
            if hasMask:
                word = Concat(wordEoF, wordMask, wordData)
            else:
                word = Concat(wordEoF, wordData)

            ioSimStream.append(word)

        if dataLeftoverWidth:
            if fullWordCnt > 0:
                data = data[:fullWordCnt * dataWidth]
                if hasMask:
                    mask = mask[:fullWordCnt * maskWidth]
            if eof:
                # add padding and transmit current data
                wordData = Concat(HBits(dataWidth - dataLeftoverWidth).from_py(None), data)
                assert (dataWidth - dataLeftoverWidth) % byteWidth == 0, (instr, dataWidth, dataLeftoverWidth)
                if hasMask:
                    wordMask = Concat(HBits((dataWidth - dataLeftoverWidth) // byteWidth).from_py(0), mask)
                    word = Concat(eof, wordMask, wordData)
                else:
                    word = Concat(eof, wordData)

                ioSimStream.append(word)
                newTmpWord = None
            else:
                # store pending data to tmpWord so it is merged with next write
                if hasMask:
                    newTmpWord = (data, mask)
                else:
                    newTmpWord = (data, None)

        else:
            newTmpWord = None
        # store leftover if any
        self._streamIoTmpWords[ioArg] = newTmpWord

    def _loadStreamChannelFormatInfo(self, F: Function) -> StreamChannelFormatInfo:
        for ioArg in F.args():
            streamInfo = StreamChannelFormatInfo.findOptionalInMetadata(ioArg)
            if streamInfo is not None:
                self._streamProps[ioArg] = streamInfo

    def _decodeLlvmIrFunctionInstrStreamIo(self, interpret: "LlvmIrInterpret", instr: CallInst) -> LlvmIrInstrFunction:
        ioArg: Argument = ValueToArgument(instr.getArgOperand(0))
        if IsStreamRead(instr):
            assert ioArg
            w: int = streamReadGetOrigChunkBitWidth(instr)
            behaviorType: StreamReadBehaviorType = streamReadGetBehavior(instr)
            streamProps: StreamChannelFormatInfo = self._streamProps.get(ioArg)
            assert streamProps is not None, ("StreamChannelFormatInfo should have been discovered by previous StreamReadStartOfFrame", instr)

            def _intrinsic_StreamRead(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                v = self._runLlvmIrFunctionInstrStreamRead(instr, ioArg, w, behaviorType, streamProps)
                interpret._storeInstrResult(waveLog, nowTime, regs, instr, v)

            return _intrinsic_StreamRead

        elif IsStreamWrite(instr):
            assert ioArg
            streamProps: StreamChannelFormatInfo = self._streamProps.get(ioArg)
            assert streamProps is not None, ("StreamChannelFormatInfo should have been discovered by previous StreamWriteStartOfFrame", instr)
            ioSimStream = self.interpret.fnArgs[ioArg.getArgNo()]
            wWidth = streamWriteGetOrigChunkBitWidth(instr)
            behaviorType = streamWriteGetBehavior(instr)

            def _intrinsic_StreamWrite(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                self._runLlvmIrFunctionInstrStreamWrite(regs, instr, ioArg, streamProps, wWidth, behaviorType, ioSimStream)

            return _intrinsic_StreamWrite

        elif IsStreamReadStartOfFrame(instr) or IsStreamWriteStartOfFrame(instr):
            assert ioArg
            streamProps: StreamChannelFormatInfo = self._streamProps[ioArg]

            def _intrinsic_StreamReadStartOfFrame(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                if streamProps.segmentCnt <= 1:
                    curTmp = self._streamIoTmpWords.get(ioArg, None)
                    assert curTmp is None, ("There must be no leftover from previous frame because new frame was just started", instr, curTmp)

            return _intrinsic_StreamReadStartOfFrame

        elif IsStreamReadEndOfFrame(instr):
            assert ioArg
            streamProps: StreamChannelFormatInfo = self._streamProps[ioArg]

            def _intrinsic_StreamReadEndOfFrame(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                curTmp = self._streamIoTmpWords.get(ioArg, None)
                if streamProps.byteEnableEncoding == ByteEnableEncoding.BEE_NONE:
                    if curTmp is not None:
                        self._streamIoTmpWords.pop(ioArg)
                elif streamProps.segmentCnt > 1:
                    pass
                else:
                    assert curTmp is None, ("The frame does not end when expected", instr, curTmp)

            return _intrinsic_StreamReadEndOfFrame

        elif IsStreamWriteEndOfFrame(instr):
            assert ioArg

            def _intrinsic_StreamWriteEndOfFrame(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                curTmp = self._streamIoTmpWords.pop(ioArg, None)
                assert curTmp is None, ("There was no write with EoF when EoF was expected", instr, curTmp)

            return _intrinsic_StreamWriteEndOfFrame

        elif IsStreamTmpAllocaTmpSetterPlaceholder(instr):
            # assert ioArg

            def _intrinsic_StreamTmpAllocaTmpSetterPlaceholder(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                pass

            return _intrinsic_StreamTmpAllocaTmpSetterPlaceholder

        else:
            raise NotImplementedError("Unknown streamIO intrinsic", instr)

    def _decodeLoadFromStreamTmpVar_offset(self, instr: LoadInst, srcAlloca: AllocaInst, streamOffsetMd: MDNode):
        assert streamOffsetMd.getNumOperands() == 1, streamOffsetMd
        ioIdMd = streamOffsetMd.getOperand(0).get()
        ioIdV = MetadataToValueAsMetadata(ioIdMd).getValue()
        ioId = ValueToConstantInt(ioIdV).getValue().getZExtValue()
        ioArg = self.interpret.F.getArg(ioId)
        interpret = self.interpret
        resT = HBits(instr.getType().getIntegerBitWidth())
        DW = self._streamProps[ioArg].dataWidth

        def _opcode_LoadInst_streamTmpVar_offset(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            tmpWord = self._streamIoTmpWords.get(ioArg, None)
            if tmpWord is None:
                res = 0
            else:
                res = DW - tmpWord[0]._dtype.bit_length()
                assert res >= 0, (DW, tmpWord)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, resT.from_py(res))

        return _opcode_LoadInst_streamTmpVar_offset
