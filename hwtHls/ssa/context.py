from typing import Type, Dict


class SsaContext():
    """
    :ivar objCnt: the dictionary of object counts used for name generating
    """

    def __init__(self):
        self.objCnt = 0  # : Dict[Type, int] = {}

    def genName(self, obj):
        prefix = getattr(obj, "_GEN_NAME_PREFIX", "o")
        i = self.objCnt  # .get(obj.__class__, 0)
        self.objCnt = i + 1  # [obj.__class__] = i
        return f"{prefix}{i:d}"
