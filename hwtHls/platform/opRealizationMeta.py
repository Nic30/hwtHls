

class OpRealizationMeta():
    """
    :ivar inputWireDelay: minimal amount of time until next clock cycle
    :ivar inputClkTickOffset: number of cycles from component first cycle when the input is accepted
    :ivar outputWireDelay: time required to stabilize output value after clock cycle
    :ivar outputClkTickOffset: number of clock cycles required for data to reach output
    :ivar mayBeginInFFStoreTime: if true the input end time may be at the end of clock window in FF store time,
        Asserting this true means that the node is not moved to next clock cycle if its node ends in ffstore time.

    :note: all times are relative to scheduledZero of HlsNetNode.
        inputWireDelay>0 means the input is before scheduledZero
        inputWireDelay<0 means the input is after scheduledZero
        outputWireDelay>0 means output is after scheduledZero
        etc.
    """

    def __init__(self, inputClkTickOffset:int=0, inputWireDelay=0.0, outputWireDelay=0.0,
                 outputClkTickOffset:int=0, mayBeInFFStoreTime:bool=False):
        self.inputWireDelay = inputWireDelay
        self.inputClkTickOffset = inputClkTickOffset
        self.outputWireDelay = outputWireDelay
        self.outputClkTickOffset = outputClkTickOffset
        self.mayBeInFFStoreTime = mayBeInFFStoreTime


EMPTY_OP_REALIZATION = OpRealizationMeta(mayBeInFFStoreTime=True)
UNSPECIFIED_OP_REALIZATION = OpRealizationMeta(
    inputWireDelay=None, outputWireDelay=None,
    inputClkTickOffset=None, outputClkTickOffset=None)
