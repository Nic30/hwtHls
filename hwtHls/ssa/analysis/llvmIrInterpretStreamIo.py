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
    IsStreamTmpAllocaTmpSetterPlaceholder, MetadataToValueAsMetadata, MDNode, LoadInst, AllocaInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr, \
    LlvmIrInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter


class LlvmIrInterpretStreamIo():
    """
    :ivar _streamIoTmpWords: stream words which were not yet entirely written or read,
        the format of tuple corresponds to bus word format for specified stream interface. (e.g. data, strb, last for Axi4Stream),
        if interface has multiple segments a list of segment words is used instead just a single word
    """

    def __init__(self, interpret: "LlvmIrInterpret"):
        self.interpret = interpret
        self._streamIoTmpWords: dict[Argument, tuple[HBitsConst, ...] | list[tuple[HBitsConst, ...]] | None] = {}
        self._streamProps: dict[Argument, StreamChannelFormatInfo] = {}

    def _runLlvmIrFunctionInstrStreamRead(self, instr: CallInst, ioArg: Argument, w: int,
                                          behaviorType: StreamReadBehaviorType,
                                          streamProps: StreamChannelFormatInfo) -> None:
        # try return value from tmp word, else read from input until the required amount
        # of data is collected and then return it
        curTmp = self._streamIoTmpWords.get(ioArg, None)

        # variables for members of stream segment word
        data = None
        enable = None
        mask = None
        empty = None
        sof = None
        eof = None
        error = None

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

        if curTmp is not None:
            if bee == ByteEnableEncoding.BEE_MASK or bee == ByteEnableEncoding.BEE_NONE:
                # data, mask?, error?, sof?, eof?
                if not hasMask and not hasError and not hasSoF and not hasEoF:
                    data = curTmp
                else:
                    curTmpIt = iter(curTmp)
                    data = next(curTmpIt)
                    if hasMask:
                        mask = next(curTmpIt)
                    if hasError:
                        error = next(curTmpIt)
                    if hasSoF:
                        sof = next(curTmpIt)
                    if hasEoF:
                        eof = next(curTmpIt)
                    assert next(curTmpIt, None) is None, ("unexpected number of members in segment tuple", instr, curTmp)

            elif bee == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
                # data, enable, sof?, eof?, err?, empty?
                curTmpIt = iter(curTmp)
                data = next(curTmpIt)
                enable = next(curTmpIt)
                if hasSoF:
                    sof = next(curTmpIt)
                if hasEoF:
                    eof = next(curTmpIt)
                if hasError:
                    error = next(curTmpIt)
                if hasEmpty:
                    empty = next(curTmpIt)
                assert next(curTmpIt, None) is None, ("unexpected number of members in segment tuple", instr, curTmp)
            else:
                raise NotImplementedError(streamProps.byteEnableEncoding)

        byteWidth = streamProps.byteWidth
        dataWidth = streamProps.dataWidth
        ioSimStream = self.interpret.fnArgs[ioArg.getArgNo()]
        while data is None or data._dtype.bit_length() < w:
            try:
                streamWord = next(ioSimStream)  # :note: Function argumets are sorted, if this fails you may specified interpert args in wrong order
            except StopIteration:
                raise SimIoUnderflowErr()

            # parse members of stream word concatenated value
            assert isinstance(streamWord, HBitsConst), (instr, streamWord)
            newData = streamWord[dataWidth:]
            if hasMask:
                assert streamWord._dtype.bit_length() == streamProps.getWidthOfBusWord(), ("The stream word must have correct size",
                                                         instr, streamWord, streamProps.getWidthOfBusWord())
                off = streamProps.getOffsetOfMask()
                newMask = streamWord[off + streamProps.getWidthOfMask(): off]

            if hasEmpty:
                newEnable = streamWord[streamProps.getOffsetOfEnable()]
                if hasEmpty:
                    off = streamProps.getOffsetOfEmpty()
                    newEmpty = streamWord[off + streamProps.getWidthOfEmpty():off]

            if hasSoF:
                newSoF = streamWord[streamProps.getOffsetOfSoF()]
            if hasEoF:
                newEof = streamWord[streamProps.getOffsetOfEoF()]

            if data is None:
                # this is the first data chunk seen
                data = newData
                if hasMask:
                    mask = newMask
                if hasEnable:
                    enable = newEnable
                if hasEmpty:
                    empty = newEmpty
            else:
                # there is some data from previous word and merging is required
                data = Concat(newData, data)
                if hasMask:
                    mask = Concat(newMask, mask)
                if hasEnable:
                    enable = newEnable
                if hasEmpty:
                    newEmptyWidth = streamProps.getWidthOfEmptyForData(
                        data._dtype.bit_length(),
                        byteWidth,
                        supportZLP or isUnreliable)
                    empty = HBits(newEmptyWidth).from_py(int(empty) + int(newEmpty))

            if hasSoF:
                if sof is None:
                    sof = newSoF
                else:
                    assert not newSoF, "Frame can not have SoF in the middle of frame"

            if hasEoF:
                eof = newEof
                if eof is not None and eof:
                    break  # stream underflow or end in last word

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
                newEmptyWidth = streamProps.getWidthOfEmptyForData(w)
                empty = HBits(newEmptyWidth).from_py(int(empty) + padByteCnt)
        else:
            # the read ends somewhere in the middle of the stream word
            assert w % byteWidth == 0, (instr, w, byteWidth)

            if hasMask and eof & ~mask[w // byteWidth]:
                # the stream word does not contain any other valid bit, this is end of stream and remaining
                # data is discarded and any streamRead should check for eof to prevent reading further
                newTmpWord = None

            elif hasEmpty and eof & int(empty) >= ((actualWidth - w) // byteWidth):
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
                    newTmpWord.append(enable)
                    if hasSoF:
                        newTmpWord.append(sof)  # this is leftover and thus it can not contain first byte with sof
                    if hasEoF:
                        newTmpWord.append(eof)
                    if hasError:
                        newTmpWord.append(error)
                    if hasEmpty:
                        newEmptyWidth = streamProps.getWidthOfEmptyForData(w, byteWidth, supportZLP or isUnreliable)
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

        self._streamIoTmpWords[ioArg] = newTmpWord
        retValMembers = [data, ]
        if bee == ByteEnableEncoding.BEE_MASK or bee == ByteEnableEncoding.BEE_NONE:
            # data, mask?, error?, sof?, eof?
            if isUnreliable and hasMask:
                retValMembers.append(mask)
            if hasError:
                retValMembers.append(error)
            if hasSoF:
                retValMembers.append(sof)
            if hasEoF:
                retValMembers.append(eof)

        elif bee == ByteEnableEncoding.BEE_ENABLE_PLUS_EMPTY:
            # data, enable, sof?, eof?, err?, empty?
            if hasEnable:
                retValMembers.append(enable)
            if hasSoF:
                retValMembers.append(sof)
            if hasEoF:
                retValMembers.append(eof)
            if hasError:
                retValMembers.append(error)
            if isUnreliable and hasEmpty:
                retValMembers.append(empty)
        else:
            raise NotImplementedError(streamProps.byteEnableEncoding)

        # print("   StreamRead", instr, retValMembers)
        retVal = Concat(*reversed(retValMembers))
        assert retVal._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (instr, retVal, retValMembers)

        return retVal

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

    def _loadStreamChannelFormatInfo(self, ioArg: Argument) -> StreamChannelFormatInfo:
        streamInfo = self._streamProps.get(ioArg, None)
        if streamInfo is None:
            streamInfo = StreamChannelFormatInfo.findOptionalInMetadata(ioArg)
            assert streamInfo
            self._streamProps[ioArg] = streamInfo
        return streamInfo

    def _decodeLlvmIrFunctionInstrStreamIo(self, interpret: "LlvmIrInterpret", instr: CallInst) -> LlvmIrInstrFunction:
        ioArg: Argument = ValueToArgument(instr.getArgOperand(0))
        if IsStreamRead(instr):
            assert ioArg
            w: int = streamReadGetOrigChunkBitWidth(instr)
            behaviorType: StreamReadBehaviorType = streamReadGetBehavior(instr)
            streamProps: StreamChannelFormatInfo = self._loadStreamChannelFormatInfo(ioArg)
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
            self._loadStreamChannelFormatInfo(ioArg)

            def _intrinsic_StreamReadStartOfFrame(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                curTmp = self._streamIoTmpWords.get(ioArg, None)
                assert curTmp is None, ("There must be no leftover from previous frame because new frame was just started", instr, curTmp)

            return _intrinsic_StreamReadStartOfFrame

        elif IsStreamReadEndOfFrame(instr):
            assert ioArg

            def _intrinsic_StreamReadEndOfFrame(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                curTmp = self._streamIoTmpWords.pop(ioArg, None)
                streamProps: StreamChannelFormatInfo = self._streamProps[ioArg]
                if streamProps.byteEnableEncoding == ByteEnableEncoding.BEE_NONE:
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
