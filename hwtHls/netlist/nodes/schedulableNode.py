from itertools import zip_longest
from math import inf, isfinite
from typing import Optional, Callable, Union, Literal, \
    Generator, Self

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, \
    clkWindowBeginOfNext, clkWindowEnd, SchedTime, \
    SchedTime_format, clkWindowOffsetFromWindowEnd,\
    clkWindowOffsetFromWindowBegin
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

SchedulizationDict = dict["HlsNetNode", tuple[SchedTime,  # node zero time
                                              tuple[SchedTime, ...],  # scheduledIn
                                              tuple[SchedTime, ...]]]  # scheduledOut
TimeSpec = Union[float, tuple[SchedTime, ...]]
OutputMinUseTimeGetter = Callable[[HlsNetNodeOut, Union[SchedTime, Literal[inf]]], SchedTime]  # second parameter is a current min time resolved from inputs
OutputTimeGetter = Callable[[HlsNetNodeOut, Optional[SetList["HlsNetNode"]], SchedTime], SchedTime]  # 2. parameter is path of nodes for debug of cycles, 3. parameter is beginOfFirstClk


class SchedulableNode():
    """
    :ivar scheduledZero: This time is usually a time max(scheduledIn) <= scheduledZero <= min(scheduledOut)
        used to avoid re-computation of last input. But for aggregate nodes it may have any value.
    :attention: scheduledZero time is used to cheaply detect that the scheduling of the node has changed.
        This time should not be used to resolve when the node is scheduled and port times should be used instead.
        Because it is not guaranteed to have any specific value.
        
        
    :note: if isMulticlock=True the scheduledZero is set to begin of clk window after 
        where inputs with inputClkTickOffset=0 are (= clkWindow where outputs with outputClkTickOffset=0 are)
    :ivar scheduledIn: a time when the input is scheduled
    :ivar scheduledOut: a time when the output is scheduled
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        self.netlist = netlist
        self.usedBy: list[list[HlsNetNodeIn]] = []
        self.dependsOn: ObservableList[HlsNetNodeOut] = ObservableList()
        self._inputs: list[HlsNetNodeIn] = []
        self._outputs: ObservableList[HlsNetNodeOut] = ObservableList()

        self.scheduledZero: Optional[SchedTime] = None
        self.scheduledZeroMin: Optional[SchedTime] = None
        self.scheduledZeroMax: Optional[SchedTime] = None
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None
        self.realization: Optional[OpRealizationMeta] = None
        self.isMulticlock: bool = False

    def getSchedulingResourceType(self):
        return None  # None marks that there is no constraint

    def copyScheduling(self, schedule: SchedulizationDict):
        schedule[self] = (self.scheduledZero, self.scheduledIn, self.scheduledOut)

    def setScheduling(self, schedule: SchedulizationDict):
        (self.scheduledZero, self.scheduledIn, self.scheduledOut) = schedule[self]

    def checkScheduling(self):
        """
        Assert that the scheduling is consistent.
        """
        assert self.scheduledZero is not None, self
        if self.scheduledZeroMin is not None:
            assert self.scheduledZero >= self.scheduledZeroMin, (self, self.scheduledZero, '>=', self.scheduledZeroMin)
        if self.scheduledZeroMax is not None:
            assert self.scheduledZero <= self.scheduledZeroMax, (self, self.scheduledZero, '<', self.scheduledZeroMax)

        assert self.scheduledIn is not None, self
        assert self.scheduledOut is not None, self
        checkNotInFfStoreTime = self.realization is not None and not self.realization.isAllowedInFFStoreTime
        netlist = self.netlist
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        clkPeriod = netlist.normalizedClkPeriod
        usableClkWindow = clkPeriod - ffdelay
        for i, iT, dep in zip_longest(self._inputs, self.scheduledIn, self.dependsOn):
            assert isinstance(iT, SchedTime), (self, i, dep, iT)
            assert dep is not None, (self, i, dep, "Inconsistent input specification")
            assert i is not None, (self, dep, "Inconsistent input specification")
            assert dep.obj.scheduledOut is not None, (self, dep.obj)
            oT = dep.obj.scheduledOut[dep.out_i]
            assert isinstance(oT, SchedTime), (dep, oT)
            assert iT >= oT, (oT, SchedTime_format(oT, clkPeriod), iT, SchedTime_format(iT, clkPeriod), "Input must be scheduled after connected output port.", dep, "->", i)
            assert iT >= 0, (iT, self, i, "Scheduled before start of the time.")
            assert oT >= 0, (oT, dep, "Scheduled before start of the time.")
            if checkNotInFfStoreTime:
                try:
                    assert abs(iT % clkPeriod) <= usableClkWindow, (self, i, iT % clkPeriod, iT, clkPeriod)
                except:
                    raise
        for o, oT, users in zip_longest(self._outputs, self.scheduledOut, self.usedBy):
            for u in users:
                uSched = u.obj.scheduledIn
                if uSched is None:
                    continue  # not scheduled yet
                iT = uSched[u.in_i]
                assert iT >= oT, (oT, SchedTime_format(oT, clkPeriod), iT, SchedTime_format(iT, clkPeriod), self, u)

        if checkNotInFfStoreTime:
            for o, oT in zip(self._outputs, self.scheduledOut):
                assert abs(oT % clkPeriod) <= usableClkWindow, (o, oT, clkPeriod, ffdelay, abs(oT % clkPeriod), usableClkWindow)

    def resetScheduling(self):
        self.scheduledZero = None
        self.scheduledIn = None
        self.scheduledOut = None

    def moveSchedulingTime(self, offset: SchedTime):
        assert offset != 0, ("If offset is 0 this is useless to call this", self)
        self.scheduledZero += offset
        if self.scheduledZeroMin is not None:
            assert self.scheduledZero >= self.scheduledZeroMin, (self, self.scheduledZero, '>=', self.scheduledZeroMin)
        if self.scheduledZeroMax is not None:
            assert self.scheduledZero < self.scheduledZeroMax, (self, self.scheduledZero, '<', self.scheduledZeroMax)

        self.scheduledIn = tuple(t + offset for t in self.scheduledIn)
        self.scheduledOut = tuple(t + offset for t in self.scheduledOut)

    def _setScheduleZeroTimeSingleClock(self, t: SchedTime):
        assert not self.isMulticlock, self
        assert isinstance(t, SchedTime), t
        assert self.scheduledZero != t, (self, t, "If time is the same this is useless to call")
        if self.scheduledZeroMin is not None:
            assert t >= self.scheduledZeroMin, (self, t, '>=', self.scheduledZeroMin)
        if self.scheduledZeroMax is not None:
            assert t <= self.scheduledZeroMax, (self, t, '<', self.scheduledZeroMax)

        self.scheduledIn = tuple(
            t - in_delay
            for in_delay in self.inputWireDelay
        )
        self.scheduledZero = t
        self.scheduledOut = tuple(
            t + out_delay
            for out_delay in self.outputWireDelay
        )
        clkPeriod = self.netlist.normalizedClkPeriod
        clkI = t // clkPeriod
        b = clkI * clkPeriod
        e = (clkI + 1) * clkPeriod
        for _t in self.scheduledIn:
            assert b <= _t < e, (self, _t)  
        for _t in self.scheduledOut:
            assert b <= _t < e, (self, _t)  
        # maxOutputLatency = max(self.outputWireDelay, default=0)
        # if not self.isAllowedInFFStoreTime:
        #    netlist = self.netlist
        #    clkPeriod = netlist.normalizedClkPeriod
        #    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        #    if clkWindowOffsetFromWindowEnd(self.scheduledZero, clkPeriod) < ffdelay + maxOutputLatency:
        #        raise AssertionError()

    def _setScheduleZeroTimeMultiClock(self, t: SchedTime, clkPeriod: SchedTime, epsilon: SchedTime, ffdelay: SchedTime):
        """
        :note: the t (scheduledZero) is a time of the "middle" of the node
        """
        assert isinstance(t, SchedTime), t
        assert self.scheduledZero != t, (self, t, "If time is the same this is useless to call")
        assert t % clkPeriod == 0, (self, t, clkPeriod)

        if self.scheduledZeroMin is not None:
            assert t >= self.scheduledZeroMin, (self, t, '>=', self.scheduledZeroMin)
        if self.scheduledZeroMax is not None:
            assert t < self.scheduledZeroMax, (self, t, '<', self.scheduledZeroMax)

        clkI = clkWindowIndex(t, clkPeriod)
        self.scheduledIn = tuple(
            (clkI - iTicks) * clkPeriod - iDelay - epsilon
            for (iDelay, iTicks) in zip(self.inputWireDelay, self.inputClkTickOffset)
        )
        self.scheduledZero = t
        self.scheduledOut = tuple(
            (clkI + oTicks) * clkPeriod + oDelay
            for (oDelay, oTicks) in zip(self.outputWireDelay, self.outputClkTickOffset)
        )


    @staticmethod
    def _schedulerJumpToPrevCycleIfRequired(time: Union[float, SchedTime], requestedTime: SchedTime,
                                            clkPeriod: SchedTime,
                                            timeSpacingBeforeClkEnd: SchedTime) -> SchedTime:
        prevClkEndTime = clkWindowIndex(time, clkPeriod) * clkPeriod
        if requestedTime < prevClkEndTime:
            # must shift whole node sooner in time because the input  time of the input can not be satisfied
            # in a clock cycle where the input is currently scheduled
            requestedTime = prevClkEndTime - timeSpacingBeforeClkEnd
        elif requestedTime > prevClkEndTime + clkPeriod - timeSpacingBeforeClkEnd:
            # must shift because current requested time is in timeSpacingBeforeClkEnd
            requestedTime = prevClkEndTime + clkPeriod - timeSpacingBeforeClkEnd

        return requestedTime

    # @staticmethod
    # def _schedulerGetNormalizedTimeForInput(availableInTime: SchedTime, inWireLatency: SchedTime,
    #                                        inputClkTickOffset: SchedTime, clkPeriod: SchedTime,
    #                                        ffdelay: SchedTime, isAllowedInFFStoreTime: bool):
    #    """
    #    Returns the "scheduledZero" inferred from the time where input is available and its scheduling props.
    #    :note: This computes only for 1 input and ingnores outputs.
    #
    #    :param availableInTime: time when all dependencies of input are available
    #    :param inWireLatency: time which must be available before clock cycle
    #    :param inputClkTickOffset: number of clock cycles between clock cycle where this input is and where node zero time is
    #    :param clkPeriod: normalized clock period
    #    :param ffdelay: normalized time of register store operation
    #    :param mayBeginInFFStoreTime: if true the input time may be at the end of clock window in FF store time
    #
    #    :return: normalized time of where node zero time is according this input
    #    """
    #    if isAllowedInFFStoreTime and inWireLatency == 0 and inputClkTickOffset == 0:
    #        return availableInTime
    #
    #    nextClkTime = (clkWindowIndex(availableInTime, clkPeriod) + 1) * clkPeriod
    #    timeBudget = nextClkTime - availableInTime
    #
    #    if isAllowedInFFStoreTime:
    #        requiredUntilClkEnd = inWireLatency
    #    else:
    #        requiredUntilClkEnd = max(inWireLatency, ffdelay)
    #
    #    if inputClkTickOffset != 0:
    #        if requiredUntilClkEnd > timeBudget:
    #            inputClkTickOffset += 1
    #        # snapping to next clk window begin
    #        return nextClkTime + inputClkTickOffset * clkPeriod
    #    else:
    #        if requiredUntilClkEnd > timeBudget:
    #            # does not fit to this clock cycle -> move at the begining of the next
    #            return nextClkTime + inWireLatency
    #        else:
    #            # delay of input fits well to this clock cycles
    #            return availableInTime + inWireLatency
    #
    def _scheduledZeroApplyLimits(self, newNodeZeroTime: SchedTime, allowEarlier:bool, allowLater:bool):
        zeroTimeMin = self.scheduledZeroMin
        if zeroTimeMin is not None and newNodeZeroTime < zeroTimeMin:
            if allowLater:
                return zeroTimeMin
            else:
                raise TimeConstraintError(
                                "Impossible scheduling, scheduledZeroMin specifies >=", zeroTimeMin,
                                " but the best node can do is ", newNodeZeroTime, self)
        zeroTimeMax = self.scheduledZeroMax
        if zeroTimeMax is not None and newNodeZeroTime >= zeroTimeMax:
            if allowEarlier:
                return zeroTimeMax
            else:
                raise TimeConstraintError(
                                "Impossible scheduling, zeroTimeMax specifies <=", zeroTimeMax,
                                " but the best node can do is ", newNodeZeroTime, self)
        return newNodeZeroTime

    def getFirstSchedZeroClkI(self):
        assert self.scheduledZero is not None, self
        if self._inputs:
            minT = min(self.scheduledIn)
        else:
            minT = self.scheduledZero

        return minT // self.netlist.normalizedClkPeriod

    def _getSchedResourceClkI(self, scheduledZero: SchedTime):
        return clkWindowIndex(scheduledZero, self.netlist.normalizedClkPeriod) - (1 if self.isMulticlock else 0)

    def getSchedResourceClkI(self):
        """
        Get clk window index used where the schedulable resource used by this node is allocated
        """
        return self._getSchedResourceClkI(self.scheduledZero)

    def _scheduleAsap_ScheduledZero_fromInSchedule(self,
                                                  availableInTime: SchedTime,
                                                  inWireLatency: SchedTime,
                                                  inputClkTickOffset: int,
                                                  requiredForOutputTime: SchedTime,
                                                  ffdelay: SchedTime):
        clkPeriod = self.netlist.normalizedClkPeriod
        if inWireLatency + requiredForOutputTime >= clkPeriod:
            raise TimeConstraintError(
                "Impossible scheduling, clkPeriod too low for ",
                self.inputWireDelay, self.outputWireDelay, "clkPeriod:", clkPeriod, self)
        # normalizedTime = self._schedulerGetNormalizedTimeForInput(
        #    availableInTime, inWireLatency, 0, clkPeriod, ffdelay,
        #    isAllowedInFFStoreTime)
        isAllowedInFFStoreTime = self.isAllowedInFFStoreTime
        if isAllowedInFFStoreTime and inWireLatency == 0 and inputClkTickOffset == 0:
            return availableInTime
        else:
            nextClkTime = (clkWindowIndex(availableInTime, clkPeriod) + 1) * clkPeriod
            timeBudget = nextClkTime - availableInTime

            if isAllowedInFFStoreTime:
                requiredUntilClkEnd = inWireLatency
            elif self._outputs:
                requiredUntilClkEnd = inWireLatency + requiredForOutputTime
            else:
                requiredUntilClkEnd = max(inWireLatency, ffdelay)

            if inputClkTickOffset != 0:
                if requiredUntilClkEnd > timeBudget:
                    inputClkTickOffset += 1
                # snapping to next clk window begin
                return nextClkTime + inputClkTickOffset * clkPeriod
            else:
                if requiredUntilClkEnd > timeBudget:
                    # does not fit to this clock cycle -> move at the begining of the next
                    return nextClkTime + inWireLatency
                else:
                    # delay of input fits well to this clock cycles
                    return availableInTime + inWireLatency

    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]],
                     beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> list[int]:
        """
        The recursive function of As Soon As Possible scheduling. Initial netlist scheduling method.
        """
        if self.scheduledZero is None:
            netlist = self.netlist
            clkPeriod = netlist.normalizedClkPeriod
            if self.realization is None:
                # resolve realization if it is not already resolved
                self.resolveRealization()

            ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
            if self.dependsOn:
                if pathForDebug is not None:
                    if self in pathForDebug:
                        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                    else:
                        pathForDebug.append(self)
                try:
                    # :note: all inputs must be scheduled first before
                    if outputTimeGetter is None:
                        inputTimes = (d.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[d.out_i]
                                       for d in self.dependsOn)
                    else:
                        inputTimes = (outputTimeGetter(d, pathForDebug, beginOfFirstClk) for d in self.dependsOn)

                    inputTimes = tuple(inputTimes)

                    # now we have times when the value is available on input
                    # and we must resolve the minimal time so each input timing constraints are satisfied
                    nodeZeroTime = beginOfFirstClk
                    isAllowedInFFStoreTime = self.realization.isAllowedInFFStoreTime
                    if self.isMulticlock:
                        zeroClkI = clkWindowIndex(nodeZeroTime, clkPeriod)
                        # :note: -1 because zeroClkI was the index of clock after
                        # clock window where inputs with inputClkTickOffset=0 are
                        zeroClkI -= 1

                        for (availableInTime, inWireLatency, inputClkTickOffset) in zip(inputTimes,
                                                                                        self.inputWireDelay,
                                                                                        self.inputClkTickOffset):
                            if inWireLatency >= clkPeriod:
                                raise TimeConstraintError(
                                    "Impossible scheduling, clkPeriod too low for ",
                                    self.inputWireDelay, self.outputWireDelay, "clkPeriod:", self)
                            inClkBudget = clkWindowOffsetFromWindowEnd(availableInTime, clkPeriod)
                            zeroClkIFromThisIn = clkWindowIndex(availableInTime, clkPeriod) + inputClkTickOffset
                            if inClkBudget < inWireLatency:
                                # first clk can not be mapped to same clock cycle window where the connected
                                # out is
                                zeroClkIFromThisIn += 1

                            if zeroClkI < zeroClkIFromThisIn:
                                # must schedule at later time if any input requires it
                                zeroClkI = zeroClkIFromThisIn

                        nodeZeroTime = (zeroClkI + 1) * clkPeriod
                    else:
                        requiredForOutputTime = 0 if not self.outputWireDelay else max(self.outputWireDelay)
                        if not isAllowedInFFStoreTime:
                            if self.outputWireDelay:
                                requiredForOutputTime += ffdelay

                        for (availableInTime, inWireLatency, inputClkTickOffset) in zip(inputTimes,
                                                                                        self.inputWireDelay,
                                                                                        self.inputClkTickOffset):
                            assert inputClkTickOffset == 0, self
                            newZeroTime = self._scheduleAsap_ScheduledZero_fromInSchedule(
                                availableInTime, inWireLatency, inputClkTickOffset, requiredForOutputTime, ffdelay)
                            if newZeroTime > nodeZeroTime:
                                nodeZeroTime = newZeroTime

                        if not self._inputs:
                            if nodeZeroTime + requiredForOutputTime > clkWindowEnd(nodeZeroTime, clkPeriod):
                                # if the output delay does not fit to current clock, move this node to next clock
                                nodeZeroTime = clkWindowBeginOfNext(nodeZeroTime, clkPeriod)
                                if self.inputWireDelay:
                                    nodeZeroTime += max(self.inputWireDelay)

                finally:
                    if pathForDebug is not None:
                        pathForDebug.pop()
            else:
                assert not self._inputs
                nodeZeroTime = beginOfFirstClk

            nodeZeroTime = self._scheduledZeroApplyLimits(nodeZeroTime, False, True)

            if self.isMulticlock:
                epsilon = netlist.scheduler.epsilon
                self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
            else:
                self._setScheduleZeroTimeSingleClock(nodeZeroTime)
            assert self.scheduledOut is not None, self

        return self.scheduledOut

    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[Self], bool]])\
            ->Generator["HlsNetNode", None, None]:
        """
        Single clock variant (inputClkTickOffset and outputClkTickOffset are all zeros)

        :return: a generator of dependencies which are now possible subject to compaction.
        """
        if self.isMulticlock:
            yield from self.scheduleAlapCompactionMultiClock(endOfLastClk, outputMinUseTimeGetter, excludeNode)
            return
        # self.checkScheduling()
        # assert not self.isMulticlock, (self, "this node should use scheduleAlapCompactionMultiClock instead")
        # assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        netlist = self.netlist
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        clkPeriod = netlist.normalizedClkPeriod

        if not self._outputs:
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port.")
            nodeZeroTime = inf
        else:
            # resolve a minimal time where the output can be scheduler and translate it to nodeZeroTime
            nodeZeroTime = inf
            curZero = self.scheduledZero
            for (out, uses, outWireLatency) in zip(self._outputs, self.usedBy, self.outputWireDelay):
                if outWireLatency + ffdelay >= clkPeriod:
                        raise TimeConstraintError(
                            "Impossible scheduling, clkPeriod too low for ",
                            self.outputWireDelay, ffdelay, clkPeriod, self)
                if uses:
                    oZeroT = inf
                    # find earliest time where this output is used
                    for dependentIn in uses:
                        dependentIn: HlsNetNodeIn
                        inpTime = dependentIn.obj.scheduledIn[dependentIn.in_i]
                        if curZero is not None:
                            assert inpTime >= curZero, (inpTime, curZero, self.scheduledOut[out.out_i],
                                                        "Current output time violates input arrival time.", out, dependentIn)
                        zeroTFromUserInput = inpTime - outWireLatency
                        # if outWireLatency does not fit into space until clock end,
                        # it should move to prev clk end + ffdelay + outWireLatency
                        zeroTFromUserInput = self._schedulerJumpToPrevCycleIfRequired(
                            inpTime, zeroTFromUserInput, clkPeriod, ffdelay + outWireLatency)
                        assert inpTime >= zeroTFromUserInput, self
                        oZeroT = min(oZeroT, zeroTFromUserInput)
                else:
                    # there are some other uses we may skip this
                    oZeroT = inf

                if outputMinUseTimeGetter is not None:
                    oZeroT = outputMinUseTimeGetter(out, oZeroT)

                nodeZeroTime = min(nodeZeroTime, oZeroT)

        maxOutputLatency = max(self.outputWireDelay, default=0)
        if not self.isAllowedInFFStoreTime:
            if clkWindowOffsetFromWindowEnd(self.scheduledZero, clkPeriod) < ffdelay + maxOutputLatency:
                raise TimeConstraintError("Node was already scheduled on wrong time, end overlaps to ffstore time",
                                          clkWindowOffsetFromWindowEnd(self.scheduledZero, clkPeriod), ffdelay, maxOutputLatency, self)

        if isfinite(nodeZeroTime):
            maxInDelay = max(self.inputWireDelay, default=0)
            # we have to check if every input has enough time for its delay
            # and optionally move this node to previous clock cycle
            for inDelay in self.inputWireDelay:
                if inDelay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.inputWireDelay, clkPeriod, self)
            inTime = nodeZeroTime - maxInDelay
            nodeZeroTime = self._schedulerJumpToPrevCycleIfRequired(
                nodeZeroTime, inTime, clkPeriod, maxInDelay + maxOutputLatency + ffdelay) + maxInDelay
        else:
            # no use of any output, we must use some ASAP input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port used (or more likely it should be removed because it is useless)")
            nodeZeroTime = endOfLastClk - (ffdelay + maxOutputLatency) - netlist.scheduler.epsilon

        nodeZeroTime = self._scheduledZeroApplyLimits(nodeZeroTime, True, False)

        if self.scheduledZero != nodeZeroTime:
            assert isinstance(nodeZeroTime, SchedTime) and (self.scheduledZero is None or (isinstance(self.scheduledZero, SchedTime))
                    ), (self.scheduledZero, "->", nodeZeroTime, self)

            if self.scheduledZero is not None and self.scheduledZero > nodeZeroTime:
                # this can happen if successor nodes were packed inefficiently in previous cycles and it moved this node.
                # We can not move this node because it would potentially move whole circuit which would eventually result
                # in an endless cycle in scheduling
                raise TimeConstraintError(
                       "Can not be scheduled sooner then current best ALAP time,"
                       " because otherwise time should have been kept",
                       self, SchedTime_format(self.scheduledZero, clkPeriod), "->", SchedTime_format(nodeZeroTime, clkPeriod))

            self._setScheduleZeroTimeSingleClock(nodeZeroTime)
            # self.checkScheduling()

            for dep in self.dependsOn:
                yield dep.obj

    def scheduleAlapCompactionMultiClock(self, endOfLastClk: SchedTime,
                                         outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                                         excludeNode: Optional[Callable[[Self], bool]])\
                                          ->Generator["HlsNetNode", None, None]:
        """
        Move node to a later time if possible. Netlist is expected to be scheduled.
        This allows to move trees of nodes to later times and allow for possibly better fit of nodes
        to a clock period windows.

        :return: generator of nodes for compaction worklist
        :see: :meth:`HlsNetNode::scheduleAlapCompactionMultiClock`
        """
        assert self.isMulticlock, self
        # if all dependencies have inputs scheduled we schedule this node and try successors
        netlist = self.netlist
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        clkPeriod = netlist.normalizedClkPeriod
        epsilon = netlist.scheduler.epsilon
        isAllowedInFFStoreTime = self.realization.isAllowedInFFStoreTime
        if not self._outputs or not any(self.usedBy):
            # no outputs, we must use some ASAP input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port.")
            nodeZeroTime = endOfLastClk + epsilon
        else:
            # move back in time to satisfy all output timing requirements
            nodeZeroClkI = inf
            for out, uses, oDelay, oTicks in zip(self._outputs,
                                                 self.usedBy,
                                                 self.outputWireDelay,
                                                 self.outputClkTickOffset):
                # find earliest time where this output is used
                oT = inf
                for dependentIn in uses:
                    dependentIn: HlsNetNodeIn
                    iT = dependentIn.obj.scheduledIn[dependentIn.in_i]
                    oT = min(oT, iT)

                if outputMinUseTimeGetter is not None:
                    oT = outputMinUseTimeGetter(out, oT)
                if oT is inf:
                    continue

                clkBudget = clkWindowOffsetFromWindowBegin(oT, clkPeriod)
                if isAllowedInFFStoreTime:
                    clkBudget = max(clkBudget, clkPeriod -ffdelay)
                clkI = clkWindowIndex(oT, clkPeriod) - oTicks
                if clkBudget < oDelay:
                    clkI -= 1
                nodeZeroClkI = min(nodeZeroClkI, clkI)

            nodeZeroTime = nodeZeroClkI * clkPeriod

            assert isfinite(nodeZeroTime), (self, "Must be finite because we already checked that there is some use.")
            # the node input times are anchored to end of clk window
            # if there is not enough time for iDelay it means that schedule is not possible
            for iDelay in self.inputWireDelay:
                if iDelay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.inputWireDelay, self.outputWireDelay, self)

        nodeZeroTime = self._scheduledZeroApplyLimits(nodeZeroTime, True, False)
        nodeZeroTime = (nodeZeroTime // clkPeriod) * clkPeriod
        if nodeZeroTime > self.scheduledZero:
            self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
            for dep in self.dependsOn:
                yield dep.obj

    def scheduleAsapCompaction(self, beginOfFirstClk: SchedTime, outputTimeGetter:Optional[OutputTimeGetter]) -> \
            Generator["HlsNetNode", None, None]:
        outTimes = self.scheduledOut
        zeroClkI = self.getSchedResourceClkI()
        origSchedZero = self.scheduledZero
        origIsMulticlock = self.isMulticlock

        # self.checkScheduling()
        schedule = {}
        self.copyScheduling(schedule)
        self.resetScheduling()
        self.scheduleAsap(None, beginOfFirstClk, outputTimeGetter)
        if any(curOT > prevOT for  prevOT, curOT in zip(outTimes, self.scheduledOut)):
            self.setScheduling(schedule)
            return
        # for prevOT, curOT, o in zip(outTimes, self.scheduledOut, self._outputs):
        #    assert prevOT >= curOT, ("asap compact", o, prevOT, "->", curOT)

        assert self.getSchedResourceClkI() <= zeroClkI, (
            "asap compact", self, zeroClkI, "->", self.getSchedResourceClkI(),
            (origIsMulticlock, origSchedZero, SchedTime_format(origSchedZero, self.netlist.normalizedClkPeriod)), "->",
            (self.isMulticlock, self.scheduledZero, SchedTime_format(self.scheduledZero, self.netlist.normalizedClkPeriod)),
            'clkPeriod:', self.netlist.normalizedClkPeriod)

        # self.checkScheduling()
        if outTimes != self.scheduledOut:
            for uses in self.usedBy:
                for u in uses:
                    yield u.obj

    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod

        if not self.scheduledIn and not self.scheduledOut:
            endTime = beginTime = self.scheduledZero
            assert endTime is not None, ("Node expected to be scheduled", self)
            pass  # part ref
        else:
            endTime = beginTime = self.scheduledZero
            for i in self.scheduledIn:
                beginTime = min(beginTime, i)

            for o in self.scheduledOut:
                endTime = max(endTime, o)

            if not self.scheduledIn:
                beginTime = endTime

            if not self.scheduledOut:
                endTime = beginTime

        startClkI = clkWindowIndex(beginTime, clkPeriod)
        endClkI = clkWindowIndex(endTime, clkPeriod)
        yield from range(startClkI, endClkI + 1)

    def splitOnClkWindows(self):
        assert not self.isMulticlock, ("This node class does not have clock splitting implemented", self)
        return False


def HlsNetNodeOut_getMaxUseTime(rPort: HlsNetNodeOut) -> Optional[SchedTime]:
    uses = rPort.obj.usedBy[rPort.out_i]
    maxUseTime = None
    for u in uses:
        u: HlsNetNodeIn
        t = u.obj.scheduledIn[u.in_i]
        if maxUseTime is None:
            maxUseTime = t
        else:
            maxUseTime = max(maxUseTime, t)

    return maxUseTime
