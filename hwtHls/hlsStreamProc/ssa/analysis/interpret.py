from collections import deque
from typing import Dict, Optional, Union

from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.instr import SsaInstr
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtHls.hlsStreamProc.statements import HlsStreamProcWrite


class SsaInterpretVarStore(Dict[Union[RtlSignal, HValue, SsaPhi], HValue]):

    def __setitem__(self, key, value):
        if isinstance(key, SsaPhi):
            key = key.dst
        dict.__setitem__(self, key, value)

    def __getitem__(self, key):
        if isinstance(key, SsaPhi):
            key = key.dst
        return dict.__getitem__(self, key)


class SsaInterpret():

    def __init__(self, io:Dict[Interface, deque], start_block: SsaBasicBlock):
        self.io = io
        self.variables = SsaInterpretVarStore()
        self.predecessor: Optional[SsaBasicBlock] = start_block
        self.current_block: SsaBasicBlock = start_block

    def eval_block(self):
        pred = self.predecessor
        current = self.current_block
        variables = self.variables
        if pred is not None:
            for phi in current.phis:
                phi: SsaPhi
                phi_value_found = False
                for (v, bb) in phi.operands:
                    if bb is pred:
                        if not isinstance(v, HValue):
                            v = variables[v]
                        variables[phi] = v
                        phi_value_found = True
                        break
                assert phi_value_found, (phi, phi.operands, pred)


        for code in current.body:
            if isinstance(code, HlsStreamProcWrite):
                code: HlsStreamProcWrite
                channel = self.io.get(code, None)
                if channel is None:
                    channel = deque()
                    self.io[code.dst] = channel
                v = code.operands[0]
                if not isinstance(v, HValue):
                    v = variables[v]
                channel.append(v)

            elif isinstance(code, SsaInstr):
                code: SsaInstr
                v = code.operands
                v = code.operator._evalFn(*(o if isinstance(o, HValue) else variables[o] for o in v[1]))
                v = variables[v]
                variables[code] = v

            else:
                raise NotImplementedError()

        self.predecessor = current
        target_found = False
        for c, target in current.successors.targets:
            if c is None or variables[c]:
                self.current_block = target
                target_found = True
                break
        assert target_found, current

    def __iter__(self):
        return self

    def __next__(self):
        self.eval_block()
