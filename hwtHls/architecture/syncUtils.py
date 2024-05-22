from typing import Tuple, Union, Literal, Sequence

from hwt.hwIOs.std import HwIORdVldSync, HwIODataRdVld, \
    HwIOSignal, HwIOBramPort_noClk, HwIORdSync, HwIOVldSync
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIO import HwIO
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.io.portGroups import getFirstInterfaceInstance, MultiPortGroup, \
    BankedPortGroup
from hwtLib.amba.axi_common import Axi_hs
from hwtLib.handshaked.streamNode import ValidReadyTuple

SyncOfInterface = Union[HwIODataRdVld, HwIORdVldSync, Axi_hs, ValidReadyTuple]


def HwIO_getSync(
            hwIO: Union[HwIORdVldSync, HwIORdSync, HwIOVldSync, RtlSignalBase, HwIOSignal, SyncOfInterface]
            ) -> SyncOfInterface:
    if isinstance(hwIO, (HwIODataRdVld, HwIORdVldSync, Axi_hs)):
        return hwIO
    else:
        return HwIO_getSyncTuple(hwIO)


def HwIO_getSyncTuple(
            hwIO: Union[HwIORdVldSync, HwIORdSync, HwIOVldSync, RtlSignalBase, HwIOSignal, ValidReadyTuple]
            ) -> ValidReadyTuple:
    if isinstance(hwIO, tuple):
        # expect ValidReadyTuple
        assert len(hwIO) == 2, hwIO
        assert isinstance(hwIO[0], (int, RtlSignalBase, HwIOSignal)), hwIO
        assert isinstance(hwIO[1], (int, RtlSignalBase, HwIOSignal)), hwIO
        return hwIO
    elif isinstance(hwIO, Axi_hs):
        return (hwIO.valid, hwIO.ready)
    elif isinstance(hwIO, (HwIODataRdVld, HwIORdVldSync)):
        return (hwIO.vld, hwIO.rd)
    elif isinstance(hwIO, HwIOVldSync):
        return (hwIO.vld, 1)
    elif isinstance(hwIO, HwIOBramPort_noClk):
        return (hwIO.en, 1)
    elif isinstance(hwIO, HwIORdSync):
        return (1, hwIO.rd)
    elif isinstance(hwIO, (RtlSignalBase, HwIOSignal, HwIOStruct)):
        return (1, 1)
    else:
        raise TypeError("Unknown synchronization of ", hwIO)


def HwIO_getSyncSignals(hwIO: Union[HwIO, RtlSignal, MultiPortGroup, BankedPortGroup]) -> Tuple[HwIO, ...]:
    hwIO = getFirstInterfaceInstance(hwIO)
    if isinstance(hwIO, Axi_hs):
        return (hwIO.valid, hwIO.ready)
    elif isinstance(hwIO, HwIORdVldSync):
        return (hwIO.vld, hwIO.rd)
    elif isinstance(hwIO, (RtlSignal, HwIOSignal, HwIOStruct)):
        return ()
    elif isinstance(hwIO, HwIOVldSync):
        return (hwIO.vld,)
    elif isinstance(hwIO, HwIORdSync):
        return (hwIO.rd,)
    elif isinstance(hwIO, HwIOBramPort_noClk):
        return (hwIO.en,)
    else:
        raise NotImplementedError(hwIO)

