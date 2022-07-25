from types import FunctionType
from typing import Union

from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.value import SsaValue


class PyBytecodeInPreproc():
    """
    A marker of hw object that the immediate store is store of preproc variable only.


    Usage:
    
    .. code-block:: Python


        x = PyBytecodeInPreproc(uint8_t.from_py(0))
        # x is now variable holding original uint8_t value no extraction
        #   to hardware was performed and x stays only in preprocessor
        # :note: it is sufficient to mark variable only once in first initialization

    """

    def __init__(self, ref: Union[SsaValue, HValue, RtlSignal]):
        self.ref = ref
    
    def __iter__(self):
        """
        Used in in UNPACK_SEQUENCE
        """
        for i in self.ref:
            yield PyBytecodeInPreproc(i)


class PyBytecodeInline():
    """
    Inline function body to a callsite.

    Usage:
    
    .. code-block:: Python

        PyBytecodeInline(fn)(args)
        
        # or

        @PyBytecodeInline
        def fn(args):
            pass
            
        fn(args)
    
    """

    def __init__(self, ref: FunctionType):
        self.ref = ref

   
class PyBytecodePreprocDivergence():
    """
    Marks that the condition causes divergence in preprocessor and each dependent code blocks must be duplicated for each path.
    :note: required only for a divergence where value of preprocessor variables is resolved from HW evaluated condition
    Usage:
    
    .. code-block:: Python
        
        x = uint8_t.from_py(0) # variable realized in hardware
        if PyBytecodePreprocDivergence(x):
            i = 0
        else:
            i = 1
        use(i) # this code block will be duplicated for each possible value of i variable
               # without :class:`~.PyBytecodePreprocDivergence` the i variable would have only
               # value 0 because the successor blocks would be generated only for a first variant
    
    
    :note: required only for a divergence where value of preprocessor variables is resolved from HW evaluated condition
    
    """

    def __init__(self, cond: Union[SsaValue, HValue, RtlSignal]):
        assert isinstance(cond, (SsaValue, HValue, RtlSignal)), (cond, "Must be hardware evaluated expression otherwise this marker is useless")
        self.cond = cond
