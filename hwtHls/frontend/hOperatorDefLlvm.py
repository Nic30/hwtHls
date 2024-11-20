from typing import Callable, Optional

from hdlConvertorAst.hdlAst._expr import HdlOpType
from hwt.hdl.operatorDefs import HOperatorDef
from hwtHls.llvm.llvmIr import IRBuilder, Value


class HOperatorDefLlvm(HOperatorDef):

    def __init__(self, evalFn, llvmOperatorConstructor: Callable[[IRBuilder, ...], Value],
                 allowsAssignTo=False,
                 idStr:Optional[str]=None,
                 hdlConvertoAstOp:Optional[HdlOpType]=None):
        HOperatorDef.__init__(self, evalFn, allowsAssignTo=allowsAssignTo, idStr=idStr,
                              hdlConvertoAstOp=hdlConvertoAstOp)
        self.llvmOperatorConstructor = llvmOperatorConstructor
