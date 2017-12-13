class FsmNode():
    """
        -------
 lValid>|     |>rValid
        |     |
 lReady<|     |<rReady
        -------

    """

    def __init__(self):
        self.ldata = None
        self.lReady = None
        self.lValid = None

        self.rdata = None
        self.rReady = None
        self.rValid = None

    def isClkDependent(self):
        raise NotImplementedError()