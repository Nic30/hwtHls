#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld, HwIOStruct
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.scope import HlsScope
from tests.frontend.stmWhile import HlsPythonHwWhile0a
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier


class _TestMulHL(_BaseALU1HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ: int = HwParam(int(100e6))
        self.T: HBits = HwParam(HBits(64))
        self.T_LHS: Optional[HBits] = HwParam(None)
        self.T_RHS: Optional[HBits] = HwParam(None)
        self.RHS_IS_LHS: bool = HwParam(False)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructRdVld] = HwParam(HwIOStructRdVld)

    @override
    def hwDeclr(self):
        PipelinedMultiplier.hwDeclr(self)

    def mainThread(self, hls: HlsScope):
        w = self.T.bit_length()
        while b1:
            inp = hls.read(self.data_in).data
            if self.RHS_IS_LHS:
                res = inp.a._ext(w) * inp.a._ext(w)
            else:
                res = inp.a._ext(w) * inp.b._ext(w)
            hls.write(res, self.data_out)

    def hwImpl(self):
        HlsPythonHwWhile0a.hwImpl(self)


if __name__ == "__main__":
    from hwt.serializer.verilog import VerilogSerializer
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = _TestMulHL()
    m.T = HBits(32, signed=False)
    m.T_LHS = m.T_RHS = HBits(24, signed=False)
    
    m.RHS_IS_LHS = False
    m.IN_CHANNEL_TYPE = m.OUT_CHANNEL_TYPE = HwIOStruct
    m.CLK_FREQ = int(100e6)
    p = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                   # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED]
    )
    # installFpComponentGenerators(p)
    # 
    print(to_rtl_str(m, serializer_cls=VerilogSerializer, target_platform=p))  # {HlsDebugBundle.DBG_23_arch}
