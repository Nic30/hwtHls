from typing import Sequence, Union, Literal

from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtSimApi.agents.base import NOP


HlsNetlistSimScalarWord = Union[int, None, HBitsConst, Literal[NOP], tuple["HlsNetlistSimScalarWord", ...]]
HlsNetlistSimScalarInputWords = Sequence[HlsNetlistSimScalarWord]
HlsNetlistSimScalarOutputWords = list[HlsNetlistSimScalarWord]
HlsNetlistSimScalarInputOrOutputWords = Union[HlsNetlistSimScalarInputWords, HlsNetlistSimScalarOutputWords]

HlsNetlistSimStateT = dict[HlsNetNodeOutAny, HBitsConst]
