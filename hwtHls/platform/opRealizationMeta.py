

class OpRealizationMeta():
    """
    :ivar inputWireDelay: minimal amount of time until next clock cycle
    :ivar inputClkTickOffset: number of cycles from component first cycle when the input is accepted
    :ivar outputWireDelay: time required to stabilize output value after clock cycle
    :ivar outputClkTickOffset: number of clock cycles required for data to reach output
    """

    def __init__(self, inputClkTickOffset=0, inputWireDelay=0.0, outputWireDelay=0.0,
                 outputClkTickOffset=0):
        self.inputWireDelay = inputWireDelay
        self.inputClkTickOffset = inputClkTickOffset
        self.outputWireDelay = outputWireDelay
        self.outputClkTickOffset = outputClkTickOffset


EMPTY_OP_REALIZATION = OpRealizationMeta()
UNSPECIFIED_OP_REALIZATION = OpRealizationMeta(
    inputWireDelay=None, outputWireDelay=None,
    inputClkTickOffset=None, outputClkTickOffset=None)
