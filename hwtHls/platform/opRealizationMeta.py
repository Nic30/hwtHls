from typing import Self, Union

from dataclasses import dataclass
from hwtHls.netlist.scheduler.clk_math import RealTime


@dataclass(frozen=True)
class OpRealizationMeta():
    """
    :ivar inputWireDelay: minimal amount of time until next clock cycle
    :ivar inputClkTickOffset: number of cycles from component first cycle when the input is accepted
    :ivar outputWireDelay: time required to stabilize output value after clock cycle
    :ivar outputClkTickOffset: number of clock cycles required for data to reach output
    :ivar mayBeginInFFStoreTime: if true the input end time may be at the end of clock window in FF store time,
        Asserting this true means that the node is not moved to next clock cycle if its node ends in ffstore time.
    
    :attention: all times are floats in seconds e.g. 1e-9 for 1ns, for use during scheduling
        this has to be converted to :obj:`hwtHls.netlist.scheduler.clk_math.SchedTime`
    
    :note: if isMulticlock
          scheduledZero % clkPeriod == 0
           inTime = scheduledZero -  inputClkTickOffset*clkPeriod -  inputWireDelay
          outTime = scheduledZero + outputClkTickOffset*clkPeriod + outputWireDelay
        else
           inTime = scheduledZero -  inputWireDelay
          outTime = scheduledZero + outputWireDelay

    :note: inputWireDelay/outputWireDelay unit is second (e.g. for 1ns it will have 1e-9)
    :note: all times are relative to scheduledZero of HlsNetNode.
        inputWireDelay>0 means the input is before scheduledZero
        inputWireDelay<0 means the input is after scheduledZero
        outputWireDelay>0 means output is after scheduledZero
        etc.
    """
    inputClkTickOffset:int | tuple[int] = 0
    inputWireDelay:RealTime | tuple[RealTime] = 0.0
    outputWireDelay:RealTime | tuple[RealTime] = 0.0
    outputClkTickOffset:int | tuple[int] = 0
    isAllowedInFFStoreTime:bool = False
    isMulticlock: bool = False

    _PROPERTY_NAMES = ("inputWireDelay", "inputClkTickOffset", "outputClkTickOffset", "outputWireDelay")
    _FLAG_NAMES = ("isAllowedInFFStoreTime", "isMulticlock")

    # def __new__(cls, inputClkTickOffset:int=0, inputWireDelay=0.0, outputWireDelay=0.0,
    #            outputClkTickOffset:int=0, isAllowedInFFStoreTime:bool=False):
    #    return super(OpRealizationMeta, cls).__new__(cls, inputClkTickOffset, inputWireDelay, outputWireDelay,
    #                           outputClkTickOffset, isAllowedInFFStoreTime)
        # self.inputWireDelay = inputWireDelay
        # self.inputClkTickOffset = inputClkTickOffset
        # self.outputWireDelay = outputWireDelay
        # self.outputClkTickOffset = outputClkTickOffset
        # self.isAllowedInFFStoreTime = isAllowedInFFStoreTime
    def mutated(self, inputClkTickOffset=None,
                inputWireDelay=None, outputWireDelay=None,
                outputClkTickOffset=None, isAllowedInFFStoreTime=None,
                isMulticlock=None) -> Self:
        if inputClkTickOffset is None:
            inputClkTickOffset = self.inputClkTickOffset
        if inputWireDelay is None:
            inputWireDelay = self.inputWireDelay
        if outputWireDelay is None:
            outputWireDelay = self.outputWireDelay
        if outputClkTickOffset is None:
            outputClkTickOffset = self.outputClkTickOffset
        if isAllowedInFFStoreTime is None:
            isAllowedInFFStoreTime = self.isAllowedInFFStoreTime
        if isMulticlock is None:
            isMulticlock = self.isMulticlock
        return self.__class__(inputClkTickOffset=inputClkTickOffset,
                              inputWireDelay=inputWireDelay,
                              outputWireDelay=outputWireDelay,
                              outputClkTickOffset=outputClkTickOffset,
                              isAllowedInFFStoreTime=isAllowedInFFStoreTime,
                              isMulticlock=isMulticlock)

    def hasOnlyInputWireDelay(self) -> bool:
        return self.inputClkTickOffset == 0 and \
             self.outputWireDelay == 0.0 and \
             self.outputClkTickOffset == 0

    def fitsIntoSingleClockWindow(self):
        """
        :note: Even if all IO fits a single clock window the component
            can still cause stalls and have an internal state.
        """
        if self.isMulticlock:
            return self.inputClkTickOffset == 0 and self.outputClkTickOffset == -1
        else:
            assert self.inputClkTickOffset == 0 and self.outputClkTickOffset == 0, self
            return True

    def fitsIntoSchedTime(self, clkWindowBudget: "SchedTime", schedResolution: RealTime) -> bool:
        return self.fitsIntoSingleClockWindow() and \
                        (self.inputWireDelay + self.outputWireDelay) / schedResolution < clkWindowBudget

    def __mul__(self, other:int):
        return self.__class__(
            inputClkTickOffset=self.inputClkTickOffset * other,
            inputWireDelay=self.inputWireDelay * other,
            outputWireDelay=self.outputWireDelay * other,
            outputClkTickOffset=self.outputClkTickOffset * other,
            isAllowedInFFStoreTime=self.isAllowedInFFStoreTime,
            isMulticlock=self.isMulticlock,
        )

    def __add__(self, other:Self):
        """
        :attention: order does matter if OpRealizationMeta spawns over multiple clock windows
        """
        assert isinstance(self.inputClkTickOffset, int), self
        assert isinstance(self.inputWireDelay, (int, RealTime)), self
        assert isinstance(self.outputClkTickOffset, int), self
        assert isinstance(self.outputWireDelay, (int, RealTime)), self
        # [todo] assert that result delay does not exceed the clkPeriod
        if self.fitsIntoSingleClockWindow():
            if other.fitsIntoSingleClockWindow():
                # just sum
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset + other.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay + other.inputWireDelay,
                    outputWireDelay=self.outputWireDelay + other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset + other.outputClkTickOffset,
                    isAllowedInFFStoreTime=other.isAllowedInFFStoreTime,
                    isMulticlock=False,
                )
            else:
                # self fits into first clock before other
                # inputWireDelay = self total delay
                return self.__class__(
                    inputClkTickOffset=other.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay + self.outputWireDelay + other.inputWireDelay,
                    outputWireDelay=other.outputWireDelay,
                    outputClkTickOffset=other.outputClkTickOffset,
                    isAllowedInFFStoreTime=other.isAllowedInFFStoreTime,
                    isMulticlock=True,
                )
        else:
            if other.fitsIntoSingleClockWindow():
                # other fits into last clkPeriod of self
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay,
                    outputWireDelay=self.outputWireDelay + other.inputWireDelay + other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset,
                    isAllowedInFFStoreTime=other.isAllowedInFFStoreTime,
                    isMulticlock=True,
                )
            else:
                # 1 clk overlap of last clk of self with first clk of other
                return self.__class__(
                    inputClkTickOffset=self.inputClkTickOffset,
                    inputWireDelay=self.inputWireDelay,
                    outputWireDelay=other.outputWireDelay,
                    outputClkTickOffset=self.outputClkTickOffset + other.inputClkTickOffset + other.outputClkTickOffset,
                    isAllowedInFFStoreTime=other.isAllowedInFFStoreTime,
                    isMulticlock=True,
                )

    @staticmethod
    def __hasNonDefValue(v: Union[int, RealTime, tuple[Union[int, RealTime]]]):
        return v and (isinstance(v, (RealTime, int)) or sum(v))

    def __repr__(self):
        args = []
        for propName in self._PROPERTY_NAMES:
            v = getattr(self, propName)
            if self.__hasNonDefValue(v):
                args.append(f"{propName:s}={v}")

        for propName in self._FLAG_NAMES:
            v = getattr(self, propName)
            if v:
                args.append(propName)

        return f"<{self.__class__.__name__} {', '.join(args):s}>"


EMPTY_OP_REALIZATION = OpRealizationMeta(isAllowedInFFStoreTime=True)


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
    _FLAG_NAMES = (*OpRealizationMeta._FLAG_NAMES, "requiresInValid", "mayGenerateInStall", "mayGenerateOutStall")

    def __init__(self, inputClkTickOffset:int=0,
                 inputWireDelay=0.0, outputWireDelay=0.0,
                 outputClkTickOffset:int=0,
                 isAllowedInFFStoreTime:bool=False,
                 isMulticlock:bool=False,
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
            isAllowedInFFStoreTime,
            isMulticlock)
        self.requiresInValid = requiresInValid
        self.mayGenerateInStall = mayGenerateInStall
        self.mayGenerateOutStall = mayGenerateOutStall

    def mutated(self, inputClkTickOffset=None,
                inputWireDelay=None, outputWireDelay=None,
                outputClkTickOffset=None, isAllowedInFFStoreTime=None,
                isMulticlock=None,
                requiresInValid=None,
                mayGenerateInStall=None,
                mayGenerateOutStall=None) -> Self:
        if inputClkTickOffset is None:
            inputClkTickOffset = self.inputClkTickOffset
        if inputWireDelay is None:
            inputWireDelay = self.inputWireDelay
        if outputWireDelay is None:
            outputWireDelay = self.outputWireDelay
        if outputClkTickOffset is None:
            outputClkTickOffset = self.outputClkTickOffset
        if isAllowedInFFStoreTime is None:
            isAllowedInFFStoreTime = self.isAllowedInFFStoreTime
        if isMulticlock is None:
            isMulticlock = self.isMulticlock
        if requiresInValid is None:
            requiresInValid = self.requiresInValid
        if mayGenerateInStall is None:
            mayGenerateInStall = self.mayGenerateInStall
        if mayGenerateOutStall is None:
            mayGenerateOutStall = self.mayGenerateOutStall
        return self.__class__(inputClkTickOffset=inputClkTickOffset,
                              inputWireDelay=inputWireDelay,
                              outputWireDelay=outputWireDelay,
                              outputClkTickOffset=outputClkTickOffset,
                              isAllowedInFFStoreTime=isAllowedInFFStoreTime,
                              isMulticlock=isMulticlock,
                              requiresInValid=requiresInValid,
                              mayGenerateInStall=mayGenerateInStall,
                              mayGenerateOutStall=mayGenerateOutStall)

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
            r.isAllowedInFFStoreTime,
            r.isMulticlock)

