

class SsaContext():
    """
    :ivar objCnt: the number used to generated unique object id
    """

    def __init__(self):
        self.objCnt = 0

    def genName(self, obj):
        prefix = getattr(obj, "_GEN_NAME_PREFIX", "o")
        i = self.objCnt  # .get(obj.__class__, 0)
        self.objCnt = i + 1  # [obj.__class__] = i
        return f"{prefix}{i:d}"
