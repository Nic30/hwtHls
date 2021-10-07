from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


class TmpVariable(RtlSignalBase):

    def __init__(self, origin: RtlSignal):
        self.origin = origin
        self.i = None
        self._const = False

    @property
    def _dtype(self):
        return self.origin._dtype

    @property
    def _name(self):
        return self.__repr__()

    def __repr__(self):
        return f"\"{self.origin}\"_{self.i}"
