#pragma once
#include <coroutine>
#include <cstddef>
#include <functional>
#include <generator>
#include <iterator>
#include <memory>
#include <optional>
#include <stdint.h>
#include <vector>

namespace hwtHls {

class HlsNetNode;

// :note: HlsNetNodeIn/HlsNetNodeOut obj is not reference to avoid confusion for
// std::vector and alike

// :note: there is a potential problem with the fact that in python the
// HlsNetNodeIn/Out object is a value
//  copied from its own vector container on HlsNetNode
class HlsNetNodeIn {
public:
	HlsNetNode *obj;
	size_t in_i;
	HlsNetNodeIn(HlsNetNode &obj);
	bool operator==(const HlsNetNodeIn &RHS) const;
};

class HlsNetNodeOut {
public:
	HlsNetNode *obj;
	size_t out_i;
	HlsNetNodeOut(HlsNetNode &obj);
	void connectHlsIn(const HlsNetNodeIn &in)
		const; // :note: const because it does not modify the the value s in
			   // HlsNetNodeOut itself
	bool operator==(const HlsNetNodeOut &RHS) const;
};

class HlsNetNodeFlags {
public:
	bool isPrimaryIn;
	bool isPrimaryOut;
	HlsNetNodeFlags() :
		isPrimaryIn(false), isPrimaryOut(false) {}
};

class HlsNetNodeInDepNodes {
public:
	struct Iterator {
		using iterator_category = std::forward_iterator_tag;
		using difference_type = std::ptrdiff_t;
		using value_type = HlsNetNode;
		using pointer = HlsNetNode *;
		using reference = HlsNetNode &;

		Iterator(std::vector<std::optional<HlsNetNodeOut>>::iterator ptr,
				 std::vector<std::optional<HlsNetNodeOut>>::iterator end);

		reference operator*() const;
		pointer operator->();
		Iterator &operator++();
		Iterator operator++(int);
		bool operator==(const Iterator &b) const;
		bool operator!=(const Iterator &b) const;

	private:
		std::vector<std::optional<HlsNetNodeOut>>::iterator m_ptr;
		std::vector<std::optional<HlsNetNodeOut>>::iterator m_end;
	};

	Iterator begin();
	Iterator end();

	HlsNetNodeInDepNodes(HlsNetNode &node);

private:
	HlsNetNode &node;
};

class HlsNetNodeOutUserNodes {
public:
	using UseListIt = std::vector<std::vector<HlsNetNodeIn>>::iterator;
	static constexpr std::vector<HlsNetNodeIn>::iterator _VEC_VEC_IN_END = {};
	struct Iterator {
		using iterator_category = std::forward_iterator_tag;
		using difference_type = std::ptrdiff_t;
		using value_type = HlsNetNode;
		using pointer = HlsNetNode *;
		using reference = HlsNetNode &;

		Iterator(UseListIt uselistIt, UseListIt uselistItEnd,
				 std::vector<HlsNetNodeIn>::iterator inUseListPos);

		reference operator*() const;
		pointer operator->();
		Iterator &operator++();
		Iterator operator++(int);
		bool operator==(const Iterator &b) const;
		bool operator!=(const Iterator &b) const;

	private:
		UseListIt m_uselist;
		UseListIt m_uselist_end;
		std::vector<HlsNetNodeIn>::iterator m_uselist_pos;
	};

	Iterator begin();
	Iterator end();
	HlsNetNodeOutUserNodes(HlsNetNode &node);

private:
	HlsNetNode &node;
};

using SchedTime = int64_t;

class HlsNetlistCtx {
	size_t _uniqNodeCntr;
	size_t getUniqId();

public:
	std::vector<std::unique_ptr<HlsNetNode>> nodes;
	SchedTime schedEpsilon;
	SchedTime normalizedClkPeriod;
	SchedTime schedFFSetupTime;

	HlsNetlistCtx(SchedTime normalizedClkPeriod, SchedTime schedFFSetupTime) :
		_uniqNodeCntr(0),
		schedEpsilon(1),
		normalizedClkPeriod(normalizedClkPeriod),
		schedFFSetupTime(schedFFSetupTime) {}
	// :note: if id is specified it is responsibility of caller to assert that
	// the id is unique
	HlsNetNode *createNode(size_t inCnt, size_t outCnt,
						   std::optional<size_t> id = {});
};

struct SchedulingStateItem {
	HlsNetNode *node;
	std::optional<SchedTime> scheduleZero;
	std::vector<SchedTime> scheduleIn;
	std::vector<SchedTime> scheduleOut;
};

using SchedulingState = std::vector<SchedulingStateItem>;

/*
 * Enum for recursive iteration of HlsNetNode
 *
 * :note: parent in this context means HlsNetNodeAggregate, children are nodes
 * directly in it
 *
 * :ivar PREORDER: parent before children
 * :ivar POSTORDER: children before parent
 * :ivar OMMIT_PARENT: only children (no HlsNetNodeAggregate instances)
 * :ivar ONLY_PARENT_PREORDER: iterate  HlsNetlistCtx/HlsNetNodeAggregate
 * instances only, parent is yielded first :ivar ONLY_PARENT_POSTORDER: same as
 * ONLY_PARENT_PREORDER but parent is yielded last
 */
enum class NODE_ITERATION_TYPE {
	PREORDER,
	POSTORDER,
	OMMIT_PARENT,
	ONLY_PARENT_PREORDER,
	ONLY_PARENT_POSTORDER,
};

class HlsNetNode {
public:
	HlsNetlistCtx &netlist;
	size_t _id;
	HlsNetNodeFlags flags;

	void *_scratchpad; // a pointer on a pass private structure associated with
					   // this node
	// :attention: should be cleared on the end of the pass if used
	template <typename PrivT> PrivT &scratchpad() {
		*static_cast<PrivT *>(_scratchpad);
	}

	// ports and their connections
	std::vector<HlsNetNodeIn> _inputs;
	std::vector<std::optional<HlsNetNodeOut>>
		dependsOn; // connected output for every input, std::optional to be able
				   // represent the case where input id disconnected
	std::vector<HlsNetNodeOut> _outputs;
	std::vector<std::vector<HlsNetNodeIn>>
		usedBy; // list of users for every output

	// scheduling times
	std::optional<SchedTime>
		scheduledZero; // std::optional to be able to represent the case where
					   // node is not scheduled
	std::optional<SchedTime>
		scheduledZeroMin; // :note: scheduledZeroMin/Max is used to constraint
						  // the time range where the node can be scheduled.
	std::optional<SchedTime> scheduledZeroMax;
	std::vector<SchedTime> scheduledIn; // sheduleIn/sheduleOut is always of the
										// same size as _inputs/_outputs
	std::vector<SchedTime> scheduledOut;

	// delays/latencies and alike props for scheduling
	bool isMulticlock;
	bool scheduleMayBeInFFStoreTime;
	std::vector<SchedTime> inputWireDelay;
	std::vector<size_t> inputClkTickOffset;
	std::vector<SchedTime> outputWireDelay;
	std::vector<size_t> outputClkTickOffset;

	HlsNetNode(HlsNetlistCtx &context, size_t id) :
		netlist(context),
		_id(id),
		_scratchpad(nullptr),
		isMulticlock(false),
		scheduleMayBeInFFStoreTime(false) {}
	// port related methods
	const HlsNetNodeIn _addInput();
	const HlsNetNodeOut _addOutput();
	HlsNetNodeInDepNodes iterInDepNodes();
	HlsNetNodeOutUserNodes iterOutUserNodes();
	virtual std::generator<HlsNetNode *>
	iterAllNodesFlat(NODE_ITERATION_TYPE itTy);

	// utilities

	friend std::ostream& operator<< (std::ostream& out, const HlsNetNode& node) {
		return out << node.__repr__();
	}
	virtual std::string __repr__() const;

	// scheduling related methods
	virtual void copyScheduling(SchedulingState &scheduling) const;
	virtual void resetScheduling();
	virtual SchedulingState::const_iterator
	setScheduling(SchedulingState::const_iterator schedBegin,
				  SchedulingState::const_iterator schedEnd);
	virtual void checkScheduling() const;
	virtual void
	moveSchedulingTime(SchedTime offset); // move scheduling time without any
										  // additional check or re-computation
	void _setScheduleZeroTimeSingleClock(SchedTime t);
	void _setScheduleZeroTimeMultiClock(SchedTime t, SchedTime clkPeriod,
										SchedTime epsilon, SchedTime ffdelay);
	static SchedTime
	schedulerJumpToPrevCycleIfRequired(SchedTime time, SchedTime requestedTime,
									   SchedTime clkPeriod,
									   SchedTime timeSpacingBeforeClkEnd);
	//static SchedTime schedulerGetNormalizedTimeForInput(
	//	SchedTime availableInTime, SchedTime inWireLatency,
	//	SchedTime inputClkTickOffset, SchedTime clkPeriod, SchedTime ffdelay,
	//	bool isAllowedInFFStoreTime);
	SchedTime _scheduledZeroApplyLimits(SchedTime newNodeZeroTime,
										bool allowEarlier, bool allowLater);

	using OutputTimeGetterTy = std::function<std::vector<SchedTime>(
		const HlsNetNodeOut &,
		std::vector<HlsNetNode *> *, // optional path of nodes for debug of
									 // cycles
		SchedTime					 // beginOfFirstClk
		)>;
	SchedTime _scheduleAsap_ScheduledZero_fromInSchedule(
		SchedTime availableInTime,		 //
		SchedTime inWireLatency,		 //
		int inputClkTickOffset,			 //
		SchedTime requiredForOutputTime, //
		SchedTime ffdelay				 //
	);
	virtual const std::vector<SchedTime> &
	scheduleAsap(std::vector<HlsNetNode *>
					 *pathForDebug, // pathForDebug is optional path to check
									// for cycles in scheduling
				 SchedTime beginOfFirstClk,
				 OutputTimeGetterTy outputTimeGetter = nullptr);
	virtual std::generator<HlsNetNode *> scheduleAlapCompaction(
		SchedTime endOfLastClk,
		std::function<SchedTime(const HlsNetNodeOut &, SchedTime)>
			outputMinUseTimeGetter = nullptr,
		std::function<bool(const HlsNetNode &)> excludeNode = nullptr);

	std::generator<HlsNetNode *>
	scheduleAlapCompactionUpdateFromInputDelays(SchedTime nodeZeroTime,
												SchedTime endOfLastClk);
	std::generator<HlsNetNode *> scheduleAlapCompactionMultiClock(
		SchedTime endOfLastClk,
		std::function<SchedTime(const HlsNetNodeOut &, SchedTime)>
			outputMinUseTimeGetter = nullptr,
		std::function<bool(const HlsNetNode &)> excludeNode = nullptr);
	virtual std::generator<HlsNetNode *>
	scheduleAsapCompaction(SchedTime beginOfFirstClk,
						   OutputTimeGetterTy outputTimeGetter = nullptr);
	virtual ~HlsNetNode() {}

	template <typename SequenceT>
	static void scratchpadClear(SequenceT &nodes) {
		for (HlsNetNode *node : nodes) {
			node->_scratchpad = nullptr;
		}
	}
};

SchedTime clkWindowIndex(SchedTime time, SchedTime clkPeriod);
SchedTime clkWindowEnd(SchedTime time, SchedTime clkPeriod);
// :note: endOfPrevClk == begin of this clk window 
SchedTime clkWindowEndOfPrev(SchedTime time, SchedTime clkPeriod);
SchedTime clkWindowBeginOfNext(SchedTime time, SchedTime clkPeriod);
SchedTime clkWindowOffsetFromWindowBegin(SchedTime time, SchedTime clkPeriod);
SchedTime clkWindowOffsetFromWindowEnd(SchedTime time, SchedTime clkPeriod);

	
class TimeConstraintError : public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

} // namespace hwtHls

namespace std {

template <> struct hash<pair<hwtHls::HlsNetNode *, hwtHls::HlsNetNode *>> {
	size_t operator()(const pair<hwtHls::HlsNetNode *, hwtHls::HlsNetNode *> &p)
		const noexcept {
		size_t h1 = hash<hwtHls::HlsNetNode *>{}(p.first);
		size_t h2 = hash<hwtHls::HlsNetNode *>{}(p.second);
		return h1 ^ (h2 << 1);
	}
};

template <> struct hash<hwtHls::HlsNetNodeIn> {
	size_t operator()(const hwtHls::HlsNetNodeIn &p) const noexcept {
		size_t h1 = hash<hwtHls::HlsNetNode *>{}(p.obj);
		size_t h2 = hash<size_t>{}(p.in_i);
		return h1 ^ (h2 << 1);
	}
};

template <> struct hash<hwtHls::HlsNetNodeOut> {
	size_t operator()(const hwtHls::HlsNetNodeOut &p) const noexcept {
		size_t h1 = hash<hwtHls::HlsNetNode *>{}(p.obj);
		size_t h2 = hash<size_t>{}(p.out_i);
		return h1 ^ (h2 << 1);
	}
};

} // namespace std
