

class HwIOMeta():

    def __init__(self, mayBecomeBackedge=False, channelInit=(), minBufferCapacity=None):
        self.mayBecomeBackedge = mayBecomeBackedge
        self.channelInit = channelInit
        self.minBufferCapacity = minBufferCapacity
