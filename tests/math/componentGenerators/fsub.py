from hwt.hdl.operatorDefs import HwtOps
from tests.math.componentGenerators.fadd import ComponentGeneratorFADD
from tests.math.fp.fpadd import IEEE754FpAdd
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from tests.math.fp.fptypes import IEEE754FpValue


@hlsBytecode
def IEEE754FpSub(a: IEEE754FpValue, b: IEEE754FpValue, isSim=False):
    b.sign = ~b.sign
    return PyBytecodeInline(IEEE754FpAdd)(a, b, isSim=isSim)


class ComponentGeneratorFSUB(ComponentGeneratorFADD):
    HWT_OPERATOR = HwtOps.SUB
    FP_OPERATOR_FN = staticmethod(IEEE754FpSub)

