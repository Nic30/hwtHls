from typing import Union, Tuple

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName as _getInterfaceName
from hwt.synthesizer.unit import Unit


def getInterfaceName(parentUnit: Unit, io: Union[Interface, Tuple[Interface]]) -> str:
    if isinstance(io, tuple):
        return "|".join([getInterfaceName(parentUnit, intf) if i == 0 else intf._name for i, intf in enumerate(io)])
    else:
        return _getInterfaceName(parentUnit, io)
