from typing import Self, Union


class OpRealizationMeta():
    """
    :ivar inputWireDelay: minimal amount of time until next clock cycle
    :ivar inputClkTickOffset: number of cycles from component first cycle when the input is accepted
    :ivar outputWireDelay: time required to stabilize output value after clock cycle
    :ivar outputClkTickOffset: number of clock cycles required for data to reach output
    :ivar mayBeginInFFStoreTime: if true the input end time may be at the end of clock window in FF store time,
        Asserting this true means that the node is not moved to next clock cycle if its node ends in ffstore time.

    :note: inputWireDelay/outputWireDelay unit is second (e.g. for 1ns it will have 1e-9)
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

    def hasOnlyInputWireDelay(self) -> bool:
        return self.inputClkTickOffset == 0 and \
             self.outputWireDelay == 0.0 and \
             self.outputClkTickOffset == 0

    def fitsIntoSingleClockWindow(self):
        return self.inputClkTickOffset == 0 and self.outputClkTickOffset == 0

    def fitsIntoSchedTime(self, clkWindowBudget: "SchedTime", schedResolution: float) -> bool:
        return self.fitsIntoSingleClockWindow() and \
                        (self.inputWireDelay + self.outputWireDelay) / schedResolution < clkWindowBudget

    def __mul__(self, other:int):
        return self.__class__(
            inputClkTickOffset=self.inputClkTickOffset * other,
            inputWireDelay=self.inputWireDelay * other,
            outputWireDelay=self.outputWireDelay * other,
            outputClkTickOffset=self.outputClkTickOffset * other,
            mayBeInFFStoreTime=self.mayBeInFFStoreTime,
        )

    def __add__(self, other:Self):
        """
        :attention: order does matter if OpRealizationMeta spawns over multiple clock windows
        """
        assert isinstance(self.inputClkTickOffset, int), self
        assert isinstance(self.inputWireDelay, (int, float)), self
        assert isinstance(self.outputClkTickOffset, int), self
        assert isinstance(self.outputWireDelay, (int, float)), self
        # [todo] assert that result delay does not exceed the clkPeriod
        if self.fitsIntoSingleClockWindow():
            if other.fitsIntoSingleClockWindow():
                # just sum
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset + other.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay + other.inputWireDelay,
                    outputWireDelay=self.outputWireDelay + other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset + other.outputClkTickOffset,
                    mayBeInFFStoreTime=other.mayBeInFFStoreTime,
                )
            else:
                # self fits into first clock before other
                # inputWireDelay = self total delay
                return self.__class__(
                    inputClkTickOffset=other.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay + self.outputWireDelay + other.inputWireDelay,
                    outputWireDelay=other.outputWireDelay,
                    outputClkTickOffset=other.outputClkTickOffset,
                    mayBeInFFStoreTime=other.mayBeInFFStoreTime,
                )
        else:
            if other.fitsIntoSingleClockWindow():
                # other fits into last clkPeriod of self
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay,
                    outputWireDelay=self.outputWireDelay + other.inputWireDelay + other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset,
                    mayBeInFFStoreTime=other.mayBeInFFStoreTime,
                )
            else:
                # 1 clk overlap of last clk of self with first clk of other
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay,
                    outputWireDelay=other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset + other.inputClkTickOffset + other.outputClkTickOffset,
                    mayBeInFFStoreTime=other.mayBeInFFStoreTime,
                )

    @staticmethod
    def __hasNonDefValue(v: Union[int, float, tuple[Union[int, float]]]):
        return v and (isinstance(v, (float, int)) or sum(v))

    def __repr__(self):
        args = []
        for propName in ("inputWireDelay", "inputClkTickOffset", "outputClkTickOffset", "outputWireDelay"):
            v = getattr(self, propName)
            if self.__hasNonDefValue(v):
                args.append(f"{propName:s}={v}")
        if self.mayBeInFFStoreTime:
            args.append("mayBeInFFStoreTime")

        return f"<{self.__class__.__name__} {', '.join(args):s}>"


EMPTY_OP_REALIZATION = OpRealizationMeta(mayBeInFFStoreTime=True)
UNSPECIFIED_OP_REALIZATION = OpRealizationMeta(
    inputWireDelay=None, outputWireDelay=None,
    inputClkTickOffset=None, outputClkTickOffset=None)


class ComponentRealizationMeta(OpRealizationMeta):
    """
    :ivar requiresInValid: True if he input por requires rtl valid signal which
        marks that the value of input is valid ad the operation
        implemented in this component should be performed
    :ivar mayGenerateInStall: True if the component implementation
        may stall input even if all outputs are not stalled by sink
    :ivar mayGenerateOutStall: mayGenerateOutStall similar as mayGenerateInStall
        just for outputs
    """

    def __init__(self, inputClkTickOffset:int=0,
                 inputWireDelay=0.0, outputWireDelay=0.0,
                 outputClkTickOffset:int=0,
                 mayBeInFFStoreTime:bool=False,
                 requiresInValid: bool=False,
                 mayGenerateInStall: bool=False,
                 mayGenerateOutStall: bool=False
                 ):
        OpRealizationMeta.__init__(
            self,
            inputClkTickOffset,
            inputWireDelay,
            outputWireDelay,
            outputClkTickOffset,
            mayBeInFFStoreTime)
        self.requiresInValid = requiresInValid
        self.mayGenerateInStall = mayGenerateInStall
        self.mayGenerateOutStall = mayGenerateOutStall

    def canBeSynchornizedPurelyByLatency(self):
        return not self.requiresInValid and\
               not self.mayGenerateInStall and \
               not self.mayGenerateOutStall

    @classmethod
    def fromOpRealization(cls, r: OpRealizationMeta):
        return cls(
            r.inputClkTickOffset,
            r.inputWireDelay,
            r.outputWireDelay,
            r.outputClkTickOffset,
            r.mayBeInFFStoreTime)

