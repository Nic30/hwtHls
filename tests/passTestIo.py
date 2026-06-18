from _collections import deque
from typing import Any, Optional, Generator, Iterable, Union, Self, Callable

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwtSimApi.triggers import StopSimumulation
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.passTestInjector import PassTestInjector


LlvmSimFunctionArgT = Union[list[HBitsConst], Generator[HBitsConst, None, None]]  # :note: item types depend on type of the IO of the simulated function


class ListRaisingStopSimumulationWhenFilled(list):

    def __init__(self, __iterable:Iterable, targetSize:int) -> None:
        list.__init__(self, __iterable)
        self.targetSize = targetSize

    def append(self, __object) -> None:
        list.append(self, __object)
        if len(self) >= self.targetSize:
            raise StopSimumulation()

    def extend(self, __iterable:Iterable) -> None:
        for i in __iterable:
            self.append(i)


class PassTestIo():
    """
    Base class of objects which are adapter between simulation data and the simulators.
    Its purpose is to handle casts, and to provide universal api for data container materialization.
    
    :ivar rtlPresetBeforeClk: a flag set to  :class:`hwtSimApi.agents.rdVldSync.DataRdVldAgent` presetBeforeClk 
        (if True the values are set to IO 1/4 of clock in advance, to make simulation wave more readable. Note that
         this is only possible in situations with a single and stable clock.)
    :ivar randomizeControl: see :meth:`hwt.simulator.simTestCase.SimTestCase.randomize`
    """

    def __init__(self, name: Optional[str]=None, rtlPresetBeforeClk:bool=True, randomizeControl:bool=False):
        self.passTests: Optional[PassTestInjector] = None
        self.name = name
        self.rtlPresetBeforeClk = rtlPresetBeforeClk
        self.randomizeControl = randomizeControl

    def bindPassTestInjector(self, passTests: PassTestInjector):
        self.passTests = passTests

    def getForModel(self) -> Any:
        """
        Prepare the io argument for the model of the DUT.
        """
        raise NotImplementedError(self)

    def getForLlvmIr(self) -> LlvmSimFunctionArgT:
        """
        Prepare the io argument :class:`hwtHls.ssa.analysis.llvmIrInterpret.LlvmIrInterpret`
        """
        raise NotImplementedError(self)

    def getForLlvmMir(self) -> LlvmSimFunctionArgT:
        """
        Prepare the io argument :class:`hwtHls.ssa.analysis.llvmMirInterpret.LlvmMirInterpret`
        """
        return self.getForLlvmIr()

    def getForHlsNetlist(self) -> LlvmSimFunctionArgT:
        """
        Prepare the io argument :class:`hwtHls.netlist.analysis.hlsNetlistSimulator.HlsNetlistSimulator`
        """
        return self.getForLlvmIr()

    def _getRtlDutPort(self) -> HwIO:
        dut = self.passTests._topToRunTestsOn
        return getattr(dut, self.name)

    def getRtlDataLen(self) -> int:
        return len(self._getRtlDutPort()._ag.data)

    def getForRtl(self, ioPort:Optional[HwIO]=None):
        """
        Prepare data in  :class:`hwtSimApi.agents.base.AgentBase` prepared on dut after compilation
        finished and RTL simulation was started on :class:hwt.simulator.simTestCase.SimTestCase`
        """
        if ioPort is None:
            ioPort = self._getRtlDutPort()

        ioPort._ag.presetBeforeClk = self.rtlPresetBeforeClk
        if self.randomizeControl:
            self.passTests.tc.randomize(ioPort)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} for {self.name}>"
        

class PassTestIoToFlatten(tuple[Union[Self, PassTestIo]]):

    @classmethod
    def appendUnwrapped(cls, src: Union[Self, PassTestIo], dst: list[PassTestIo]):
        if isinstance(src, cls):
            for m in src:
                cls.appendUnwrapped(m, dst)
        else:
            dst.append(src)


class PassTestIoIn(PassTestIo):
    """
    :attention: dataIn in constructor is not final and may change before simulation execution
    """

    def __init__(self, dataIn: list[Any], name:Optional[str]=None, rtlPresetBeforeClk=True, randomizeControl=False):
        super().__init__(name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.dataIn = dataIn

    @override
    def getForModel(self):
        return iter(self.dataIn)

    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        return self.getForModel()

    @override
    def getForLlvmMir(self) -> Generator[HBitsConst, None, None]:
        return self.getForLlvmIr()

    @override
    def getForHlsNetlist(self) -> Generator[HBitsConst, None, None]:
        return self.getForLlvmIr()

    @override
    def getForRtl(self, ioPort:Optional[HwIO]=None, portData: Optional[deque[HBitsConst]]=None):
        if portData is None:
            if ioPort is None:
                ioPort = self._getRtlDutPort()
            portData = ioPort._ag.data
            super().getForRtl(ioPort=ioPort)

        portData.extend(self.dataIn)


class PassTestIoInPyInt(PassTestIoIn):

    def __init__(self, T: HBits, dataIn: list[int], name:Optional[str]=None, rtlPresetBeforeClk=True, randomizeControl=False):
        super().__init__(dataIn, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.T = T
        self.dataInH: Optional[list[HConst]] = None
    
    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        dataInH = self.dataInH
        if dataInH is None:
            w = self.T.bit_length()
            T = HBits(w).from_py
            dataInH = [T(to_unsigned(d, w)) for d in self.dataIn]
            self.dataInH = dataInH

        return iter(dataInH)


def errMsgFrormatter_HBitsAsHex(ptIo: PassTestIo, dataOut: list[HBitsConst], dataOutRef:list[int]):
    return ptIo.name, "[%s] != [%s]" % (
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in dataOutRef)
        )


def errMsgFrormatter_ioName(ptIo: PassTestIo, dataOut: list[HBitsConst], dataOutRef:list[int]):
    return ptIo.name


ErrMsgFormatterT = Callable[[Self, list[HBitsConst], list[int]], Any]


class PassTestIoOut(PassTestIo):
    """
    :attention: dataRef in constructor is not final and may change before simulation execution
    """

    def __init__(self, dataRef: list[Any], itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter: Optional[ErrMsgFormatterT]=errMsgFrormatter_ioName,
                 randomizeControl=False,
                 ):
        super().__init__(name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.dataRef = dataRef
        self.itemCntLimit = itemCntLimit
        self.errMsgFormatter = errMsgFormatter

    def setDataRef(self, data: list[Any]):
        self.dataRef = data

    @override
    def getForModel(self):
        # spawn empty data container for output data
        if self.itemCntLimit is None:
            return []
        else:
            return ListRaisingStopSimumulationWhenFilled((), self.itemCntLimit)

    @override
    def getForLlvmIr(self) -> list[HBitsConst]:
        return self.getForModel()

    @override
    def getForLlvmMir(self) -> list[HBitsConst]:
        return self.getForLlvmIr()

    @override
    def getForHlsNetlist(self) -> list[HBitsConst]:
        return self.getForLlvmIr()

    def checkForLlvmIr(self, dataSim: list[HBitsConst]):
        tc = self.passTests.tc
        tc.assertValSequenceEqual(dataSim, self.dataRef, msg=self.errMsgFormatter(self, dataSim, self.dataRef))

    def checkForLlvmMir(self, dataSim: list[HBitsConst]):
        self.checkForLlvmIr(dataSim)

    def checkForHlsNetlist(self, dataSim: list[HBitsConst]) -> list[HBitsConst]:
        return self.checkForLlvmIr(dataSim)

    def getRtlDataLen(self) -> int:
        return len(self.dataRef)

    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        self.checkForLlvmIr(oPort._ag.data)

