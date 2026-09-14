from typing import Sequence, Optional

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue


# :attention: this should be done automatically when using [] operator on any python object with HBits value
# :todo: remove this
@hwt_expr_producer
def selectUsingCasesWithCondition(cases: Sequence[tuple[Optional[AnyHBitsValue], AnyHBitsValue]], defaultVal=None) -> AnyHBitsValue:
    res = defaultVal
    for c, val in reversed(cases):
        assert c is not None
        res = c._ternary(val, res)

    return res

