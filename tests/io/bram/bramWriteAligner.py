#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat, segment_get
from hwt.constants import NOP
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.code import shl
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope, HlsScopeBoundIoScalar
from hwtLib.commonHwIO.addr_data import HwIOAddrDataRdVld
from pyMathBitPrecise.bit_utils import byte_mask_to_bit_mask


class HwIOAddrDataUnalignedToBram(HwModule):
    """
    Write potentially unaligned words to a bram (which supports only aligned access).
    If the access is unaligned, it must be split into 2 words which must be performed in sequence.
    If next request in overlapping with previous leftover word, merge them so unaligned
    sequential access still have full troughput.
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(4)
        self.DATA_WIDTH = HwParam(64)

    @override
    def hwDeclr(self):
        addClkRstn(self)

        self.reqIn = HwIOAddrDataRdVld()
        self.reqIn.ADDR_WIDTH = self.ADDR_WIDTH + log2ceil(self.DATA_WIDTH // 8)
        self.reqIn.DATA_WIDTH = self.DATA_WIDTH
        self.reqIn.HAS_MASK = True

        with self._hwParamsShared():
            self.ramOut: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()
            ramOut = self.ramOut
            ramOut.HAS_W = True
            ramOut.HAS_R = False
            ramOut.HAS_BE = True

    @hwt_expr_producer
    @classmethod
    def splitToAlignedWords(cls, newD: HStructConstBase, addrToWordIndexAlignBits:int, dataWidth:int):
        bit2_t = HBits(2)
        newWIndex = newD.addr[:addrToWordIndexAlignBits]
        wordAddrAlignBits = newD.addr[addrToWordIndexAlignBits:]

        wordByteShift = Concat(bit2_t.from_py(0), wordAddrAlignBits)
        wordAligned = shl(newD.data._zext(dataWidth * 2), Concat(wordByteShift, HBits(3).from_py(0)))
        maskAligned = shl(newD.mask._zext(dataWidth // 8 * 2), wordByteShift)
        PyBytecodeNoSplitSlices(wordAligned)
        PyBytecodeNoSplitSlices(maskAligned)

        newWord0 = wordAligned[dataWidth:]
        newWord1 = wordAligned[:dataWidth]
        WORD_BYTE_CNT = dataWidth // 8
        newWord0Mask = maskAligned[WORD_BYTE_CNT:]
        newWord1Mask = maskAligned[:WORD_BYTE_CNT]

        return newWIndex, newWord0, newWord0Mask, newWord1, newWord1Mask

    @hlsBytecode
    def forwardRequestThread(self, wordIndexTy: HdlType,
                             wordTy: HdlType,
                             wordMaskTy: HdlType,
                             ALIGN_BIT_CNT:int,
                             WORD_INDEX_STEP: int,
                             reqIn:HlsScopeBoundIoScalar,
                             ramOut: BramArrayProxy,
                             isSim: bool,
                             ):

        wordRegTy = HStruct(
            (wordIndexTy, "index"),
            (wordTy, "data"),
            (wordMaskTy, "mask"),
            (BIT, "valid"),
        )
        DATA_WIDTH = wordTy.bit_length()

        def copy(v):
            if isSim and v is not NOP:
                return v.__copy__()
            else:
                return v

        w0 = wordRegTy.from_py({"valid": 0})
        w1 = wordRegTy.from_py({"valid": 0})

        while b1:
            newD = reqIn.T.from_py(None)
            newDValid = b0
            if ~w1.valid:
                # if previous write was write of leftover and next write was unaligned and split to 2 transactions
                # we have to wait
                _newD = reqIn.read(blocking=False)
                newD = copy(_newD.data)
                newDValid = _newD.valid
                # if newDValid:
                #    print(f"dataIn.read {int(newD.addr):x} {int(newD.data):x} {int(newD.empty):x}")

            (newWIndex,
             newWord0, newWord0Mask,
             newWord1, newWord1Mask) = PyBytecodeInline(self.splitToAlignedWords)(newD, ALIGN_BIT_CNT, DATA_WIDTH)
            newWord1occupied = newWord1Mask[0]
            outWord = wordRegTy.from_py(None)
            outWord.valid = w0.valid | newDValid

            if w0.valid:
                # there are 2 options
                # if new data is mergable with w0 output w0+ new data, store potential overflow to w0
                # else write just w0 and store new data to w0 and also to w1 if is not aligned
                outWord.index = w0.index
                if newDValid:
                    # :note: w1 is guaranteed to be invalid
                    if w0.index._eq(newWIndex):
                        # w0 + newD -> output
                        # potentially store leftover to w0
                        outWord = copy(w0)
                        # :note: new and old data may overlap, just "| newWord0 & newWord0Mask" is insufficient
                        newDataBytes = []
                        for wordByteI, wordByteEn in enumerate(newWord0Mask):
                            newDataBytes.append(wordByteEn._ternary(segment_get(newWord0, 8, wordByteI),
                                                                    segment_get(w0.data, 8, wordByteI),
                                                                    ))
                            del wordByteEn
                        outWord.data = Concat(*reversed(newDataBytes))
                        outWord.mask |= newWord0Mask

                        w0.index += WORD_INDEX_STEP
                        w0.data = newWord1
                        w0.mask = newWord1Mask
                        w0.valid = newWord1occupied
                    else:
                        # w0 -> output,
                        # input -> w0, w1
                        outWord = copy(w0)

                        w0.index = newWIndex
                        w0.data = newWord0
                        w0.mask = newWord0Mask
                        w0.valid = b1

                        w1.index = newWIndex + WORD_INDEX_STEP
                        w1.data = newWord1
                        w1.mask = newWord1Mask
                        w1.valid = newWord1occupied

                else:
                    # write only leftover as there is no new data
                    outWord = copy(w0)
                    w0 = copy(w1)
                    w1.valid = b0

            else:
                # write current part optionally store leftover to w0
                outWord.index = newWIndex
                outWord.data = newWord0
                outWord.mask = newWord0Mask
                outWord.valid = newDValid

                w0.index = newWIndex + WORD_INDEX_STEP
                w0.data = newWord1
                w0.mask = newWord1Mask
                w0.valid = newDValid & newWord1occupied

            if outWord.valid:
                if isinstance(outWord.mask, HConst):
                    assert outWord.mask
                # print(f"ramOut.write {int(outWord.index):x} {int(outWord.data):x} {int(outWord.mask):x}")
                ramOut.write(outWord.index, outWord.data, mask=outWord.mask)

            #
            # if w0.valid:
            #    print(f"w0 {int(w0.index):x} {int(w0.data):x} {int(w0.mask):x}")
            # else:
            #    print("w0 - invalid")
            #
            # if w1.valid:
            #    print(f"w1 {int(w1.index):x} {int(w1.data):x} {int(w1.mask):x}")
            # else:
            #    print("w1 - invalid")

    @hlsBytecode
    def mainThread(self, hls: HlsScope, reqIn: HwIOAddrDataRdVld, ramOut: BramArrayProxy, isSim=False):
        ALIGN_BIT_CNT = log2ceil(self.DATA_WIDTH // 8)
        wordT = ramOut.interface.din._dtype
        wordIndexTy = ramOut.interface.addr._dtype
        wordMaskT = ramOut.interface.we._dtype
        WORD_INDEX_STEP = 1
        PyBytecodeInline(self.forwardRequestThread)(
            wordIndexTy, wordT, wordMaskT, ALIGN_BIT_CNT, WORD_INDEX_STEP,
            reqIn, ramOut, isSim)

    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        ramOut = BramArrayProxy(hls, self.ramOut)
        reqIn = HlsScopeBoundIoScalar(
            hls, self.reqIn,
            dtype=HwIO_to_HdlType().apply(self.reqIn, exclude=(self.reqIn.rd,
                                                               self.reqIn.vld)))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, reqIn, ramOut)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = HwIOAddrDataUnalignedToBram()
    m.CLK_FREQ = int(1e6)
    m.ADDR_WIDTH = 10-2
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
