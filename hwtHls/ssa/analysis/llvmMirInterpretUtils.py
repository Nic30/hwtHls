from _io import StringIO
from typing import Callable, Optional, Iterable, Union, Any

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import MachineBasicBlock
from pyDigitalWaveTools.vcd.value_format import LogValueFormatter
from pyDigitalWaveTools.vcd.writer import VcdVarWritingInfo

LlvmMirInstrFunction = Callable[[int, dict[int, HConst]], Optional[MachineBasicBlock]]
# e.g.  def _opcode_X(timeNow: int, regs: list[HConst]) -> Optional[MachineBasicBlock]]:


class VcdLlvmMirBBFormatter(LogValueFormatter):

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: MachineBasicBlock, updater, t: int, out: StringIO):
        num = newVal.getNumber()
        out.write(f"b{num:b} {self.vcdId:s}\n")


class DictWithSetitemListener(dict):

    def __init__(self, __iterable:Iterable, listener:Callable[None, [list, Union[slice, int], Any]]) -> None:
        dict.__init__(self, __iterable)
        self._listener = listener

    def __setitem__(self, __s:Union[slice, int], __o) -> None:
        self._listener(self, __s, __o)
        dict.__setitem__(self, __s, __o)

