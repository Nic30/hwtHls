from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


class HlsTmpVariable(RtlSignalBase):
    """
    An object which spilifies generating of temporary variables for a signal sinstance.
    """
    def __init__(self, name: str, origin: RtlSignal):
        self.name = name
        self.origin = origin
        self._const = False
        self.hidden = False

    @property
    def _dtype(self):
        return self.origin._dtype

    @property
    def _name(self):
        return self.__repr__()

    def __repr__(self):
        return self.name
