import math
from typing import Type

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld, HwIOStruct, \
    HdlType_to_HwIO
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.serializer.mode import serializeParamsUniq
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerator import HlsErrorHighlyInefficientImplementation
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLLVMLoopUnroll
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scope import HlsScope


@serializeParamsUniq
class _BaseALU1HwModule(HwModule):
    """
    Universal HwModule wrapper around point unary operator function.
    :ivar CLK_FREQ: target frequency
    :ivar MAIN_FN_META: additional HLS metadata for main function
    :ivar CHECK_FOR_INEFFICIENCY: if true and the module is configured
        in some highly sub-optimal the exception is raised
    """

    def hwConfig(self) -> None:
        self.T: HdlType = HwParam(None)
        self.CLK_FREQ: int = HwParam(int(20e6))
        self.UNROLL_FACTOR = HwParam(1)
        self.MAIN_FN_META = HwParam(None)
        self.CHECK_FOR_INEFFICIENCY: bool = HwParam(True)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructRdVld)

    def _setIoChannelTypes(self, realization: OpRealizationMeta):
        if not realization.fitsIntoSingleClockWindow():
            # contains FSM and read, write should be in different state and there should not
            # be any path from control of output to control of input and reverse
            self.IN_CHANNEL_TYPE = HwIOStructRdVld
            self.OUT_CHANNEL_TYPE = HwIOStructRdVld
        elif self._isFullyUnrolled():
            # synchronization can be implemented entirely outside of this module
            self.IN_CHANNEL_TYPE = HwIOStruct
            self.OUT_CHANNEL_TYPE = HwIOStruct
        else:
            # module can receive input data in the same clock it provides output
            # However the input must be supplied from previous stage otherwise
            # parent pipeline stage deadlocks because it waits for another input for this until before
            # it consumes the output from this module
            # * the parent stage is virtually split into two by this unit, the input part must
            #   work asynchronously from output part to prevent deadlock

            # * input valid is required in input of parent can stall
            # * output valid is required to recognize this module latency by parent
            # * output ready is required if this parent or any successor pipeline stage can stall
            self.IN_CHANNEL_TYPE = HwIOStructVld
            self.OUT_CHANNEL_TYPE = HwIOStructRdVld

    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert t is not None, self

        self._addDataInDataOut(t, t)

    def _addDataInDataOut(self, inT: HdlType, outT: HdlType):
        if self.IN_CHANNEL_TYPE is HwIOStruct:
            self.data_in: HwIOStruct = HdlType_to_HwIO().apply(inT)
        else:
            self.data_in: HwIOStructVld = self.IN_CHANNEL_TYPE()
            self.data_in.T = inT

        if self.OUT_CHANNEL_TYPE is HwIOStruct:
            self.data_out: HwIOStruct = HdlType_to_HwIO().apply(outT)._m()
        else:
            self.data_out: HwIOStructRdVld = self.OUT_CHANNEL_TYPE()._m()
            self.data_out.T = outT

    @staticmethod
    def _getTypeOfIo(io):
        try:
            return io._dtype
        except AttributeError:
            return io.T

    def _getMaxIterationCount(self):
        return 1

    def _isFullyUnrolled(self):
        ITERATION_CNT = self._getMaxIterationCount()
        assert self.UNROLL_FACTOR <= ITERATION_CNT, "Using larger UNROLL_FACTOR does not bring any benefit"
        return self.UNROLL_FACTOR == ITERATION_CNT

    def _getLoopMeta(self):
        UNROLL_FACTOR = self.UNROLL_FACTOR
        if UNROLL_FACTOR > 1:
            return PyBytecodeLLVMLoopUnroll(True, UNROLL_FACTOR,
                # followup_unrolled=PyBytecodeLoopFlattenUsingIf()
                )
        else:
            return None
            # return PyBytecodeLoopFlattenUsingIf()

    def _backupTiming(self, hls: HlsScope, isFullyUnrolled: bool):
        inputClkTickOffset = math.inf
        inputWireDelay = math.inf
        outputClkTickOffset = 0
        outputWireDelay = 0
        for t in hls._threads:
            netlist: HlsNetlistCtx = t.netlist
            clkPeriod = netlist.normalizedClkPeriod
            timeResolution = netlist.scheduler.resolution
            for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
                if isinstance(n, HlsNetNodeRead):
                    if n.src is self.data_in:
                        t = min(n.scheduledOut)
                        inputWireDelay = min(inputWireDelay, (t % clkPeriod))
                        inputClkTickOffset = min(inputClkTickOffset, t // clkPeriod)

                elif isinstance(n, HlsNetNodeWrite):
                    if n.dst is self.data_out:
                        t = max(n.scheduledIn)
                        outputWireDelay = max(outputWireDelay, (t % clkPeriod))
                        outputClkTickOffset = max(outputClkTickOffset, t // clkPeriod)

        self.hlsOpRealizationMeta = OpRealizationMeta(
            inputClkTickOffset,
            inputWireDelay * timeResolution,
            outputWireDelay * timeResolution,
            outputClkTickOffset  # + (0 if isFullyUnrolled else 1)
            # +1 because the output is in fist clk, but after n iterations
            # and thus data_in read and data_out write can not happen at once
        )
        return outputClkTickOffset

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        # hls.hwIOMeta[self.data_in] = HwIOMeta(mayBecomeBackedge, channelInit)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()
        outputClkTickOffset = self._backupTiming(hls, self._isFullyUnrolled())

        if self.CHECK_FOR_INEFFICIENCY and\
              outputClkTickOffset > 0 and\
              self.UNROLL_FACTOR != 1 and\
              not self._isFullyUnrolled():
            raise HlsErrorHighlyInefficientImplementation("UNROLL_FACTOR forces sequential implementation"
                                                          " to have loop with increased latency and resources",
                                                          self.UNROLL_FACTOR, self)

    @hlsBytecode
    def aluFn(self, inp) -> RtlSignal:
        raise NotImplementedError("Implement this in child class", self.__class__, self)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        self.MAIN_FN_META
        if self._isFullyUnrolled() or (self.IN_CHANNEL_TYPE == HwIOStruct and self.OUT_CHANNEL_TYPE == HwIOStruct):
            while b1:
                # main loop for the case this is just strait pipeline
                inp = hls.read(self.data_in).data
                resTmp = PyBytecodeInline(self.aluFn)(inp)
                hls.write(resTmp, self.data_out, mayBecomeFlushable=False)
        else:
            # version with read rotated at the end of the loop to allow read of input in the same
            # cycle when the data is written to output
            inp = self._getTypeOfIo(self.data_in).from_py(None)
            inpValid = b0
            while b1:
                if inpValid:
                    # # read input at the end of the loop to be able receive it in the same clock as output is produced
                    # while ~inpValid:
                    #    # [fixme] This is necessary because the if inp.valid would not prevent the execution of
                    #    #         functional to execute, (just if r.valid in the main loop would not be sufficient as r.valid
                    #    #         would travel to next loop iteration as data on channel with non blocking read.)
                    #    #         That would not be a problem, the functional unit would execute and data would be correctly
                    #    #         dropped at the end. However the latency of unit would be added as delay to this loop.
                    #    #         This could cause serious performance loss and it is prevented by this loop,
                    #    r = hls.read(self.data_in, blocking=False)
                    #    inp = r.data
                    #    inpValid = r.valid
                    # # loop for the case where functional unit has some internal delay.
                    # The output of the lop
                    # if inpValid:
                    resTmp = PyBytecodeInline(self.aluFn)(inp)
                    hls.write(resTmp, self.data_out, mayBecomeFlushable=False)

                r = hls.read(self.data_in, blocking=False)
                inp = r.data
                inpValid = r.valid

        # while b1:
        #    # data_in = MultiPortGroup((self.data_in, self.data_in)) # :note: workaround to allow 2 reads in same clock cycle
        #    # data_in = self.data_in
        #    ## non blocking read to avoid comb loop from data_in.valid to data_out.valid
        #    ## as it cancels the new data_in word when writing res
        #    r = hls.read(self.data_in) # , blocking=False
        #    inp = r.data
        #    # main loop for the case this is just strait pipeline
        #    res = FN(inp.dividend, inp.divisor,
        #             inp.signed if self.HAS_RUNTIME_SIGN else self.T.signed,
        #             loopPragmaGetter=self._getLoopMeta)
        #    resTmp = outT.from_py(None)
        #    resTmp.quotient = res[0]
        #    resTmp.remainder = res[1]
        #    hls.write(resTmp, self.data_out, mayBecomeFlushable=False)
        #    # inp = hls.read(data_in).data
        #
        # if self._isFullyUnrolled() or (self.IN_CHANNEL_TYPE == HwIOStruct and self.OUT_CHANNEL_TYPE == HwIOStruct):
        # while b1:
        #    # main loop for the case this is just strait pipeline
        #    inp = hls.read(self.data_in).data
        #    res = PyBytecodeInline(DIV_FN)(inp.dividend, inp.divisor, inp.signed if self.HAS_RUNTIME_SIGN else self.IS_SIGNED,
        #        loopPragmaGetter=self._getLoopMeta)
        #    resTmp = outT.from_py(None)
        #    resTmp.quotient = res[0]
        #    resTmp.remainder = res[1]
        #    hls.write(resTmp, self.data_out, mayBecomeFlushable=False)
        # else:
        #    inp = self.data_in.T.from_py({"dividend":0, "divisor":0})
        #    while b1:
        #        # loop for the case where functional unit has some internal delay.
        #        # The output of the lop
        #        res = PyBytecodeInline(DIV_FN)(inp.dividend, inp.divisor,
        #                                       inp.signed if self.HAS_RUNTIME_SIGN else self.IS_SIGNED,
        #            loopPragmaGetter=self._getLoopMeta)
        #        resTmp = outT.from_py(None)
        #        resTmp.quotient = res[0]
        #        resTmp.remainder = res[1]
        #        hls.write(resTmp, self.data_out, mayBecomeFlushable=False)
        #        # read input at the end of the loop to be able receive it in the same clock as output is produced
        #        while b1:
        #            # [fixme] This is necessary because the if inp.valid would not prevent the execution of
        #            #         functional to execute, (just if r.valid in the main loop would not be sufficient as r.valid
        #            #         would travel to next loop iteration as data on channel with non blocking read.)
        #            #         That would not be a problem, the functional unit would execute and data would be correctly
        #            #         dropped at the end. However the latency of unit would be added as delay to this loop.
        #            #         This could cause serious performance loss and it is prevented by this loop,
        #            r = hls.read(self.data_in, blocking=False)
        #            if r.valid:
        #                break
        #        inp = r.data
    # @hlsBytecode
    # def mainThread(self, hls: HlsScope):
    #    # disable slow optimizations which are useless in this case
    #    # PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", "hwtHls::SelectPruningPass"])
    #
    #    self.MAIN_FN_META
    #    FN = PyBytecodeInline(self.FN)
    #    raise NotImplementedError()
    #    # if self._isFullyUnrolled() or (self.IN_CHANNEL_TYPE == HwIOStruct and self.OUT_CHANNEL_TYPE == HwIOStruct):
    #    #    while b1:
    #    #        inp = hls.read(self.data_in).data
    #    #        res = FN(inp._reinterpret_cast(self.T), loopPragmaGetter=self._getLoopMeta)
    #    #        hls.write(res, self.data_out, mayBecomeFlushable=False)
    #    # else:
    #    #    vld = b0
    #    #    inp = self.data_in.T.from_py(None)
    #    #    while b1:
    #    #        if vld:
    #    #            res = FN(inp._reinterpret_cast(self.T), loopPragmaGetter=self._getLoopMeta)
    #    #            hls.write(res, self.data_out, mayBecomeFlushable=False)
    #    #        # read input at the end of the loop to be able receive it in the same clock as output is produced
    #    #        r = hls.read(self.data_in, blocking=False)
    #    #        inp = r.data
    #    #        vld = r.valid
    #

