from typing import Union, Tuple

from hwt.hwIO import HwIO
from hwt.hwModule import HwModule
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName as _getInterfaceName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup


def HwIO_getName(parentHwModule: HwModule, hwIO: Union[HwIO, Tuple[HwIO]]) -> str:
    if isinstance(hwIO, (MultiPortGroup, BankedPortGroup)):
        return "|".join([HwIO_getName(parentHwModule, sHwIO) if i == 0 else sHwIO._name for i, sHwIO in enumerate(hwIO)])
    else:
        return _getInterfaceName(parentHwModule, hwIO)
