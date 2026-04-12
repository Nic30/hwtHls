from copy import copy
import math
from typing import Type

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld, HwIOStruct, \
    HdlType_to_HwIO
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerator import HlsErrorHighlyInefficientImplementation
from hwtHls.frontend.pragmaLoop import PyBytecodeLLVMLoopUnroll
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.opRealizationMeta import  ComponentRealizationMeta
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

    @override
    def hwConfig(self) -> None:
        self.T: HdlType = HwParam(None)
        self.CLK_FREQ: int = HwParam(int(20e6))
        self.UNROLL_FACTOR = HwParam(1)
        self.MAIN_FN_META = HwParam(None)
        self.CHECK_FOR_INEFFICIENCY: bool = HwParam(True)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructRdVld)

    def _setIoChannelTypes(self, realization: ComponentRealizationMeta):
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

    @override
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
        if self.CHECK_FOR_INEFFICIENCY:
            assert self.UNROLL_FACTOR <= ITERATION_CNT, "Using larger UNROLL_FACTOR does not bring any benefit"
        return self.UNROLL_FACTOR == ITERATION_CNT

    def _getLoopMeta(self):
        UNROLL_FACTOR = self.UNROLL_FACTOR
        if UNROLL_FACTOR > 1:
            return PyBytecodeLLVMLoopUnroll(True, UNROLL_FACTOR,
                # followup_unrolled=PyBytecodeLoopFlattenUsingIf(mode=PyBytecodeLoopFlattenUsingIf.Mode.CHILD_LOOP_ENTRY_IN_SAME_ITERATION)
                )
        else:
            return None
            # return PyBytecodeLoopFlattenUsingIf(mode=PyBytecodeLoopFlattenUsingIf.Mode.CHILD_LOOP_ENTRY_IN_SAME_ITERATION)

    def _backupTiming(self, hls: HlsScope, isFullyUnrolled: bool):
        inputClkTickOffset = math.inf
        inputWireDelay = math.inf
        outputClkTickOffset = 0
        outputWireDelay = 0
        inSeen = False
        outSeen = False
        for t in hls._threads:
            netlist: HlsNetlistCtx = t.netlist
            clkPeriod = netlist.normalizedClkPeriod
            timeResolution = netlist.scheduler.resolution
            for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
                if isinstance(n, HlsNetNodeRead):
                    if n.src is self.data_in:
                        assert not inSeen, self
                        t = min(n.scheduledOut)
                        inputWireDelay = min(inputWireDelay, t % clkPeriod)
                        inputClkTickOffset = min(inputClkTickOffset, t // clkPeriod)
                        inSeen = True

                elif isinstance(n, HlsNetNodeWrite):
                    if n.dst is self.data_out:
                        assert not outSeen, self
                        t = max(n.scheduledIn)
                        outputWireDelay = max(outputWireDelay, t % clkPeriod)
                        outputClkTickOffset = max(outputClkTickOffset, t // clkPeriod)
                        outSeen = True
        assert inSeen, self
        assert outSeen, self
        assert isinstance(inputClkTickOffset, int), (self, inputClkTickOffset)

        hlsOpRealizationMetaAsSeenFromInside = ComponentRealizationMeta(
            inputClkTickOffset=inputClkTickOffset,
            inputWireDelay=inputWireDelay * timeResolution,
            outputWireDelay=outputWireDelay * timeResolution,
            outputClkTickOffset=outputClkTickOffset,
            requiresInValid=not isFullyUnrolled,
            mayGenerateInStall=not isFullyUnrolled,
            mayGenerateOutStall=not isFullyUnrolled
        )
        hlsOpRealizationMetaAsSeenFromOutside: ComponentRealizationMeta = copy(hlsOpRealizationMetaAsSeenFromInside)
        if not isFullyUnrolled and inputClkTickOffset == 0 and outputClkTickOffset == 0:
            # +1 because the output is in fist clk, but after n iterations
            # and thus data_in read and data_out write can not happen at once
            hlsOpRealizationMetaAsSeenFromOutside.inputClkTickOffset = 1
            # :attention: Inside and Outside realization may be different
            # because in parent the port of this component may be used earlier
            # if the input and output happen in same clock and the implementation
            # can not respond with output within the same clock cycle

        self.__hlsOpRealizationMeta = (hlsOpRealizationMetaAsSeenFromInside,
                                       hlsOpRealizationMetaAsSeenFromOutside)

        return outputClkTickOffset

    def getHlsOpRealizationMeta(self):
        if self._shared_component_with is None:
            return self.__hlsOpRealizationMeta
        else:
            return self._shared_component_with[0].getHlsOpRealizationMeta()

    @override
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
        aluFn = PyBytecodeInline(self.aluFn)
        outT = self._getTypeOfIo(self.data_out)
        if self._isFullyUnrolled() or\
                (self.IN_CHANNEL_TYPE == HwIOStruct and self.OUT_CHANNEL_TYPE == HwIOStruct):
            # or \
            #    (self.IN_CHANNEL_TYPE == HwIOStructRdVld and self.OUT_CHANNEL_TYPE == HwIOStructRdVld)
            # :note: V0
            # :note: In this case the read and write does not need to be scheduled into the same clk window
            while b1:
                # main loop for the case this is just strait pipeline
                PyBytecodeBlockLabel("bb._BaseALU1HwModule.header")
                inp = hls.read(self.data_in).data
                out = aluFn(inp)
                assert out._dtype == outT, (out._dtype, outT)
                PyBytecodeBlockLabel("bb._BaseALU1HwModule.latch")
                hls.write(out, self.data_out, mayBecomeFlushable=False)
        else:
            # assert self.IN_CHANNEL_TYPE == HwIOStructVld and self.OUT_CHANNEL_TYPE == HwIOStructRdVld, self
            # :note: In this case the read and write must must be scheduled into the same clk window
            #   because the new data must be accepted in the same clock when the output is flushed
            # Complications:
            #  * aluFn can not be speculatively executed because it is expected that the computation time would be long
            #  * the read must happen after write for write to be flushable
            #  * the static scheduling needs a clock window where read/write is performed or not
            #    this time if this io operation is in the cycle this time will be consumed during execution even
            #    if the io operation is not performed
            #  * Components generated by this function may be nested,  this implies
            #    that any overhead in this function will multiply quiclky

            inpValid = b0
            inpData = self._getTypeOfIo(self.data_in).from_py(None)
            PyBytecodeBlockLabel("bb._BaseALU1HwModule.preheader")
            while b1:
                # :note: if to prevent speculative execution of the potentially costly aluFn
                out = outT.from_py(None)
                if inpValid:
                    PyBytecodeBlockLabel("bb._BaseALU1HwModule.compute")
                    outTmp = aluFn(inpData)
                    assert outTmp._dtype == outT, (outTmp._dtype, outT)
                    out = outTmp
                    del outTmp
                    # :note: read/write may happen only in the same clock cycle
                    PyBytecodeBlockLabel("bb._BaseALU1HwModule.outSt")
                    hls.write(out, self.data_out, mayBecomeFlushable=False)
                del out

                PyBytecodeBlockLabel("bb._BaseALU1HwModule.inLd")
                r = hls.read(self.data_in, blocking=False)  # :note: non-blocking so data_in.valid does not stall data_out write
                inpData = r.data
                inpValid = r.valid

            ########################################################################################
            # # :note: equivalent to V0, due to loop rotation
            # data_in = PyBytecodeInPreproc(self.data_in)
            # r = hls.read(data_in, blocking=True)
            # inpData = r.data
            # while b1:
            #     res = aluFn(inpData)
            #     hls.write(res, self.data_out, mayBecomeFlushable=True)
            #     r = hls.read(data_in, blocking=True)
            #     inpData = r.data
            ########################################################################################
            # # :note: V1 this version has combinational loop from data_in.valid to data_out.ready
            # out = self._getTypeOfIo(self.data_out).from_py(None)
            # outVld = b0
            # while b1:
            #     if outVld:
            #         hls.write(out, self.data_out, mayBecomeFlushable=True)
            #     inp = hls.read(self.data_in).data
            #     out = PyBytecodeInline(self.aluFn)(inp)
            #     outVld = b1
            ########################################################################################
            # # :note: V2 this has the problem that the block with read may be entered conditionaly from header,
            # #  this means that the whole loop synchronization is one big SCC
            # # version with read rotated at the end of the loop to allow read of input in the same
            # # cycle when the data is written to output
            # inp = self._getTypeOfIo(self.data_in).from_py(None)
            # inpValid = b0
            # while b1:
            #     if inpValid:
            #         # # read input at the end of the loop to be able receive it in the same clock as output is produced
            #         # while ~inpValid:
            #         #    # [fixme] This is necessary because the if inp.valid would not prevent the execution of
            #         #    #         functional to execute, (just if r.valid in the main loop would not be sufficient as r.valid
            #         #    #         would travel to next loop iteration as data on channel with non blocking read.)
            #         #    #         That would not be a problem, the functional unit would execute and data would be correctly
            #         #    #         dropped at the end. However the latency of unit would be added as delay to this loop.
            #         #    #         This could cause serious performance loss and it is prevented by this loop,
            #         #    r = hls.read(self.data_in, blocking=False)
            #         #    inp = r.data
            #         #    inpValid = r.valid
            #         # # loop for the case where functional unit has some internal delay.
            #         # The output of the lop
            #         # if inpValid:
            #         resTmp = PyBytecodeInline(self.aluFn)(inp)
            #         hls.write(resTmp, self.data_out, mayBecomeFlushable=True)
            #     # :note: using write(mayBecomeFlushable=False) and read(blocking=False)
            #     #   may result in more simple circuit but fsm will spin in idle, if aluFn
            #     #   takes more than 1 clk cycle component would not be abble to accept data
            #     #   if it is spinning on some iddle state then first one, this would cause delay
            #     #   bubles if input is not saturated
            #     r = hls.read(self.data_in)
            #     inp = r.data
            #     inpValid = r.valid
            ########################################################################################
            # :note: V3 this will reduce to V2
            # inp = self._getTypeOfIo(self.data_in).from_py(None)
            # inpValid = b0
            # while b1:
            #     if inpValid:
            #         resTmp = PyBytecodeInline(self.aluFn)(inp)
            #         hls.write(resTmp, self.data_out, mayBecomeFlushable=True)
            #
            #     inpValid = b0
            #     while ~inpValid:
            #         r = hls.read(self.data_in)
            #         inp = r.data
            #         inpValid = r.valid
            ########################################################################################
            # :note: V4 this variant have problem with input valid combinational path to output valid
            # outT = self._getTypeOfIo(self.data_out)
            # out = outT.from_py(None)
            # outVld = b0
            # while b1:
            #     # :note: read/write may happen only in the same clock cycle
            #     if outVld:
            #         hls.write(out, self.data_out, mayBecomeFlushable=False)
            #
            #     r = hls.read(self.data_in, blocking=False) # :note: non-blocking so data_in.valid does not stall data_out write
            #     inpData = r.data
            #     inpValid = r.valid
            #     # :note: if to prevent speculative execution of the potentially costly aluFn
            #     if inpValid:
            #         out = aluFn(inpData)
            #     else:
            #         out = outT.from_py(None)
            #     outVld = inpValid
            ########################################################################################

            # inpData = self._getTypeOfIo(self.data_in).from_py(None)
            # inpValid = b0
            # while b1:
            #    # data_in = PyBytecodeInPreproc(MultiPortGroup((self.data_in, self.data_in)))  # :note: workaround to allow 2 reads in same clock cycle
            #    data_in = PyBytecodeInPreproc(self.data_in)
            #    if ~inpValid:
            #        r = hls.read(data_in, blocking=True)
            #        inpData = r.data
            #        inpValid = r.valid
            #
            #    res = aluFn(inpData)
            #    hls.write(res, self.data_out, mayBecomeFlushable=True)
            #    r = hls.read(data_in, blocking=True)
            #    inpData = r.data
            #    inpValid = r.valid

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

