

class Hls():
    """
    High level synthesiser context
    """

    def __init__(self, freq=None, maxLatency=None, resources=None):
        self.freq = freq
        self.maxLatency = maxLatency
        self.resources = resources

    def read(self, sig):
        """
        Scheduele read operation
        """
        raise NotImplementedError()

    def write(self, what, where):
        """
        Scheduele write operation
        """
        raise NotImplementedError()

    def __enter__(self):
        pass

    def __exit__(self):
        pass
