from typing import Optional, Union

from hwt.hwModule import HwModule
from hwt.simulator.simTestCase import SimTestCase
from hwtLib.abstract.simFrameUtils import SimFrameUtils
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIo import PassTestIo
from tests.passTestIoStream import PassTestIoInStream, PassTestIoOutStream


class PassTestInjectorForStreamHwModule(PassTestInjectorForDInDOutHwModule):
    """
    Modification of PassTestInjectorForDInDOutHwModule which supports stream HwIO like Axi4strea or AvalonST.
    """

    def __init__(self, topToRunTestsOn:HwModule, tc:SimTestCase, streamFrameUtils: SimFrameUtils):
        super().__init__(topToRunTestsOn, tc)
        self.streamFrameUtils = streamFrameUtils

    def bindDataByInOut(self,
        IN_DATA:tuple[Union[PassTestIo, list[int]], ...],
        OUT_DATA_REF:tuple[Union[PassTestIo, list[int]], ...],
        OUT_ITEM_CNT_LIMITS:Optional[tuple[Optional[int], ...]]=None,
        PORT_NAMES=("rx", "tx"),
        rtlPresetBeforeClk=True):
        """
        :note: the data for streams is in bytes or list[int] representing bytes for each frame.
        """
        fus = self.streamFrameUtils
        _IN_DATA = []
        for d in IN_DATA:
            if not isinstance(d, PassTestIo):
                d = PassTestIoInStream(fus, d)
            _IN_DATA.append(d)
        _OUT_DATA_REF = []
        for d in OUT_DATA_REF:
            if not isinstance(d, PassTestIo):
                d = PassTestIoOutStream(fus, d)
            _OUT_DATA_REF.append(d)
        super().bindDataByInOut(_IN_DATA, _OUT_DATA_REF, OUT_ITEM_CNT_LIMITS=OUT_ITEM_CNT_LIMITS,
                                PORT_NAMES=PORT_NAMES, rtlPresetBeforeClk=rtlPresetBeforeClk)

