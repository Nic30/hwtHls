
from collections import deque
from itertools import zip_longest
from math import isnan
import math
import struct
from typing import Optional, Generator, Union

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bits3t import Bits3val
from tests.math.fixp.passTestIoFixp import PassTestIoInHFixedPoint
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIo import PassTestIoIn, PassTestIoOut, PassTestIo, \
    errMsgFrormatter_ioName, ErrMsgFormatterT


class PassTestIoInIEEE754Fp(PassTestIoIn):

    def __init__(self, fpTy: IEEE754Fp, dataIn:list[float],
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 randomizeControl=False):
        super().__init__(dataIn, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         randomizeControl=randomizeControl)
        self.dataInH: Optional[tuple[HBitsConst]] = None
        self.fpTy = fpTy
        self.bitsTy = HBits(fpTy.bit_length())
        self.fpTySize = math.ceil(self.bitsTy.bit_length() / 8)
        self.floatStructFormatChar = fpTy.structFormatChar
         
    def floatToBits(self, v: float) -> Bits3val:
        if self.floatStructFormatChar is not None:
            # fast implementation with struct.unpack
            return self.bitsTy.from_py(struct.pack(self.floatStructFormatChar, v))
        else:
            # slower implementation
            return self.fpTy.from_py(v)._reinterpret_cast(self.bitsTy)

    def bitsToFloat(self, v: Bits3val) -> Optional[float]:
        assert v._dtype.bit_length() == self.bitsTy.bit_length(), (v, self.bitsTy)
        if v._is_full_valid():
            if self.floatStructFormatChar is not None:
                # fast implementation with struct.pack
                return struct.unpack(self.floatStructFormatChar, v.val.to_bytes(self.fpTySize, 'little'))[0]
            else:
                # slower implementation
                return self.bitsTy._from_py(v.val, v.vld_mask)._reinterpret_cast(self.fpTy).to_py()
        else:
            return None

    def floatAsTuple(self, d: float) -> tuple[HBitsConst, HBitsConst, HBitsConst]:
        return self.fpTy.from_py(d).to_py_tuple()  # mantisa, exponent, sign

    def _buildDataForLlvmIrMirRtl(self):
        PassTestIoInHFixedPoint._buildDataForLlvmIrMirRtl(self)
        
    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        return PassTestIoInHFixedPoint.getForLlvmIr(self)

    @override
    def getForRtl(self, portData: Optional[deque[HBitsConst]]=None):
        if portData is None:
            ioPort = self._getRtlDutPort()
            # if isinstance(ioPort, (HwIOStructRdVld, HwIOStructVld, HwIOStructRd)) and isinstance(ioPort.T, HBits):
            #     dataInH = [(d,) for d in dataInH]
                
            portData = ioPort._ag.data
            PassTestIo.getForRtl(self, ioPort)

        portData.extend(self.floatAsTuple(d) for d in self.dataIn)


class PassTestIoOutIEEE754Fp(PassTestIoOut):

    def __init__(self, fpTy:IEEE754Fp,
                 DATA_IN_FOR_DBG:list[float],
                 dataRef:list[float],
                 itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 randomizeControl=False):
        super().__init__(dataRef, itemCntLimit=itemCntLimit,
                         name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         randomizeControl=randomizeControl)
        self.fpTy = fpTy
        self.DATA_IN_FOR_DBG = DATA_IN_FOR_DBG
        
    @override
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        tc = self.passTests.tc
        T = self.fpTy
        resRef = self.dataRef

        for i, (din, ref, d) in enumerate(zip_longest(self.DATA_IN_FOR_DBG, resRef, dataSim)):
            ref: float
            d: HBitsConst
            tc.assertIsNotNone(ref, ("Output data contains more data then was expected", dataSim[len(resRef):]))
            tc.assertIsNotNone(d, ("Output data is missing data", i, resRef[len(dataSim):]))
            v = T.reinterpretRawIntToFloat(int(d))
            if isnan(ref):
                tc.assertTrue(isnan(v), (self.name, i, v, ref))
            else:
                tc.assertEqual(v, ref, (self.name, i, din, T.from_py(v), T.from_py(ref)))
    
    def IEEEFpTupleAsIntTuple(self, d: tuple[HBitsConst, HBitsConst, HBitsConst]) -> tuple[int, int, int]:
        "d in format (mantissa, exponent, sign)"
        mantissa, exponent, sign = d
        assert sign._dtype.bit_length() == 1
        return (int(mantissa), int(exponent), int(sign))

    @override
    def checkForRtl(self):
        oPort: HwIO = self._getRtlDutPort()
        formatIEEEFp = self.IEEEFpTupleAsIntTuple
        res = [formatIEEEFp(d) for d in oPort._ag.data]
        formatFloat = PassTestIoInIEEE754Fp.floatAsTuple
        resRefAsHwFp = [formatFloat(self, d) for d in self.dataRef]
        
        #inAsfAsHwFpTuple = [formatFloat(self, d) for d in self.DATA_IN_FOR_DBG]
        tc = self.passTests.tc
        tc.assertSequenceEqual(res, resRefAsHwFp,
                                 msg=(self.name, [(inputsPy, outDataRefPy)
                                                for inputsPy, outDataRefPy in zip(self.DATA_IN_FOR_DBG, self.dataRef)]))


class PassTestInjectorForFp(PassTestInjectorForDInDOutHwModule):

    def __init__(self, topToRunTestsOn:_BaseALU1HwModule, tc:SimTestCase, fpTy: IEEE754Fp, optThroughputVsArea:float, MAX_TABLE_ADDR_WIDTH:int):
        super().__init__(topToRunTestsOn, tc)
        self.optThroughputVsArea = optThroughputVsArea
        self.MAX_TABLE_ADDR_WIDTH = MAX_TABLE_ADDR_WIDTH
        self.fpTy = fpTy
    
    def _bindData_normalizeIn(self, name: str, rtlPresetBeforeClk:bool, inD: Union[PassTestIo, list[float]], randomizeControl: Optional[bool]):
        if isinstance(inD, PassTestIo):
            return super()._bindData_normalizeIn(name, rtlPresetBeforeClk, inD, randomizeControl)
        else:
            return PassTestIoInIEEE754Fp(self.fpTy, inD, name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                                         randomizeControl=bool(randomizeControl))

    def _bindData_normalizeOut(self, name: str, rtlPresetBeforeClk:bool,
                               itemCntLimit:Optional[int], outDataRef: Union[PassTestIo, list[HBitsConst]],
                               randomizeControl: Optional[bool]):
        if isinstance(outDataRef, PassTestIo):
            return super()._bindData_normalizeOut(name, rtlPresetBeforeClk, itemCntLimit, outDataRef, randomizeControl)
        else:
            return PassTestIoOutIEEE754Fp(
                self.fpTy, outDataRef, None, itemCntLimit=itemCntLimit, name=name,
                rtlPresetBeforeClk=rtlPresetBeforeClk,
                randomizeControl=bool(randomizeControl))

    @override
    def install(self, platform:VirtualHlsPlatform):
        installMathLibComponentGenerators(platform,
                                          optThroughputVsArea=self.optThroughputVsArea,
                                          MAX_TABLE_ADDR_WIDTH=self.MAX_TABLE_ADDR_WIDTH
                                          )
        super().install(platform)

