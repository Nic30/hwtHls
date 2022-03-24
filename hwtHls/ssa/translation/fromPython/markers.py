from typing import Union

from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.value import SsaValue


class PythonBytecodeInPreproc():
    """
    A container of hw object marked that the immediate store is store of preproc variable only
    """

    def __init__(self, ref: Union[SsaValue, HValue, RtlSignal]):
        self.ref = ref
    
    def __iter__(self):
        """
        Used in in UNPACK_SEQUENCE
        """
        for i in self.ref:
            yield PythonBytecodeInPreproc(i)

