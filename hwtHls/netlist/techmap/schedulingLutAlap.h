#pragma once

#include <hwtHls/netlist/techmap/flowmap_yosys.h>
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/pool.h>

namespace hwtHls::techmap {
/*
 * Variant of alapSchedule which uses explicit dictionary for backedges instead
 * of connection of nodes.
 * :param nodeLatency: how long the operation of the node takes
 * :param clkPeriod: the duration of clock window
 * :param ffPreSetTime: the margin at the end of the clock window where
 *                      the operation of normal nodes should not be scheduled
 * :param endOfLastClk: the max time in the schedule
 * :param afterNodeScheduled: in this callback it is possible to update
 *                            other nodes if the selected nodes are not
 * connected directly together
 * */
// :attention: this expect that the time for primary outputs is set
void scheduleLutAlap(FlowmapWorker &fmw, SchedTime lutDelay,
					 SchedTime endOfLastClk);
} // namespace hwtHls::techmap