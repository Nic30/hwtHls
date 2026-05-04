from typing import Optional

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.hwrange import hwrange
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtLib.types.ctypes import uint64_t
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier


class PipelinedMultiplierSequential(_BaseALU1HwModule):

    @override
    def hwConfig(self):
        _BaseALU1HwModule.hwConfig(self)
        self.T = uint64_t
        self.T_LHS: Optional[HBits] = HwParam(None)
        self.T_RHS: Optional[HBits] = HwParam(None)

    @override
    def hwDeclr(self) -> None:
        PipelinedMultiplier.hwDeclr(self)

    @override
    def _getMaxIterationCount(self):
        rhsT = self.T if self.T_RHS is None else self.T_RHS
        return rhsT.bit_length()

    @override
    @hlsBytecode
    def aluFn(self, inp) -> None:
        """
        Same as :meth:`hwImplChained` but the steps use shared resources.
        https://courses.csail.mit.edu/6.111/f2008/handouts/L09.pdf
        .. code-block::
            Init: P=0, load A and B
            Repeat M times {
                P += (BLSB==1 ? A : 0)
                {P, B} >>= 1
            }
            Done: (N+M)-bit result in {P, B}
        """
        A = inp.a._cast_sign(False)
        B = inp.b._cast_sign(False)
        N = A._dtype.bit_length()
        M = B._dtype.bit_length()
        P = HBits(N + M).from_py(0)
        for _ in hwrange(M):
            if B[0]:
                P += A._ext(P._dtype.bit_length())
            B = Concat(P[0], B[:1])
            P >>= 1
            self._getLoopMeta()

        return Concat(P, B)[self.T.bit_length():]._reinterpret_cast(self.T)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
    m = PipelinedMultiplierSequential()
    # m.UNROLL_FACTOR = 4
    m.T = HBits(4)
    m.CLK_FREQ = int(100e6)
    p = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                   llvmCliArgs=[
                    #   LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::BitwidthReductionPass")
                       # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
                    ]
                   )
    print(to_rtl_str(m, target_platform=p))  # {HlsDebugBundle.DBG_23_arch}

