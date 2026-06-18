#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.code import shl
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.bram import IoProxyBram
from hwtHls.scope import HlsScope
from tests.io.bram.bramWriteAligner import HwIOAddrDataUnalignedToBram
from hwt.hdl.types.bitsConst import HBitsConst


class PcieTlpStoreAligner(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(64)
        self.DATA_WIDTH = HwParam(256)
        self.INDEX_STEP = HwParam(1)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        i = self.dataIn = HwIOStructRdVld()
        i.T = self.getWordToStore_t(self.ADDR_WIDTH, self.DATA_WIDTH)
        self.INDEX_WIDTH = self.ADDR_WIDTH - log2ceil(self.DATA_WIDTH)
        self.ramOut: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()
        o = self.ramOut
        o.ADDR_WIDTH = self.INDEX_WIDTH
        o.DATA_WIDTH = self.DATA_WIDTH
        o.HAS_R = False
        o.HAS_BE = True

    @staticmethod
    def getWordToStore_t(addressWidth:int, dataWidth: int) -> HStruct:
        WordToStore_t = HStruct(
            (HBits(addressWidth), "addr"),  # byte address of start of this word
                                            # for array in Bus Master completition handler buffer
            (HBits(dataWidth), "data"),
            (HBits(log2ceil(dataWidth // 8)), "empty"),  # nuber of empty bytes from end (msb bit)
            name="WordToStore_t",
        )
        return WordToStore_t

    @hwt_expr_producer
    @staticmethod
    def byteEnabledByEmpty(byteI: int, bytesTotal: int, empty: AnyHBitsValue):
        if byteI == 0:
            minEmptyWidhToDisableB0 = log2ceil(bytesTotal) + 1
            if empty._dtype.bit_length() < minEmptyWidhToDisableB0:
                return b1  # never dissabled because empty may be 0 to bytesTotal-1

        maxEmptyWithByte = bytesTotal - byteI
        return empty < maxEmptyWithByte

    @hwt_expr_producer
    @classmethod
    def splitToAlignedWords(cls, newD: HStructConstBase, addrToWordIndexAlignBits:int, dataWidth:int) \
            ->tuple[HBitsConst, HBitsConst, HBitsConst, HBitsConst, HBitsConst]:
        bit2_t = HBits(2)
        newWIndex = newD.addr[:addrToWordIndexAlignBits]
        # pcie address is always aligned to 4B (PcieTlpWord_t)
        # lower bits may be masked out by first_be, which is then injected into input address
        # :var wordAddrAlignBits: specifies shift of whole word, see wordShift
        wordAddrAlignBits = newD.addr[addrToWordIndexAlignBits:2]

        in4BWordAlign = newD.addr[2:]
        # use address to extract aligned data from newD
        # 2 for 4B alignmet, 3 for 8 bits in Byte
        wordByteShift = Concat(bit2_t.from_py(0), wordAddrAlignBits, bit2_t.from_py(0))
        wordAligned = shl(newD.data._zext(dataWidth * 2), Concat(wordByteShift, HBits(3).from_py(0)))
        PyBytecodeNoSplitSlices(wordAligned)
        newWord0 = wordAligned[dataWidth:]
        newWord1 = wordAligned[:dataWidth]
        WORD_BYTE_CNT = dataWidth // 8

        # newDEmpty disables bytes from MSB side
        # wordAddrAlignBits moves all bytes to left (MSB side)
        # in4BWordAlign disables bytes from LSB side
        byteShiftWidth = wordByteShift._dtype.bit_length()
        newDEmptyExt = newD.empty._zext(byteShiftWidth)
        emptyForWord0 = newDEmptyExt - wordByteShift
        # all bytes until end of word are valid, only constraint is wordByteShift, in4BWordAlign
        # :note: this is required as emptyForWord0 would othherwise overflow
        emptyForWord0 = (newDEmptyExt < wordByteShift)._ternary(emptyForWord0._dtype.from_py(0), emptyForWord0)

        newWord0Mask = Concat(*(
            (wordByteShift <= byteI) &  # not shifted out
            cls.byteEnabledByEmpty(byteI, WORD_BYTE_CNT, emptyForWord0) &  # enabled by empty
            ((in4BWordAlign <= byteI) if byteI < 4 else 1)  # not disabled by in word offset
            for byteI in reversed(range(WORD_BYTE_CNT))
        ))
        # empty + number of bytes which remained in word 1 due to wordByteShift
        empty1Width = wordByteShift._dtype.bit_length()
        emptyForWord1 = newD.empty._zext(empty1Width) + (HBits(empty1Width).from_py(WORD_BYTE_CNT) - wordByteShift._zext(empty1Width))
        newWord1Mask = Concat(*(
            cls.byteEnabledByEmpty(byteI, WORD_BYTE_CNT, emptyForWord1) &  # enabled by empty
            (wordByteShift > byteI)  # is shifted in from word0
            for byteI in reversed(range(WORD_BYTE_CNT))
        ))

        return newWIndex, newWord0, newWord0Mask, newWord1, newWord1Mask

    @hlsBytecode
    def mainThread(self, reqIn: HwIOStructRdVld,
                   ramOut: IoProxyBram,
                   addressWidth:int,
                   dataWidth: int,
                   WORD_INDEX_STEP: int,
                   isSim:bool=False
                   ):
        """
        Receive words with arbitrary size and start address
        and store them to memory, potentially spliting unalligned transaction
        in two and potentially mergin second part with consequent unaligned transaction.
        
        The data is 4B aligned, meaning that if the address is not alligned to 4B (lower 2 bits != 0)
        the data contains padding.
        
        :note: Altera has extra 4B padding for 8B aligned transactions, this padding is not expected there.
        
        :note: expects that the address never overflows
            (which should be asserted)
        :param wordIndexStep: 1/-1 to specify direction of the iteration
        """

        addrToWordIndexAlignBits = log2ceil(dataWidth // 8)
        # emptyTy = HBits(addrToWordIndexAlignBits)
        wordMaskT = HBits(dataWidth // 8)
        wordIndexTy = HBits(addressWidth - addrToWordIndexAlignBits)
        wordT = HBits(dataWidth)

        PyBytecodeInline(HwIOAddrDataUnalignedToBram.forwardRequestThread)(self, wordIndexTy, wordT, wordMaskT,
                                                                           addrToWordIndexAlignBits, WORD_INDEX_STEP,
                                                                           reqIn, ramOut, isSim)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        hls.addThread(HlsThreadFromPy(hls, self.mainThread,
                                      IoProxyScalar(hls, self.dataIn, dtype=self.dataIn.T), IoProxyBram(hls, self.ramOut),
                                      self.ADDR_WIDTH,
                                      self.DATA_WIDTH,
                                      self.INDEX_STEP))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    dut = PcieTlpStoreAligner()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(dut, target_platform=p))

