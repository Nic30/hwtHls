from _collections import deque
from typing import Any, Optional, Union, Self, Callable, Generator

from hwt.code import Concat
from hwt.constants import NOP
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.pyUtils.typingFuture import override
from hwt.simulator.utils import Bits3valToInt
from tests.passTestInjector import PassTestInjector
from tests.passTestIo import PassTestIoOut, errMsgFrormatter_ioName, \
    PassTestIoIn, PassTestIo, PassTestIoToFlatten


class PassTestIoInStructWrap(PassTestIoIn):
    """
    PassTestIo which aggregates multiple PassTestIo instances
    
    :note: data from this PassTestIo are set from this to members
    """
    
    def __init__(self, members: tuple[PassTestIoIn, ...], dataIn:list[tuple[HConst, ...]],
                  name:Optional[str]=None,
                  rtlPresetBeforeClk=True,
                  randomizeControl=False,
                  flattenForModel=False):
        self.members = members
        self.dataIn = dataIn
        super().__init__(dataIn, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         randomizeControl=randomizeControl)
        self.flattenForModel = flattenForModel
        self.dataInForIrMir: Optional[list[HBitsConst]] = None
    
    @override
    def bindPassTestInjector(self, passTests:PassTestInjector):
        super().bindPassTestInjector(passTests)
        for m in self.members:
            m.bindPassTestInjector(passTests)

    @override
    def getForModel(self):
        memberDataAppend = tuple(m.dataIn.append for m in self.members)
        memberCnt = len(self.members) 
        for mergedData in self.dataIn:
            assert len(memberDataAppend) == memberCnt, (len(memberDataAppend), memberCnt)
            for memberD, memberAppend in zip(mergedData, memberDataAppend):
                memberAppend(memberD)

        ioIteraotrs = (m.getForModel() for m in self.members)
        if self.flattenForModel:
            return PassTestIoToFlatten(ioIteraotrs)
        else:
            return ioIteraotrs

    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        """
        :attention: assumes getForModel was previously called to copy data to members
        """
        dataInForIrMir = self.dataInForIrMir
        if dataInForIrMir is None:
            dataInForIrMir = []
            for data in zip(*(m.getForLlvmIr() for m in self.members)):
                dataInForIrMir.append(Concat(*reversed(data)))
            self.dataInForIrMir = dataInForIrMir
            
        return iter(dataInForIrMir)

    @override
    def getForRtl(self, portData: Optional[deque[tuple[HBitsConst, ...]]]=None):
        tmpData = []
        for m in self.members:
            tmpPortData = []
            m.getForRtl(portData=tmpPortData)
            tmpData.append(tmpPortData)
        portDataTuples = (memberDataWord for memberDataWord in zip(*tmpData))
        if portData is None:
            ioPort = self._getRtlDutPort()
            portData = ioPort._ag.data
            PassTestIo.getForRtl(self, ioPort=ioPort)

        portData.extend(portDataTuples)
        

class PassTestIoInStruct(PassTestIoIn):

    def __init__(self, T: HStruct, dataIn:list[HStructConstBase],
                  name:Optional[str]=None,
                  inInPyFormat=False,
                  rtlPresetBeforeClk=True,
                  randomizeControl=False,
                  unpackMembersForModel=False):
        if inInPyFormat:
            dataIn = tuple(NOP if d is NOP else T.from_py(d) for d in dataIn)
        super().__init__(dataIn, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.T = T
        self.dataInAsTuples: Optional[list[tuple[Union[int, None, HBitsConst]]]] = None
        self.dataInForLlvmIrAndMir: Optional[list[HBitsConst]] = None
        self.unpackMembersForModel = unpackMembersForModel

    def _buildDataInForLlvmIrAndMir(self):
        T = self.T
        flatT = HBits(T.bit_length())
        data = tuple(NOP if v is NOP else v._reinterpret_cast(flatT)
                     for v in self.dataIn)
        self.dataInForLlvmIrAndMir = data

    def _buildDataInAsTuples(self):
        T = self.T
        self.dataInAsTuples = tuple(NOP if d is NOP else tuple(getattr(d, field.name)
                                                               for field in T.fields)
                                    for d in self.dataIn)
    
    def getForModel(self):
        dataInAsTuples = self.dataInAsTuples
        if dataInAsTuples is None:
            self._buildDataInAsTuples()
            dataInAsTuples = self.dataInAsTuples
        if self.unpackMembersForModel:
            # reshape data for data for members
            memberCnt = len(self.T.fields) 
            memberData = tuple([] for _ in range(memberCnt))
            memberDataAppend = tuple(d.append for d in memberData)
            for mergedData in self.dataIn:
                assert len(memberDataAppend) == memberCnt, (len(memberDataAppend), memberCnt)
                for memberD, memberAppend in zip(mergedData, memberDataAppend):
                    memberAppend(memberD)
            return PassTestIoToFlatten(iter(d) for d in memberData)
        else:
            return iter(dataInAsTuples)

    @override
    def getForLlvmIr(self) -> Generator[HBitsConst, None, None]:
        dataInForLlvmIrAndMir = self.dataInForLlvmIrAndMir
        if dataInForLlvmIrAndMir is None:
            self._buildDataInForLlvmIrAndMir()
            dataInForLlvmIrAndMir = self.dataInForLlvmIrAndMir

        return iter(dataInForLlvmIrAndMir)

    @override
    def getForRtl(self):
        ioPort = self._getRtlDutPort()
        dataInAsTuples = self.dataInAsTuples
        if dataInAsTuples is None:
            self._buildDataInAsTuples()
            dataInAsTuples = self.dataInAsTuples
        ioPort._ag.data.extend(dataInAsTuples)
        PassTestIo.getForRtl(self, ioPort)


class PassTestIoOutStruct(PassTestIoOut):

    def __init__(self, T: HStruct, dataRef: Optional[list[tuple]],
                 itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter: Optional[Callable[[Self, list[HBitsConst], list[int]], Any]]=errMsgFrormatter_ioName,
                 randomizeControl=False
                 ):
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         errMsgFormatter=errMsgFormatter, randomizeControl=randomizeControl)
        self.T = T

    @override
    def setDataRef(self, data: list[Union[tuple, dict[str, Any], HStructConstBase]]):
        dataRef = self.dataRef = []
        T = self.T
        for item in data:
            if isinstance(item, HStructConstBase):
                item = item.to_py()
            if isinstance(item, dict):
                item = tuple(item[field.name] for field in T.fields)

            item = tuple(d.to_py() if isinstance(d, HConst) else d for d in item)
            dataRef.append(item)

    @override
    def checkForLlvmIr(self, dataSim: list[HBitsConst]):
        T = self.T

        dataOut = [tuple(Bits3valToInt(member)
                         for member in d._reinterpret_cast(T))
                   for d in dataSim]

        tc = self.passTests.tc
        tc.assertValSequenceEqual(dataOut, self.dataRef, msg=self.errMsgFormatter(self, dataSim, self.dataRef))

    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        dataSim = oPort._ag.data
        tc = self.passTests.tc
        tc.assertValSequenceEqual(dataSim, self.dataRef, msg=self.errMsgFormatter(self, dataSim, self.dataRef))

