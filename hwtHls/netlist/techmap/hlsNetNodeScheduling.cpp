#include <algorithm>
#include <assert.h>
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <iostream>
#include <limits>
#include <sstream>

template <typename T>
std::basic_ostream<char> &operator<<(std::basic_ostream<char> &ss,
									 const std::vector<T> &vec) {
	ss << "[";
	for (auto &v : vec) {
		ss << v;
		if (&v != &vec.back())
			ss << ", ";
	}
	ss << "]";
	return ss;
}

namespace hwtHls {

void HlsNetNode::copyScheduling(SchedulingState &scheduling) const {
	scheduling.push_back(SchedulingStateItem{const_cast<HlsNetNode *>(this),
											 scheduledZero, scheduledIn,
											 scheduledOut});
}

void HlsNetNode::resetScheduling() { scheduledZero = {}; }

SchedulingState::const_iterator
HlsNetNode::setScheduling(SchedulingState::const_iterator schedBegin,
						  SchedulingState::const_iterator schedEnd) {
	assert(schedBegin != schedEnd);
	assert(schedBegin->node == this);
	return ++schedBegin;
}

void HlsNetNode::checkScheduling() const {
	// Check scheduledZero
	assert(scheduledZero.has_value() && "Node must be scheduled");

	if (scheduledZeroMin.has_value()) {
		assert(scheduledZero.value() >= scheduledZeroMin.value() &&
			   "scheduledZero >= scheduledZeroMin");
	}
	if (scheduledZeroMax.has_value()) {
		assert(scheduledZero.value() <= scheduledZeroMax.value() &&
			   "scheduledZero <= scheduledZeroMax");
	}

	// Check scheduledIn/Out existence
	assert(!scheduledIn.empty() && "scheduledIn must exist");
	assert(!scheduledOut.empty() && "scheduledOut must exist");

	// Check each input consistency
	size_t numInputs = _inputs.size();
	assert(scheduledIn.size() == numInputs && "sheduleIn size mismatch");
	assert(dependsOn.size() == numInputs && "dependsOn size mismatch");

	for (size_t i = 0; i < numInputs; ++i) {
		SchedTime iT = scheduledIn[i];
		const auto &dep = dependsOn[i];

		// Input specification consistency
		assert(dep.has_value() && "Inconsistent input specification");

		const HlsNetNode &depNode = *dep->obj;
		assert(!depNode.scheduledOut.empty() &&
			   "Predecessor must have scheduledOut");

		SchedTime oT = depNode.scheduledOut[dep->out_i];

		// Timing constraints
		assert(iT >= oT && "Input must be scheduled after connected output");
		assert(iT >= 0 && "Input scheduled before time 0");
		assert(oT >= 0 && "Predecessor output scheduled before time 0");
	}
}

void HlsNetNode::moveSchedulingTime(SchedTime offset) {
	assert(offset != 0 && "If offset is 0 this is useless to call");

	// Update execution time
	scheduledZero.value() += offset;

	// Check bounds
	if (scheduledZeroMin.has_value()) {
		assert(scheduledZero.value() >= scheduledZeroMin.value() &&
			   "scheduledZero >= scheduledZeroMin");
	}
	if (scheduledZeroMax.has_value()) {
		assert(scheduledZero.value() < scheduledZeroMax.value() &&
			   "scheduledZero < scheduledZeroMax");
	}

	// Shift all input/output times
	for (auto &t : scheduledIn) {
		t += offset;
	}
	for (auto &t : scheduledOut) {
		t += offset;
	}
}

void HlsNetNode::_setScheduleZeroTimeSingleClock(SchedTime t) {
	assert(!isMulticlock && "Multi-clock node unsupported");
	assert((!scheduledZero.has_value() || scheduledZero.value() != t) &&
		   "If time is the same this is useless to call");

	if (scheduledZeroMin.has_value()) {
		assert(t >= scheduledZeroMin.value() && "t >= scheduledZeroMin");
	}
	if (scheduledZeroMax.has_value()) {
		assert(t <= scheduledZeroMax.value() && "t <= scheduledZeroMax");
	}

	auto usableClkWindow =
		netlist.normalizedClkPeriod - netlist.schedFFSetupTime;
	// Set input times: execution - input delay
	for (size_t i = 0; i < _inputs.size(); ++i) {
		auto iT = scheduledIn[i] = t - inputWireDelay[i];
		if (!scheduleMayBeInFFStoreTime)
			assert(std::abs(iT % netlist.normalizedClkPeriod) <=
				   usableClkWindow);
	}

	// Set execution time
	scheduledZero = t;

	// Set output times: execution + output delay
	auto clkPeriod = netlist.normalizedClkPeriod;
	for (size_t o = 0; o < _outputs.size(); ++o) {
		auto oT = scheduledOut[o] = t + outputWireDelay[o];
		if (!scheduleMayBeInFFStoreTime)
			assert(std::abs(oT % clkPeriod) <= usableClkWindow);
	}
	if (!isMulticlock) {
		auto clkI = clkWindowIndex(t, clkPeriod);
		if (!scheduledIn.empty())
			assert(clkWindowIndex(*std::max_element(scheduledIn.begin(),
													  scheduledIn.end()),
									clkPeriod) == clkI);
		if (!scheduledOut.empty())
			assert(clkWindowIndex(*std::max_element(scheduledOut.begin(),
													  scheduledOut.end()),
									clkPeriod) == clkI);
	}
}

void HlsNetNode::_setScheduleZeroTimeMultiClock(SchedTime t,
												SchedTime clkPeriod,
												SchedTime epsilon,
												SchedTime ffdelay) {
	assert(scheduledZero.has_value() && scheduledZero.value() != t &&
		   "If time is the same this is useless to call");
	assert(t % clkPeriod == 0);
	if (scheduledZeroMin.has_value()) {
		assert(t >= scheduledZeroMin.value() && "t >= scheduledZeroMin");
	}
	if (scheduledZeroMax.has_value()) {
		assert(t < scheduledZeroMax.value() && "t < scheduledZeroMax");
	}
	int clkI = clkWindowIndex(t, clkPeriod);
	// Compute input times: compaction function - input delay
	for (size_t i = 0; i < _inputs.size(); ++i) {
		auto iDelay =  inputWireDelay[i];
		auto iTicks = inputClkTickOffset[i];
		SchedTime inTime = (clkI - iTicks) * clkPeriod - iDelay - epsilon;
		scheduledIn[i] = inTime;
	}

	// Set execution time
	scheduledZero = t;

	// Compute output times: compaction function + output delay
	for (size_t o = 0; o < _outputs.size(); ++o) {
		auto oTicks = outputClkTickOffset[o];
		auto oDelay = outputWireDelay[o];
		SchedTime outTime = (clkI + oTicks) * clkPeriod + oDelay;
		scheduledOut[o] = outTime;
	}
}

SchedTime HlsNetNode::schedulerJumpToPrevCycleIfRequired(
	SchedTime time, SchedTime requestedTime, SchedTime clkPeriod,
	SchedTime timeSpacingBeforeClkEnd) {
	SchedTime prevClkEndTime = clkWindowIndex(time, clkPeriod) * clkPeriod;
	if (requestedTime < prevClkEndTime || requestedTime > prevClkEndTime + clkPeriod - timeSpacingBeforeClkEnd) {
		requestedTime = prevClkEndTime - timeSpacingBeforeClkEnd;
	}
	return requestedTime;
}

// HlsNetNode::schedulerGetNormalizedTimeForInput()
//SchedTime HlsNetNode::schedulerGetNormalizedTimeForInput(
//	SchedTime availableInTime, SchedTime inWireLatency,
//	SchedTime inputClkTickOffset, SchedTime clkPeriod, SchedTime ffdelay,
//	bool isAllowedInFFStoreTime) {
//	if (isAllowedInFFStoreTime && inWireLatency == 0 && inputClkTickOffset == 0) {
//		return availableInTime;
//	}
//
//	SchedTime nextClkTime =
//		(clkWindowIndex(availableInTime, clkPeriod) + 1) * clkPeriod;
//	SchedTime timeBudget =
//		nextClkTime - availableInTime - (isAllowedInFFStoreTime ? 0 : ffdelay);
//
//	if (inWireLatency > timeBudget) {
//		availableInTime = nextClkTime;
//	}
//
//	SchedTime normalizedTime =
//		availableInTime + inWireLatency + inputClkTickOffset * clkPeriod;
//	return normalizedTime;
//}

SchedTime HlsNetNode::_scheduledZeroApplyLimits(SchedTime newNodeZeroTime,
												bool allowEarlier,
												bool allowLater) {
	if (scheduledZeroMin.has_value() &&
		newNodeZeroTime < scheduledZeroMin.value()) {
		if (allowLater) {
			return scheduledZeroMin.value();
		} else {
			throw TimeConstraintError(
				"Impossible scheduling, scheduledZeroMin specifies >= " +
				std::to_string(scheduledZeroMin.value()) + " but best is " +
				std::to_string(newNodeZeroTime));
		}
	}

	if (scheduledZeroMax.has_value() &&
		newNodeZeroTime >= scheduledZeroMax.value()) {
		if (allowEarlier) {
			return scheduledZeroMax.value();
		} else {
			throw TimeConstraintError(
				"Impossible scheduling, scheduledZeroMax specifies <= " +
				std::to_string(scheduledZeroMax.value()) + " but best is " +
				std::to_string(newNodeZeroTime));
		}
	}

	return newNodeZeroTime;
}

SchedTime clkWindowIndex(SchedTime time, SchedTime clkPeriod) {
	assert(-10 / 1000 == 0);
	assert(-1010 / 1000 == -1);
	if (time < 0) {
		return (time  + 1) / clkPeriod - 1;
	} else {
		return time / clkPeriod;
	}
}

SchedTime clkWindowEnd(SchedTime time, SchedTime clkPeriod) {
	return clkWindowBeginOfNext(time, clkPeriod) - 1;
}

SchedTime clkWindowEndOfPrev(SchedTime time, SchedTime clkPeriod) {
	return clkWindowIndex(time, clkPeriod) * clkPeriod - 1;
}

SchedTime clkWindowBeginOfNext(SchedTime time, SchedTime clkPeriod) {
	SchedTime clkI = clkWindowIndex(time, clkPeriod);
	return (clkI + 1) * clkPeriod;
}

SchedTime clkWindowOffsetFromWindowBegin(SchedTime time, SchedTime clkPeriod) {
	SchedTime clkI = clkWindowIndex(time, clkPeriod);
	// the clock window begins on left (lower) side
	if (clkI >= 0) {
		return time - (clkI * clkPeriod);
	} else {
		return -((clkI * clkPeriod) - time);
	}
}

SchedTime clkWindowOffsetFromWindowEnd(SchedTime time, SchedTime clkPeriod) {
    return clkWindowBeginOfNext(time, clkPeriod) - time;
}

// :note: Has python equivalent
SchedTime HlsNetNode::_scheduleAsap_ScheduledZero_fromInSchedule(
	SchedTime availableInTime,		 //
	SchedTime inWireLatency,		 //
	int inputClkTickOffset,			 //
	SchedTime requiredForOutputTime, //
	SchedTime ffdelay				 //
) {
	SchedTime clkPeriod = netlist.normalizedClkPeriod;

    if (inWireLatency + requiredForOutputTime >= clkPeriod) {
		std::stringstream ss;
		ss << "Impossible scheduling, clkPeriod too low for ";
		ss << inputWireDelay << ", " << outputWireDelay << "clkPeriod:" << clkPeriod << " " << *this;
        throw TimeConstraintError(ss.str());
    }

    // SchedTime normalizedTime = _schedulerGetNormalizedTimeForInput(
    //    availableInTime, inWireLatency, 0, clkPeriod, ffdelay,
    //    isAllowedInFFStoreTime);
	bool isAllowedInFFStoreTime = false;
    if (isAllowedInFFStoreTime && inWireLatency == 0 && inputClkTickOffset == 0) {
        return availableInTime;
    } else {
        SchedTime nextClkTime = (clkWindowIndex(availableInTime, clkPeriod) + 1) * clkPeriod;
        SchedTime timeBudget = nextClkTime - availableInTime;

        SchedTime requiredUntilClkEnd;
        if (isAllowedInFFStoreTime) {
            requiredUntilClkEnd = inWireLatency;
        } else if (!this->_outputs.empty()) {  // assuming _outputs is a container
            requiredUntilClkEnd = inWireLatency + requiredForOutputTime;
        } else {
            requiredUntilClkEnd = std::max(inWireLatency, ffdelay);
        }

        if (inputClkTickOffset != 0) {
            if (requiredUntilClkEnd > timeBudget) {
                inputClkTickOffset += 1;
            }
            // snapping to next clk window begin
            return nextClkTime + inputClkTickOffset * clkPeriod;
        } else {
            if (requiredUntilClkEnd > timeBudget) {
                // does not fit to this clock cycle -> move at the beginning of the next
                return nextClkTime + inWireLatency;
            } else {
                // delay of input fits well to this clock cycles
                return availableInTime + inWireLatency;
            }
        }
    }
}

// :note: Has python equivalent
const std::vector<SchedTime> &
HlsNetNode::scheduleAsap(std::vector<HlsNetNode *> *pathForDebug,
						 SchedTime beginOfFirstClk,
						 OutputTimeGetterTy outputTimeGetter) {
	if (scheduledZero.has_value()) {
		return scheduledOut; // Already scheduled
	}

	SchedTime clkPeriod = netlist.normalizedClkPeriod;
	SchedTime ffdelay = netlist.schedFFSetupTime;

	SchedTime nodeZeroTime = beginOfFirstClk;
	bool isAllowedInFFStoreTime = false;

	if (!dependsOn.empty()) {
		if (pathForDebug) {
			auto &path = *pathForDebug;
			auto it = std::find(path.begin(), path.end(), this);
			if (it != path.end()) {
				throw std::runtime_error("Cycle in graph detected");
			}
			path.push_back(this);
		}

		try {
			// Recursively schedule predecessors
			std::vector<SchedTime> inputTimes;
			inputTimes.reserve(dependsOn.size());

			for (const auto &dep : dependsOn) {
				if (outputTimeGetter) {
					auto times =
						outputTimeGetter(*dep, pathForDebug, beginOfFirstClk);
					inputTimes.push_back(times[dep->out_i]);
				} else {
					auto predOut = dep->obj->scheduleAsap(
						pathForDebug, beginOfFirstClk, nullptr);
					inputTimes.push_back(predOut[dep->out_i]);
				}
			}

			if (isMulticlock) {
				SchedTime zeroClkI = clkWindowIndex(nodeZeroTime, clkPeriod);
				// note: -1 because zeroClkI was the index of clock after
				// clock window where inputs with inputClkTickOffset=0 are
				zeroClkI -= 1;
				// [todo] use std::views::zip()
				for (size_t i = 0; i < inputTimes.size(); ++i) {
				    SchedTime availableInTime = inputTimes[i];
				    SchedTime inWireLatency = inputWireDelay[i];
				    int inputClkTickOffset = this->inputClkTickOffset[i];
				    
				    if (inWireLatency >= clkPeriod) {
				        throw TimeConstraintError("Impossible scheduling, clkPeriod too low");
				    }
				    
				    SchedTime inClkBudget = clkWindowOffsetFromWindowEnd(availableInTime, clkPeriod);
				    int zeroClkIFromThisIn = clkWindowIndex(availableInTime, clkPeriod) + inputClkTickOffset;
				    
				    if (inClkBudget < inWireLatency) {
				        // first clk can not be mapped to same clock cycle window where the connected
				        // out is
				        zeroClkIFromThisIn += 1;
				    }
				    
				    if (zeroClkI < zeroClkIFromThisIn) {
				        // must schedule at later time if any input requires it
				        zeroClkI = zeroClkIFromThisIn;
				    }
				}

				nodeZeroTime = (zeroClkI + 1) * clkPeriod;
			} else {
				// Compute minimal nodeZeroTime satisfying all input constraints
				SchedTime requiredForOutputTime =
					isMulticlock || outputWireDelay.empty()
						? 0
						: *std::max_element(outputWireDelay.begin(),
											outputWireDelay.end());
											
				if (!isAllowedInFFStoreTime)
				    if (!outputWireDelay.empty())
				        requiredForOutputTime += ffdelay;

				// [todo] use std::views::zip()
				for (size_t i = 0; i < inputTimes.size(); ++i) {
					SchedTime availableInTime = inputTimes[i];
					SchedTime inWireLatency = inputWireDelay[i];
					SchedTime inputClkTickOffset = this->inputClkTickOffset[i];
	
				//	if (inWireLatency + offsetDueOutputTime >= clkPeriod) {
				//		throw TimeConstraintError(
				//			"clkPeriod too low for wire delays");
				//	}
	            //
				//	SchedTime normalizedTime = schedulerGetNormalizedTimeForInput(
				//		availableInTime, inWireLatency, inputClkTickOffset,
				//		clkPeriod, ffdelay, scheduleMayBeInFFStoreTime);
					SchedTime newZeroTime = _scheduleAsap_ScheduledZero_fromInSchedule(
				    availableInTime, inWireLatency, inputClkTickOffset, requiredForOutputTime, ffdelay);
					if (newZeroTime > nodeZeroTime) {
						nodeZeroTime = newZeroTime;
					}
				}
	
				//// Check output timing fits in clock cycle
				//if (nodeZeroTime + offsetDueOutputTime >
				//		clkWindowEnd(nodeZeroTime, clkPeriod) -
				//			(scheduleMayBeInFFStoreTime ? 0 : ffdelay)) {
				//	nodeZeroTime = clkWindowBeginOfNext(nodeZeroTime, clkPeriod) +
				//				   *std::max_element(inputWireDelay.begin(),
				//									 inputWireDelay.end());
				//}
			}

		} catch (...) {
			if (pathForDebug) {
				pathForDebug->pop_back();
			}
			throw;
		}

		if (pathForDebug) {
			pathForDebug->pop_back();
		}
	} else {
		assert(_inputs.empty());
		nodeZeroTime = beginOfFirstClk;
	}

	// Apply scheduling limits
	nodeZeroTime = _scheduledZeroApplyLimits(nodeZeroTime, false, true);

	// Set final schedule
	if (isMulticlock) {
		SchedTime epsilon = netlist.schedEpsilon;
		_setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon,
									   ffdelay);
	} else {
		_setScheduleZeroTimeSingleClock(nodeZeroTime);
	}

	return scheduledOut;
}

/*
 * Single clock variant (inputClkTickOffset and outputClkTickOffset are all
 * zeros)
 *
 * :return: a generator of dependencies which are now possible subject to
 * compaction.
 */
std::generator<HlsNetNode *> HlsNetNode::scheduleAlapCompaction(
	SchedTime endOfLastClk,
	std::function<SchedTime(const HlsNetNodeOut &, SchedTime)>
		outputMinUseTimeGetter,
	std::function<bool(const HlsNetNode &)> excludeNode) {
	if (isMulticlock) {
		// Delegate to multi-clock version
		for (auto *dep : scheduleAlapCompactionMultiClock(
				 endOfLastClk, outputMinUseTimeGetter, excludeNode)) {
			co_yield dep;
		}
		co_return;
	}

	SchedTime ffdelay = netlist.schedFFSetupTime;
	SchedTime clkPeriod = netlist.normalizedClkPeriod;
	SchedTime nodeZeroTime = std::numeric_limits<SchedTime>::max();

	if (_outputs.empty()) {
		// no outputs, we must use some asap input time and move to end of the
		// clock
		assert(!_inputs.empty() && "Node must have at least some port");
	} else {
		std::optional<SchedTime> curZero = scheduledZero;

		for (size_t o = 0; o < _outputs.size(); ++o) {
			SchedTime outWireLatency = outputWireDelay[o];
			if (outWireLatency + ffdelay >= clkPeriod) {
				throw TimeConstraintError(
					"clkPeriod too low for output delays");
			}

			if (!usedBy[o].empty()) {
				SchedTime oZeroT = std::numeric_limits<SchedTime>::max();
				// find earliest time where this output is used
				for (const auto &dependentIn : usedBy[o]) {
					SchedTime inpTime =
						dependentIn.obj->scheduledIn[dependentIn.in_i];

					if (curZero.has_value()) {
						assert(inpTime >= curZero.value() &&
							   "Current output violates input time");
					}

					SchedTime zeroTFromUserInput = inpTime - outWireLatency;
					// if outWireLatency does not fit into space until clock
					// end, it should move to prev clk end + ffdelay +
					// outWireLatency
					assert(inpTime >= zeroTFromUserInput);
					zeroTFromUserInput = schedulerJumpToPrevCycleIfRequired(
						inpTime, zeroTFromUserInput, clkPeriod,
						ffdelay + outWireLatency);
					oZeroT = std::min(oZeroT, zeroTFromUserInput);
				}

				if (outputMinUseTimeGetter) {
					oZeroT = outputMinUseTimeGetter(_outputs[o], oZeroT);
				}

				nodeZeroTime = std::min(nodeZeroTime, oZeroT);
			}
		}
	}
	for (HlsNetNode *n : scheduleAlapCompactionUpdateFromInputDelays(
			 nodeZeroTime, endOfLastClk)) {
		co_yield n;
	}
}

/*
 * part of scheduleAlapCompaction method, this is takes max nodeZeroTime
 * computed from outputs and applies clock window overflows moving the node to
 * previous clock window so the the schedule does not overlap the clock window
 * boundary in unintended way
 **/
std::generator<HlsNetNode *>
HlsNetNode::scheduleAlapCompactionUpdateFromInputDelays(
	SchedTime nodeZeroTime, SchedTime endOfLastClk) {
	SchedTime clkPeriod = netlist.normalizedClkPeriod;
	assert(endOfLastClk % clkPeriod == 0);
	SchedTime ffdelay = netlist.schedFFSetupTime;
	SchedTime maxOutputLatency =
		outputWireDelay.empty()
			? 0
			: *std::max_element(outputWireDelay.begin(), outputWireDelay.end());
	if (scheduledZero.has_value() && scheduledZero.value() > nodeZeroTime) {
		if (clkPeriod - clkWindowOffsetFromWindowBegin(scheduledZero.value(),
													   clkPeriod) <
			ffdelay + maxOutputLatency) {
			throw TimeConstraintError("Node end overlaps FF store time");
		}
		// this can happen if successor nodes were packed inefficiently in
		// previous cycles and it moved this node. We can not move this node
		// because it would potentially move whole circuit which would
		// eventually result in an endless cycle in scheduling
		throw TimeConstraintError(
			"Cannot schedule earlier than current ALAP time");
	}
	if (nodeZeroTime != std::numeric_limits<SchedTime>::max()) {
		if (!scheduleMayBeInFFStoreTime) {
			assert((nodeZeroTime + maxOutputLatency) % clkPeriod <=
				   clkPeriod - ffdelay);
		}
		// Check input delays fit
		for (SchedTime inDelay : inputWireDelay) {
			if (inDelay + ffdelay >= clkPeriod) {
				throw TimeConstraintError("clkPeriod too low for input delays");
			}
		}

		SchedTime maxInDelay = inputWireDelay.empty()
								   ? 0
								   : *std::max_element(inputWireDelay.begin(),
													   inputWireDelay.end());
		SchedTime inTime = nodeZeroTime - maxInDelay;
		nodeZeroTime = schedulerJumpToPrevCycleIfRequired(
						   nodeZeroTime, inTime, clkPeriod,
						   maxInDelay + maxOutputLatency + ffdelay) +
					   maxInDelay;
	} else {
		// no use of any output, we must use some ASAP input time and move to
		// end of the clock
		assert(!_inputs.empty() && "Node must have ports");
		nodeZeroTime =
			endOfLastClk - (ffdelay + maxOutputLatency) - netlist.schedEpsilon;
	}

	nodeZeroTime = _scheduledZeroApplyLimits(nodeZeroTime, true, false);

	if (!scheduledZero.has_value() || scheduledZero.value() != nodeZeroTime) {
		_setScheduleZeroTimeSingleClock(nodeZeroTime);

		// Yield dependencies for compaction
		for (const auto &dep : dependsOn) {
			co_yield dep->obj;
		}
	}
}

std::generator<HlsNetNode *> HlsNetNode::scheduleAlapCompactionMultiClock(
	SchedTime endOfLastClk,
	std::function<SchedTime(const HlsNetNodeOut &, SchedTime)>
		outputMinUseTimeGetter,
	std::function<bool(const HlsNetNode &)> excludeNode) {
	/**
	 * Move node to a later time if possible. Netlist is expected to be
	 * scheduled. This allows to move trees of nodes to later times and allow
	 * for possibly better fit of nodes to a clock period windows.
	 *
	 * :return: generator of nodes for compaction worklist
	 */
	assert(isMulticlock && "Must be multiclock node");

	// if all dependencies have inputs scheduled we schedule this node and try
	// successors
	SchedTime ffdelay = netlist.schedFFSetupTime;
	SchedTime clkPeriod = netlist.normalizedClkPeriod;
	SchedTime epsilon = netlist.schedEpsilon;

	SchedTime nodeZeroTime;
	if (_outputs.empty() ||
		!std::any_of(usedBy.begin(), usedBy.end(),
					 [](const auto &uses) { return !uses.empty(); })) {
		// no outputs, we must use some ASAP input time and move to end of the
		// clock
		assert(!_inputs.empty() && "Node must have at least some port.");
		nodeZeroTime = endOfLastClk + epsilon;
	} else {
		// move back in time to satisfy all output timing requirements
		SchedTime nodeZeroClkI = std::numeric_limits<SchedTime>::max();
		for (size_t o = 0; o < _outputs.size(); ++o) {
			const auto &out = _outputs[o];
			const auto &uses = usedBy[o];
			SchedTime oDelay = outputWireDelay[o];
			int oTicks = outputClkTickOffset[o];

			// find earliest time where this output is used
			SchedTime oT = std::numeric_limits<SchedTime>::max();
			for (const auto &dependentIn : uses) {
				SchedTime iT =
					dependentIn.obj->scheduledIn[dependentIn.in_i];
				oT = std::min(oT, iT);
			}
			
			if (outputMinUseTimeGetter) {
				oT = outputMinUseTimeGetter(out, oT);
			}
			if (oT ==  std::numeric_limits<SchedTime>::max())
			    continue;

			auto clkBudget = clkWindowOffsetFromWindowEnd(oT, clkPeriod);
			if (scheduleMayBeInFFStoreTime)
			    clkBudget -= ffdelay;
			auto clkI = clkWindowIndex(oT, clkPeriod) - oTicks;
			if (clkBudget < oDelay) {
			    clkI -= 1;
			}
			nodeZeroClkI = std::min(nodeZeroClkI, clkI);
		}
		nodeZeroTime = nodeZeroClkI * clkPeriod;

		assert(nodeZeroTime != std::numeric_limits<SchedTime>::max() &&
			   "Must be finite because we already checked that there is some "
			   "use.");

		// we have to check if every input has enough time for its delay
		// and optionally move this node to previous clock cycle
		for (SchedTime iDelay : inputWireDelay) {
			if (iDelay + ffdelay >= clkPeriod) {
				std::stringstream err;
				err << "Impossible scheduling, clkPeriod too low for ";
				err << inputWireDelay << " " << outputWireDelay << __repr__();
				throw TimeConstraintError(err.str());
			}
		}
	}

	nodeZeroTime = _scheduledZeroApplyLimits(nodeZeroTime, true, false);

	if (scheduledZero.has_value() && nodeZeroTime > scheduledZero.value()) {
		_setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon,
									   ffdelay);
		for (const auto &dep : dependsOn) {
			co_yield dep->obj;
		}
	}
}

std::generator<HlsNetNode *>
HlsNetNode::scheduleAsapCompaction(SchedTime beginOfFirstClk,
								   OutputTimeGetterTy outputTimeGetter) {
	auto outTimes = scheduledOut;
	auto zeroTime = scheduledZero;

	SchedulingState schedule;
	copyScheduling(schedule);
	resetScheduling();

	scheduleAsap(nullptr, beginOfFirstClk, outputTimeGetter);

	bool anyOutputLater = false;
	for (size_t i = 0; i < outTimes.size(); ++i) {
		if (scheduledOut[i] > outTimes[i]) {
			anyOutputLater = true;
			break;
		}
	}
	if (anyOutputLater) {
		setScheduling(schedule.begin(), schedule.end());
		co_return;
	}

	assert(scheduledZero.has_value() &&
		   scheduledZero.value() <= zeroTime.value());

	if (outTimes != scheduledOut) {
		for (const auto &uses : usedBy) {
			for (const auto &u : uses) {
				co_yield u.obj;
			}
		}
	}
}

} // namespace hwtHls
