from typing import Union, Tuple

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName as _getInterfaceName
from hwt.synthesizer.unit import Unit
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup


def getInterfaceName(parentUnit: Unit, io: Union[Interface, Tuple[Interface]]) -> str:
    if isinstance(io, (MultiPortGroup, BankedPortGroup)):
        return "|".join([getInterfaceName(parentUnit, intf) if i == 0 else intf._name for i, intf in enumerate(io)])
    else:
        return _getInterfaceName(parentUnit, io)
