#pragma once

#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/pool.h>

namespace hwtHls::techmap {
using OutUserCounter = size_t;

inline OutUserCounter &getOutUserCount(HlsNetNode &n) {
	return reinterpret_cast<OutUserCounter &>(n._scratchpad);
}
void resetSchedule(const pool<HlsNetNode *> &nodes);
// :attention: this expects realizezations of all nodes and
//             schedule times of primary outputs  to be set
void alapSchedule(const pool<HlsNetNode *> &nodes, SchedTime maxLatency);

} // namespace hwtHls::techmap