from hwt.synthesizer.utils import toRtl
from hwtHls.vivadoHLS.unit import VivadoHLSUnit


class ExactMatcher(VivadoHLSUnit):
    _top = "exactMatch"
    _project = "exactMatcherVivadoHls"


if __name__ == "__main__":
    print(toRtl(ExactMatcher))
    print(ExactMatcher._entity)
