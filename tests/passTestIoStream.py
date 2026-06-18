from collections import deque
from typing import Optional

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from hwtLib.abstract.simFrameUtils import SimFrameUtils
from tests.passTestIo import PassTestIoIn, PassTestIoOut


class PassTestIoInStream(PassTestIoIn):

    def __init__(self, fuCls: SimFrameUtils, inData: list[list[int]], name:Optional[str]=None,
                 rtlPresetBeforeClk=True, randomizeControl=False):
        super().__init__(inData, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.fuCls = fuCls
        self.dataInLlvmIrAndMir: Optional[tuple[HBitsConst, ...]] = None  # flattened
        self.dataInRtl: Optional[tuple[tuple[HBitsConst, ...], ...]] = None  # tuples for agent

    def _buildFrames(self):
        # :note: this must be lazy loaded because the dut port does not exist before
        #  compilation start and thus we do not know the data format at the beginning
        fuCls = self.fuCls
        ioPort = self._getRtlDutPort()
        rxFu = fuCls.from_HwIO(ioPort)
        dataInWordTuples = []
        for frame in self.dataIn:
            rxFu.send_bytes(frame, dataInWordTuples)
        dataIn = tuple(rxFu.concatWordBits(dataInWordTuples))
        self.dataInLlvmIrAndMir = dataIn
        self.dataInRtl = tuple(dataInWordTuples)

    @override
    def getForLlvmIr(self) -> list[HBitsConst]:
        dataIn = self.dataInLlvmIrAndMir
        if dataIn is None:
            self._buildFrames()
            dataIn = self.dataInLlvmIrAndMir
        return iter(dataIn)

    @override
    def getForRtl(self):
        dataIn = self.dataInRtl
        if dataIn is None:
            self._buildFrames()
            dataIn = self.dataInRtl
        ioPort = self._getRtlDutPort()
        ioPort._ag.data.extend(dataIn)
        ioPort._ag.presetBeforeClk = self.rtlPresetBeforeClk
        if self.randomizeControl:
            self.passTests.tc.randomize(ioPort)


class PassTestIoOutStream(PassTestIoOut):

    def __init__(self, fuCls: SimFrameUtils, dataRef: list[list[int]],
                 itemCntLimit=None, name: Optional[str]=None,
                 unpackWordBits=False,
                 rtlPresetBeforeClk=True,
                 randomizeControl=False):
        super().__init__(dataRef, itemCntLimit, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk, randomizeControl=randomizeControl)
        self.fuCls = fuCls
        self.unpackWordBits = unpackWordBits

    def getRtlDataLen(self) -> int:
        ioPort = self._getRtlDutPort()
        txFu: SimFrameUtils = self.fuCls.from_HwIO(ioPort)
        tmp = deque()
        for frame in self.dataRef:
            txFu.send_bytes(frame, tmp)

        return len(tmp)

    @override
    def checkForLlvmIr(self, dataSim: list[HBitsConst]):
        ioPort = self._getRtlDutPort()
        txFu = self.fuCls.from_HwIO(ioPort)
        tx = deque(txFu.updackWordBits(d) for d in dataSim)
        # for d in tx:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))
        ioName = self.name
        tc = self.passTests.tc
        for frameI, frame in enumerate(self.dataRef):
            offset, data = txFu.receive_bytes(tx)
            tc.assertEqual(offset, 0)
            tc.assertValSequenceEqual(data, frame, msg=(ioName, "frame", frameI))

        tc.assertEqual(len(tx), 0, ioName)        
    @override
    def checkForRtl(self):
        ioPort = self._getRtlDutPort()
        txFu = self.fuCls.from_HwIO(ioPort)
        outData = ioPort._ag.data
        if self.unpackWordBits:
            tx = deque(txFu.updackWordBits(d) for d in outData)
        else:
            tx = deque(outData)
        # for d in tx:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))
        ioName = self.name
        tc = self.passTests.tc
        for frameI, frame in enumerate(self.dataRef):
            offset, data = txFu.receive_bytes(tx)
            tc.assertEqual(offset, 0)
            tc.assertValSequenceEqual(data, frame, msg=(ioName, "frame", frameI))

        tc.assertEqual(len(tx), 0, ioName)