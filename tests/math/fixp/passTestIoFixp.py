from collections import deque
from math import isnan
from typing import Optional, Generator, Any

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from pyMathBitPrecise.bit_utils import to_signed
from pyMathBitPrecise.bits3t import Bits3val
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.passTestIo import PassTestIoIn, PassTestIo, PassTestIoOut, \
    ErrMsgFormatterT, errMsgFrormatter_ioName


class PassTestIoInHFixedPoint(PassTestIoIn):

    def __init__(self, fpTy: HFixedPointQ, dataIn:list[float],
                 name:Optional[str]="data_in",
                 rtlPresetBeforeClk=True,
                 randomizeControl=False):
        super().__init__(dataIn, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         randomizeControl=randomizeControl)
        self.dataInH: Optional[tuple[HBitsConst]] = None
        self.fpTy = fpTy
        self.bitsTy = HBits(fpTy.bit_length())
         
    def floatToBits(self, v: float):
        return self.fpTy.from_py(v)._reinterpret_cast(self.bitsTy)

    def bitsToFloat(self, v: Bits3val):
        assert v._dtype.bit_length() == self.bitsTy.bit_length(), (v, self.bitsTy)
        return self.bitsTy._from_py(v.val, v.vld_mask)._reinterpret_cast(self.fpTy).to_py()

    def _buildDataForLlvmIrMirRtl(self):
        dataInH = []
        assertTrue = self.passTests.tc.assertTrue
        bitsToFloat = self.bitsToFloat
        floatToBits = self.floatToBits
        for v in self.dataIn:
            vH = floatToBits(v)
            vHAsFloat = bitsToFloat(vH)
            assertTrue(vHAsFloat == v or (isnan(vHAsFloat) and isnan(v)), ("check that input cast does not cause rounding", vH, v, vHAsFloat))
            dataInH.append(vH)
        self.dataInH = dataInH
        
    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        dataInH = self.dataInH
        if dataInH is None:
            self._buildDataForLlvmIrMirRtl()
            dataInH = self.dataInH
        return iter(dataInH)

    @override
    def getForRtl(self, portData: Optional[deque[HBitsConst]]=None):
        dataInH = self.dataInH
        if dataInH is None:
            self._buildDataForLlvmIrMirRtl()
            dataInH = self.dataInH
        if portData is None:
            ioPort = self._getRtlDutPort()
            # if isinstance(ioPort, (HwIOStructRdVld, HwIOStructVld, HwIOStructRd)) and isinstance(ioPort.T, HBits):
            #     dataInH = [(d,) for d in dataInH]
                
            portData = ioPort._ag.data
            PassTestIo.getForRtl(self, ioPort)

        portData.extend(dataInH)


class PassTestIoOutHFixedPoint(PassTestIoOut):
    """
    :param maxErrorInt: 1 represents 1ULP (Unit in the Last Place)
    """

    def __init__(self, fpTy: HFixedPointQ,
                 DATA_IN_FOR_DBG: list[float],
                 dataRef:list[float],
                 maxErrorInt:Optional[int]=None,
                 itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter:Optional[ErrMsgFormatterT]=errMsgFrormatter_ioName,
                 randomizeControl=False):
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name,
                         rtlPresetBeforeClk=rtlPresetBeforeClk,
                         errMsgFormatter=errMsgFormatter, randomizeControl=randomizeControl)
        self.fpTy = fpTy
        self.bitsTy = HBits(fpTy.bit_length())
        self.DATA_IN_FOR_DBG = DATA_IN_FOR_DBG
        self.maxErrorInt = maxErrorInt
        self.dataRefAsInts: Optional[tuple[tuple[int], ...]] = None
        
    floatToBits = PassTestIoInHFixedPoint.floatToBits
    bitsToFloat = PassTestIoInHFixedPoint.bitsToFloat
    
    def _buildDataRefAsInts(self):
        signed = self.fpTy.signed
        w = self.bitsTy.bit_length()
        res: list[tuple[int, int]] = []
        floatToBits = self.floatToBits
        for v in self.dataRef:
            c: float
            vAsInt = int(floatToBits(v))

            if signed:
                vAsInt = to_signed(vAsInt, w)
            res.append(vAsInt)
        self.dataRefAsInts = tuple(res)

    def _assertEquals(self, dataOut: list[HBitsConst]):
        fpT = self.fpTy
        w = fpT.bit_length()
        signed = fpT.signed
        tc = self.passTests.tc
        if self.dataRefAsInts is None:
            self._buildDataRefAsInts()
        
        expectedItemCnt = len(self.DATA_IN_FOR_DBG)
        tc.assertEqual(len(self.dataRef), expectedItemCnt, (expectedItemCnt, len(self.dataRef)))
        tc.assertEqual(len(dataOut), expectedItemCnt, (expectedItemCnt, len(dataOut)))
        maxErrorInt = self.maxErrorInt
        bitsToFloat = self.bitsToFloat
        for i, (vIn, vOut, refVInt) in enumerate(zip(self.DATA_IN_FOR_DBG,
                                                     dataOut,
                                                     self.dataRefAsInts)):
            vOut: HBitsConst
            vOutF = bitsToFloat(vOut)
            _vOut = vOut.to_py()
            if signed:
                _vOut = to_signed(_vOut, w)
            tc.assertAlmostEqual(_vOut, refVInt,
                                   msg=(i, vIn, vOut, vOutF),
                                   delta=maxErrorInt)

    @override
    def checkForLlvmIr(self, dataSim: list[HBitsConst]):
        self._assertEquals(dataSim)

    @override
    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        self._assertEquals(oPort._ag.data)


class PassTestIoOutStructHFixedPoint2(PassTestIoOut):

    def __init__(self, fpTy: HFixedPointQ,
                 DATA_IN_FOR_DBG: list[float],
                 dataRef:list[Any], maxErrorInt:Optional[int]=None,
                 itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter:Optional[ErrMsgFormatterT]=errMsgFrormatter_ioName,
                 randomizeControl=False):
        """
        :ivar maxErrorInt: max error of the result in the format of int representing
            the max diffrence of int representation of the number
        """
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         errMsgFormatter=errMsgFormatter, randomizeControl=randomizeControl)
        self.DATA_IN_FOR_DBG = DATA_IN_FOR_DBG
        self.fpTy = fpTy
        self.bitsTy = HBits(fpTy.bit_length())
        self.maxErrorInt = maxErrorInt
        self.dataRefAsInts: Optional[tuple[tuple[int, int], ...]] = None

    floatToBits = PassTestIoInHFixedPoint.floatToBits
    bitsToFloat = PassTestIoInHFixedPoint.bitsToFloat
    
    def _buildDataRefAsInts(self):
        signed = self.fpTy.signed
        w = self.bitsTy.bit_length()
        res: list[tuple[int, int]] = []
        floatToBits = self.floatToBits
        for a, b in self.dataRef:
            a: float
            b:float
            aAsInt = int(floatToBits(a))
            bAsInt = int(floatToBits(b))

            if signed:
                aAsInt = to_signed(aAsInt, w)
                bAsInt = to_signed(bAsInt, w)
            res.append((aAsInt, bAsInt))
        self.dataRefAsInts = tuple(res)

    @override
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        fpT = self.fpTy
        w = fpT.bit_length()
        dataOutAsABPairs: list[tuple[HBitsConst, HBitsConst]] = []
        for d in dataSim:
            b = d[:w]
            a = d[w:]
            dataOutAsABPairs.append((a, b))
        
        self._assertABPairEquals(dataOutAsABPairs)

    def _assertABPairEquals(self, dataOutAsABPairs: list[tuple[HBitsConst, HBitsConst]]):
        """
        :param maxErrorInt: 1 represents 1ULP (Unit in the Last Place)
        """
        fpT = self.fpTy
        w = fpT.bit_length()
        signed = fpT.signed
        tc = self.passTests.tc
        if self.dataRefAsInts is None:
            self._buildDataRefAsInts()
        
        expectedItemCnt = len(self.DATA_IN_FOR_DBG)
        tc.assertEqual(len(self.dataRef), expectedItemCnt, (expectedItemCnt, len(self.dataRef)))
        tc.assertEqual(len(dataOutAsABPairs), expectedItemCnt, (expectedItemCnt, len(dataOutAsABPairs)))
        maxErrorInt = self.maxErrorInt
        bitsToFloat = self.bitsToFloat
        for i, (v, (a, b), (refAInt, refBInt)) in enumerate(zip(self.DATA_IN_FOR_DBG,
                                                                        dataOutAsABPairs,
                                                                        self.dataRefAsInts)):
            a: HBitsConst
            b: HBitsConst

            aF, bF = bitsToFloat(a), bitsToFloat(b)
            _a = a.to_py()
            _b = b.to_py()
            if signed:
                _a = to_signed(_a, w)
                _b = to_signed(_b, w)
            tc.assertAlmostEqual(_a, refAInt,
                                   msg=(i, v, a, aF),
                                   delta=maxErrorInt)
            tc.assertAlmostEqual(_b, refBInt,
                                   msg=(i, v, _b, b, bF),
                                   delta=maxErrorInt)

    @override
    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        self._assertABPairEquals(oPort._ag.data)

