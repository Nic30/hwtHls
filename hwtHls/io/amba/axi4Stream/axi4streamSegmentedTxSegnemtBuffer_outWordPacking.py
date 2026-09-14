#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.code import shlArray, lshrArray
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.pragmaInstruction import setHasNoUnsignedWrap
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBufferCommon import Axi4streamSegmentedTxSegnemtBufferCommon
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_inWordPacking import Axi4streamSegmentedTxSegnemtBuffer_inWordPacking, \
    Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented, \
    Axi4StreamSegmentedMockSegmentTy, Axi4StreamSegmentedMockWordNoPackTy
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


class Axi4streamSegmentedTxSegnemtBuffer_outWordPacking(Axi4streamSegmentedTxSegnemtBufferCommon):
    """
    This component takes array of segments for Axi4StreamSegmented interface which is packed
    so all valid segments are on lowest indexes, then with the help of internal buffer it
    puts the data on output interface so the frame continuity is asserted and the data segments
    are tightly packed if data available.
    """
    
    @override
    def hwDeclr(self) -> None:
        assert self.MIN_SEGMENTS_PER_LANE >= 0, self.MIN_SEGMENTS_PER_LANE
        assert self.MIN_SEGMENTS_PER_LANE <= self.MAX_SEGMENTS_PER_LANE, (self.MIN_SEGMENTS_PER_LANE, self.MAX_SEGMENTS_PER_LANE)
        addClkRstn(self)

        self.dataIn = HwIOStructRdVld()
        self.dataIn.T = self.getPackedWordTy()

        with self._hwParamsShared():
            self.dataOut: Axi4StreamSegmented = Axi4StreamSegmented()._m()

    @property
    def IN_SEGMENT_CNT(self):
        return self.SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE

    def _modelFormatSegmentsToAxi4SSFormat(self, segments: list[Axi4StreamSegmentedMockSegmentTy]):
        SEGMENT_CNT = self.SEGMENT_CNT
        outT = self.getAxi4SSWordTy()
        if len(segments) < SEGMENT_CNT:
            self.getPackedWordTy()
            Axi4streamSegmentedTxSegnemtBuffer_inWordPacking._modelAddPaddingSegments(
                segments, SEGMENT_CNT, segmentT=self.getSegmentTy())

        w = {
            "data": [seg.data for seg in segments],
        }

        if SEGMENT_CNT == 1:
            user = segments[0].user
            user = [{f.name: getattr(user, f.name)  for f in user._dtype.fields if f.name != "enable"}]
        else:
            user = [seg.user for seg in segments]
                
        w["user"] = user
        return outT.from_py(w)
    
    @hlsModelProps(returnsPyValue=False, returnsOutValue=False, inputArgsAreStructMembers=False)
    def model(self, dataIn: list, dataOut: list[Axi4StreamSegmentedMockWordNoPackTy]):
        SEGMENT_CNT = self.SEGMENT_CNT
        IN_SEGMENT_CNT = SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE
        buff: list[Axi4StreamSegmentedMockSegmentTy] = []  # list of valid segments
        # frameEndsWithEoF = 0
        segmentsEndingWithEoFCnt = 0
        for inWord in dataIn:
            assert len(inWord.segments) == IN_SEGMENT_CNT, (len(inWord.segments), SEGMENT_CNT, self.MAX_SEGMENTS_PER_LANE)
            while len(buff) >= SEGMENT_CNT or segmentsEndingWithEoFCnt != 0:  # frameEndsWithEoF & 1
                if len(buff) >= SEGMENT_CNT:
                    segmentsToConsumeCnt = SEGMENT_CNT
                else:
                    # segmentsToConsumeCnt = cttoInt(frameEndsWithEoF)
                    segmentsToConsumeCnt = segmentsEndingWithEoFCnt

                outWord = self._modelFormatSegmentsToAxi4SSFormat(buff[:segmentsToConsumeCnt])
                dataOut.append(outWord)

                buff = buff[segmentsToConsumeCnt:]
                # frameEndsWithEoF >>= SEGMENT_CNT
                segmentsEndingWithEoFCnt = max(0, segmentsEndingWithEoFCnt - segmentsToConsumeCnt)

            # append valid items to buffer
            segmentsValidCnt = inWord.segmentsValidCnt
            # _frameEndsWithEoF = inWord["frameEndsWithEoF"]
            _segmentsEndingWithEoFCnt = int(inWord.segmentsEndingWithEoFCnt)

            lastEoFindex = -1
            for i, seg in enumerate(reversed(inWord.segments)):
                u = seg.user
                if u.enable and u.eof:
                    lastEoFindex = len(inWord.segments) - i - 1
                    break
            # assert _frameEndsWithEoF == 0 if lastEoFindex < 0 else mask(lastEoFindex + 1), (_frameEndsWithEoF, lastEoFindex)
            assert _segmentsEndingWithEoFCnt == 0 if lastEoFindex < 0 else lastEoFindex + 1, (_segmentsEndingWithEoFCnt, lastEoFindex)
            # frameEndsWithEoF |= int(_frameEndsWithEoF) << len(buff)
            if _segmentsEndingWithEoFCnt:
                segmentsEndingWithEoFCnt = len(buff) + _segmentsEndingWithEoFCnt

            buff.extend(inWord.segments[:segmentsValidCnt])

        assert segmentsEndingWithEoFCnt == len(buff), "check that there is no unfinished frame"
        outT = self.getAxi4SSWordTy().from_py
        while buff:
            segmentsToConsumeCnt = min(len(buff), SEGMENT_CNT)
            outWord = self._modelFormatSegmentsToAxi4SSFormat(buff[:segmentsToConsumeCnt])
            dataOut.append(outWord)
            buff = buff[segmentsToConsumeCnt:]

    @hlsBytecode
    def produceOutWord(self, buffer: list[HStruct], writeOutEnMask: list[AnyHBitsValue], dataOut: IoProxyScalar):
        """
        Reorder bits to Axi4SS format, apply segment enable mask and write data to output
        """
        PyBytecodeBlockLabel(f"bb.produce.anyValid")
        outWord = self.getAxi4SSWordTy().from_py(None)
        for i, (en, b) in enumerate(zip(writeOutEnMask, buffer)):
            PyBytecodeBlockLabel(f"bb.produce.buff{i:d}")
            outWord.data[i] = b.data
            if self.SEGMENT_CNT == 1:
                # the enable is not present in this case
                outWord.user[i](b.user, exclude=(b.user.enable,))
            else:
                outWord.user[i] = b.user
                outWord.user[i].enable &= en
            # do not output the segments which are part of frame which does not end with eof or at the end of the word
            # it needs to wait until the rest of the data arrives
            del b
            del en

        PyBytecodeBlockLabel("bb.preduce.storeOut")
        dataOut.write(outWord, mayBecomeFlushable=False)
        del outWord

    @hlsBytecode
    def shiftOutConsummedSegments(self, leftoverBuff: list[Axi4StreamSegmentedMockSegmentTy], itemReadyToBeConsummedCnt: AnyHBitsValue):
        setBuffItem = self.setBuffItem
        SEGMENT_CNT = self.dataOut.SEGMENT_CNT
        # BUFF_SIZE = len(leftoverBuff)
        # IN_SEGMENT_T = self.getSegmentTy()
        # IN_SEGMENT_T_INVALID = IN_SEGMENT_T.from_py({'user': {'enable': 0}})
        # if itemReadyToBeConsummedCnt > SEGMENT_CNT:
        #    PyBytecodeBlockLabel("bb.shiftOutConsummedSegments.fullWord")
        #    # constant shift for SEGMENT_CNT valid
        #    for i, b in enumerate(leftoverBuff):
        #        PyBytecodeBlockLabel(f"bb.shiftOutConsummedSegments.fullWord.sh{i:d}")
        #        newB = leftoverBuff[i + SEGMENT_CNT] if i + SEGMENT_CNT < BUFF_SIZE else IN_SEGMENT_T_INVALID
        #        setBuffItem(newB, b)
        #        del newB
        #        del b
        #
        # else:
        # shift begin, mark rest invalid
        PyBytecodeBlockLabel("bb.shiftOutConsummedSegments.lessThanWord")
        beginOfLeftoverBuffShifted: list[Axi4StreamSegmentedMockSegmentTy] = HwIOArray(
            shlArray(leftoverBuff[:SEGMENT_CNT],
                     itemReadyToBeConsummedCnt._trunc(log2ceil(SEGMENT_CNT + 1))))

        # copy new data into leftoverBuff on index SEGMENT_CNT and after
        for i in range(SEGMENT_CNT):
            PyBytecodeBlockLabel(f"bb.shiftOutConsummedSegments.lessThanWord.cp{i:d}")
            setBuffItem(beginOfLeftoverBuffShifted[i], i, leftoverBuff)

        del beginOfLeftoverBuffShifted

        # set last SEGMENT_CNT items in leftoverBuff to disabled
        for i, b in enumerate(leftoverBuff[:-SEGMENT_CNT]):
            PyBytecodeBlockLabel(f"bb.shiftOutConsummedSegments.lessThanWord.del{i+SEGMENT_CNT:d}")
            b.user.enable = b0
            del b
        # :note: it does not matter if itemReadyToBeConsummedCnt < SEGMENT_CNT, because in that case the segment is already disabled
        #        because there must be < SEGMENT_CNT items in total

    # @hlsBytecode
    # def loadPackedWord(self, outWordIoIn: IoProxyScalar,
    #                    loadEn: AnyHBitsValue) -> HwIOArray[HStruct]:
    #    # create a tmp arrays for newly read word and initialize it
    #    newData = outWordIoIn.interface.T.from_py({
    #        "segmentsValidCnt": 0,
    #        "segments": [{"user": {"enable": 0}} for _ in range(self.IN_SEGMENT_CNT)],
    #        "frameEndsWithEoF": 0})
    #    # newData.frameEndsOnWordBoundary = 0
    #    # for d in newData.segments:
    #    #    d.user.enable = b0
    #    #    del d
    #    if loadEn:
    #        # :note: must use non-blocking read to flush leftover buffer
    #        newDataTmp = outWordIoIn.read(blocking=False)
    #        if newDataTmp.valid:
    #            # :note: this is necessary because all data (including enable flag) are undefined if valid=false
    #            newData = newDataTmp.data
    #
    #    return newData
    #
    @hlsBytecode
    def thread_forwardPackedWords(self, hls: HlsScope, outWordIoIn: IoProxyScalar, dataOut: IoProxyScalar):
        """
        ############################ variant 1 with the output word connected only to buffer begin ###########
        The incoming data from outWordIoIn is guaranteed to be packed left (to index 0)
        But there is still a possibility that unfinished frame which can not complete bus word appear
        and we have to wait until rest of the frame data to finish the out word.
        
        Essential requrements:
        * there must be only 1 shifter for input data only
        * there must be only 1 shifter for buffer only for first SEGMENT_CNT items
        * the update of sizes (e.g. segmentsValidCnt) must not be driven from the main shifters (because of long latency) 
        
        There are mulitple possibilities for leftover buffer behavior
        1. there is >= SEGMENT_CNT items and SEGMENT_CNT was conssumed
        2. there is <  SEGMENT_CNT items and all are consumed (same case as 1.)
        3. there is <  SEGMENT_CNT items and it ends with unfinished frame
                       in this case we have to output complete frames and latch the last one which is incomplete
                       this means that there may be  SEGMENT_CNT-1 items which need to wait
        
        * the data for output are taken only from first items of the buffer
        * the input data is only appended to a buffer (from 0 to SEGMENT_CNT-1-1 index)
        ==> the new data should be loaded if there was < 2*SEGMENT_CNT items in the buffer
       
        To assert full troughput we need to accomondate
        * 1x all inputs (SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE)
        * the leftover from previous word which can be SEGMENT_CNT-1 in size
        """
        SEGMENT_CNT = self.dataOut.SEGMENT_CNT
        IN_SEGMENT_T: HStruct = self.getSegmentTy()
        IN_SEGMENT_CNT = self.IN_SEGMENT_CNT
        BUFF_SIZE = IN_SEGMENT_CNT + SEGMENT_CNT - 1  # self.MAX_LATCHED_SEGMENTS
        inWordSizeT = HBits(log2ceil(IN_SEGMENT_CNT + 1))
        buffSizeWidth = log2ceil(BUFF_SIZE + 1)
        buffSizeT = HBits(buffSizeWidth)
        wordSizeT = HBits(log2ceil(SEGMENT_CNT + 1))
        # buffMaskT = HBits(BUFF_SIZE)

        leftoverBuff: list[Axi4StreamSegmentedMockSegmentTy] = [hls.var(f"leftoverBuff{i:d}", IN_SEGMENT_T) for i in range(BUFF_SIZE)]
        segmentsValidCnt = buffSizeT.from_py(0)
        itemsEndingWithEoFCnt = buffSizeT.from_py(0)
        # segmentsValidCntNext = buffSizeT.from_py(0)
        itemReadyToBeConsummedCnt = wordSizeT.from_py(0)  # segmentsValidCnt - count of segmets without eof
        # which must wait because there is not enough data to produce out word

        # segmentsRequiredForLastNonEoFEndingFrame = buffSizeT.from_py(BUFF_SIZE)
        # frameEndsOnWordBoundary = buffMaskT.from_py(0)
        # frameEndsWithEoF = buffMaskT.from_py(0)
        # leftoverItemCnt = HBits(log2ceil(IN_SEGMENT_CNT + 1)).from_py(0)

        # reset
        for b in leftoverBuff:
            b.user.enable = b0
            del b

        while b1:
            PyBytecodeBlockLabel(f"bb.forwardLoop")
            storeOutEn = itemReadyToBeConsummedCnt != 0
            if storeOutEn:
                PyBytecodeBlockLabel(f"bb.forwardLoop.out")
                # output word if:
                #  * the leftover had a data (and new data completes potentially unfinished frame or word)
                #  * or the the leftover has at least some frame with EoF or enough data to fill the word
                outSegmentEnMask = [(itemReadyToBeConsummedCnt >= i) for i in range(SEGMENT_CNT)]
                PyBytecodeInline(self.produceOutWord)(leftoverBuff[:SEGMENT_CNT], outSegmentEnMask, dataOut)
                PyBytecodeBlockLabel("bb.consumedShiftOut")
                PyBytecodeInline(self.shiftOutConsummedSegments)(leftoverBuff, itemReadyToBeConsummedCnt)

            PyBytecodeBlockLabel("bb.inLoad")
            # :note: now leftoverBuff has consumed items shifted out and begins with only valid items
            # :attention: segmentsValidCnt, itemReadyToBeConsummedCnt, frameEndsWithEoF is not updated yet
            loadEn = segmentsValidCnt <= (2 * SEGMENT_CNT - 1)
            # :note: underflow is not important because if the segmentsValidCnt > SEGMENT_CNT it is not used
            segmentsValidCntFromLeftover = setHasNoUnsignedWrap(segmentsValidCnt - itemReadyToBeConsummedCnt._zext(buffSizeWidth))
            segmentsValidCntFromLeftoverForSh = segmentsValidCntFromLeftover._trunc(log2ceil(SEGMENT_CNT))._zext(buffSizeWidth)
            itemReadyToBeConsummedCntAsBuffSize = itemReadyToBeConsummedCnt._zext(buffSizeWidth)
            if itemsEndingWithEoFCnt < itemReadyToBeConsummedCntAsBuffSize:
                itemsEndingWithEoFCnt = buffSizeT.from_py(0)
            else:
                itemsEndingWithEoFCnt -= itemReadyToBeConsummedCntAsBuffSize
            # segmentsValidCnt = segmentsValidCntNext
            # frameEndsWithEoF >>= segmentsValidCntFromLeftoverForSh

            # load new data and merge it with leftover buffer
            # :attention: if not hasAtLeastWordOfData this results in nop
            newDataValidItemCnt = inWordSizeT.from_py(0)
            newSegmentsEndingWithEoFCnt = inWordSizeT.from_py(None)
            newEoFInRead = b0
            # newData = PyBytecodeInline(self.loadPackedWord)(outWordIoIn, loadEn)
            if loadEn:
                newDataTmp = outWordIoIn.read(blocking=False)
                newData: Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy = newDataTmp.data
                if newDataTmp.valid:
                    PyBytecodeBlockLabel("bb.inLoadMerge")
                    # _newDataFrameEndsWithEoF = newData.frameEndsWithEoF
                    # newDataframeEndsWithEoF = _newDataFrameEndsWithEoF._zext(BUFF_SIZE)
                    # newDataframeEndsWithEoFAlignedToLeftoverEnd = newDataframeEndsWithEoF << segmentsValidCntFromLeftoverForSh
                    # del newDataframeEndsWithEoF
                    IN_SEGMENT_T_INVALID = IN_SEGMENT_T.from_py({'user': {'enable': 0}})
                    newDataPlusPadding = newData.segments + [IN_SEGMENT_T_INVALID for _ in range(SEGMENT_CNT - 1)]
                    # align new data to end of lefover by shift to right
                    newDataAlignedToLeftoverEnd = HwIOArray(lshrArray(newDataPlusPadding, segmentsValidCntFromLeftoverForSh))
                    del newDataPlusPadding
                    # frameEndsWithEoF |= newDataframeEndsWithEoFAlignedToLeftoverEnd
                    # del newDataframeEndsWithEoFAlignedToLeftoverEnd

                    # copy new segments to buffer (append after current data, consumed items are already shifted out and remaining data is packed beggining from index 0)
                    setBuffItem = self.setBuffItem
                    for i, newSegment in enumerate(newDataAlignedToLeftoverEnd):
                        if newDataTmp.valid & (buffSizeT.from_py(i) >= segmentsValidCntFromLeftover):
                            PyBytecodeBlockLabel(f"bb.inLoadMerge.store{i:d}")
                            setBuffItem(newSegment, i, leftoverBuff)
                        del newSegment

                    del newDataAlignedToLeftoverEnd
                    newDataValidItemCnt = newData.segmentsValidCnt
                    # newReadyItems = ctto(newData.frameEndsWithEoF[SEGMENT_CNT:])
                    newSegmentsEndingWithEoFCnt = newData.segmentsEndingWithEoFCnt
                    # newEoFInRead = _newDataFrameEndsWithEoF != 0
                    newEoFInRead = newData.segmentsEndingWithEoFCnt != 0

                del newData
                del newDataTmp

            # :note: main goal there is to compute update of all state variables with the most simple
            #        expression, because this is a critical section and all variables are requred in next iteration
            #        the latency of this loop limits F_max
            PyBytecodeBlockLabel("bb.finalize")
            segmentsValidCnt = setHasNoUnsignedWrap(segmentsValidCntFromLeftover + newDataValidItemCnt._zext(buffSizeWidth))
            del newDataValidItemCnt

            if segmentsValidCnt >= SEGMENT_CNT:
                # if there is (leftover + new) more than word of data we will produce full word
                itemReadyToBeConsummedCnt = wordSizeT.from_py(SEGMENT_CNT)
            elif ~newEoFInRead & storeOutEn:
                # if there is not any eof in the new data
                # all items which can be consumed are consumed
                # now there may be only <SEGMENT_CNT segments without eof and we can not produce any output word
                itemReadyToBeConsummedCnt = wordSizeT.from_py(0)
            elif newEoFInRead:
                # < SEGMENT_CNT in total and there is EoF in new data
                itemReadyToBeConsummedCnt = segmentsValidCntFromLeftover._trunc(wordSizeT.bit_length()) + \
                                            newSegmentsEndingWithEoFCnt._trunc(wordSizeT.bit_length())
                # :note: segmentsValidCntFromLeftover known to be < SEGMENT_CNT
            else:
                # cover the case of <SEGMENT_CNT potintial items with eof and without eof and the end
                itemReadyToBeConsummedCnt = itemsEndingWithEoFCnt._trunc(wordSizeT.bit_length())

            del segmentsValidCntFromLeftover
            del newEoFInRead
            del newSegmentsEndingWithEoFCnt

            # if segmentsValidCnt >= SEGMENT_CNT:
            #     # if there is (leftover + new) more than word of data we will produce full word
            #     itemReadyToBeConsummedCnt = wordSizeT.from_py(SEGMENT_CNT)
            # elif _newDataFrameEndsWithEoF._eq(0) & storeOutEn:
            #     # if there is not any eof in the new data
            #     # all items which can be consumed are consumed
            #     # now there may be only <SEGMENT_CNT segments without eof and we can not produce any output word
            #     itemReadyToBeConsummedCnt = wordSizeT.from_py(0)
            # else:
            #     # < SEGMENT_CNT in total and there is EoF in new data
            #     itemReadyToBeConsummedCnt = hwMin(
            #         # :note: segmentsValidCntFromLeftover known to be < SEGMENT_CNT
            #         segmentsValidCntFromLeftover._trunc(wordSizeT.bit_length()) + newReadyItems,
            #         wordSizeT.from_py(SEGMENT_CNT)._unsigned(),
            #     )

            # segmetsEndingWithEoF = ctto(frameEndsWithEoF[SEGMENT_CNT:])._zext(buffSizeWidth)
            # itemReadyToBeConsummedCnt = (segmentsValidCnt >= SEGMENT_CNT)._ternary(
            #    buffSizeT.from_py(SEGMENT_CNT),
            #    # [todo] frameEndsWithEoF and newDataframeEndsWithEoFAlignedToLeftoverEnd go trough many shifts which reduces f_max
            #    segmetsEndingWithEoF)
            # segmentsValidCntNext = segmentsValidCnt - itemReadyToBeConsummedCnt

            # totalCompleteItemCnt = subSat0(totalItemCnt, fitTo_t(newData.segmentsRequiredForLastNonEoFEndingFrame, buffSizeT))
            # the enable must be masked to ban assert correct frame continuity
            # * enable if frame ends with eof or on new out word boundary
            # outSegmentEnMask = [
            #    (frameEndsWithEoF[i] |  # for items from leftover buffer
            #     (newDataValidItemCnt >= segmentsRequiredForLastNonEoFEndingFrame) |  # current word is completed with new data from input
            #     # [todo] check if the underflow can break the things
            #     (totalCompleteItemCnt > i)  # this segment of new data ends with eof
            #     )  # for new items
            #     for i in range(SEGMENT_CNT)]
            #
            # hasDataForOut = outSegmentEnMask[0] & ((segmentsValidCnt != 0) | newData.segmentsValidCnt != 0)
            # update tmp variables for next iteration
            # segmentsValidCnt = subSat0(totalItemCnt, totalItemCnt._dtype.from_py(SEGMENT_CNT))
            # segmentsRequiredForLastNonEoFEndingFrame =
            # frameEndsWithEoF =

            # frameNotEndingPrematurely = frameEndsOnWordBoundary | frameEndsWithEoF
            # PyBytecodeInline(self.produceOutWord)(hls, IN_SEGMENT_T, buffForOutput, frameNotEndingPrematurely)
            # shift the new data at the end of the current leftover
            # consumedItemsCnt = hwMin(cttz(~frameNotEndingPrematurely), SEGMENT_CNT)

            # if hasDataForOut:
            #    # if the leftover data is valid use it else use data from newDataAlignedToLeftoverEnd
            #    leftoverForOut = leftoverBuff[:SEGMENT_CNT]
            #    newDataAlignedToLeftoverEndForOut = newDataAlignedToLeftoverEnd[:SEGMENT_CNT]
            #
            #    # construct mux which will select between newData and leftover
            #    outWordSegments = []
            #    for leftoverSeg, newSeg in zip(leftoverForOut, newDataAlignedToLeftoverEndForOut):
            #        outSeg = leftoverSeg.user.enable._ternary(leftoverSeg, newSeg)
            #        outWordSegments.append(outSeg)
            #        del outSeg
            #        del leftoverSeg
            #        del newSeg
            #
            #
            # raise NotImplementedError("[todo] update leftover")

    def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy):
        """
        discard ordering between read nodes and the write (between all of them pairwise)
        """
        netlist = thread.netlist
        for rwNode in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            # if isinstance(rwNode, HlsNetNodeWrite) and rwNode.dst is self.dataOut:
            #    pass
            # elif isinstance(rwNode, HlsNetNodeRead) and rwNode.src in self.dataIn:
            #    pass
            # else:
            #    continue
            if not  isinstance(rwNode, (HlsNetNodeRead, HlsNetNodeWrite)):
                continue
            netlistExplicitSyncDisconnectFromOrderingChain(DebugTracer(None), rwNode, None,
                                                           disconnectPredecessors=True,
                                                           disconnectSuccesors=True)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        t0 = HlsThreadFromPy(hls, self.thread_forwardPackedWords, hls,
                             IoProxyScalar(hls, self.dataIn),
                             IoProxyScalar(hls, self.dataOut))
        t0.netlistCallbacks.append(self.reduceOrdering)
        hls.addThread(t0)
        hls.compile()


if __name__ == "__main__":
    import sys
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtBuildsystem.vivado.part import XilinxPart
    from hwtHls.platform.xilinx.fromVitisDB import HlsPlatformFromVitisDB
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    
    sys.setrecursionlimit(int(1e6))
    m = Axi4streamSegmentedTxSegnemtBuffer_outWordPacking()
    m.SEGMENT_CNT = 1
    m.SEGMENT_DATA_WIDTH = 128
    m.CLK_FREQ = int(1.0e6)
    # m.CLK_FREQ = int(250.0e6)
    # m.CLK_FREQ = int(390.625e6)
    m.USE_SOF = True
    m.MAX_SEGMENTS_PER_LANE = 2
    m.MIN_SEGMENTS_PER_LANE = 0

#    p = XilinxPart
#    part = XilinxPart(
#        p.Family.versalHbm,
#        p.Size._1542,
#        p.Package.lsva4737,
#        p.Speedgrade._1LP
##        p.Speedgrade._3HP
#        )
#
#    targetPlatform = HlsPlatformFromVitisDB.getForPart(part,
#        # targetPlatform = VirtualHlsPlatform(
#        llvmCliArgs=[
#            # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
#        #    LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
#        ],
#        debugFilter=HlsDebugBundle.ALL_RELIABLE
#    )
    targetPlatform = Artix7Fast()
    # SEGMENT_CNT = 16, SEGMENT_DATA_WIDTH = 128, PACK_SEGMENT_DATA = True, MAX_SEGMENTS_PER_LANE = 2, VirtualHlsPlatform
    # prefix sum impl.       LUT    FF
    # balanced sum           18,168 3,942
    # non-balanced sum       17,548 4,342
    # trunc+zext orig at top 17,477 4,200

    print(to_rtl_str(m, target_platform=targetPlatform))
