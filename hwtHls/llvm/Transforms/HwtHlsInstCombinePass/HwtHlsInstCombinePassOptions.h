#pragma once
#include <cstddef>
#include <string>
#include <functional>
#include <llvm/IR/Function.h>

namespace hwtHls {

class HwtHlsInstCombinePassOptions {
public:
	// enable extractions of ctpop, ctlz, cttz and alike, note that this has high time complexity
	// as it may start to match many instructions on many places
	// :note: extractions of bitcounts may aslo prevent other optimizations to be applied
	bool extractBitcounts;

	// specifies minimum bits of bitcount instruction for extraction
	size_t bitcountExtractionTreshold;

	// merge mergable/vectorizable functions call to wider calls
	bool mergeMergableFunctionCalls;

	// depth used when called computeKnownBits
	size_t computeKnownBitsDepth;

	// speculate value of stream read EoF, to create two variants of code for (EoF=0 and EoF=1) and merge them with SelectInst on top,
	// It is highly probable that the separated versions of expressions will be much more simple
	// than one merged.
	bool streamReadEoFThreading;

	// enable floating point combining rules which may generate hwtHls specific intrinsic
	bool hwtHlsFpCombining;

	// max number how many times to run optimization of function,
	// note that the HwtHlsInstCombinePass uses worklist and 1 should be sufficient, but for debugging purposes
	// there is this option which can be used to check if problem happened because something was not added to worklist
	// when it should.
	size_t MaxIterations;

	using IrChangeCallbackFn = std::function<void(const std::string & ruleName, const llvm::Function & F)>;
	IrChangeCallbackFn* _dbgIrInstrCombineChangeCallbackFn = nullptr;
	
	HwtHlsInstCombinePassOptions(bool extractBitcounts = true,
			size_t bitcountExtractionTreshold = 2,
			bool mergeMergableFunctionCalls = true,
			size_t computeKnownBitsDepth = 8, bool streamReadEoFThreading =
					false, bool hwtHlsFpCombining = false,
			size_t MaxIterations = 1) :
			extractBitcounts(extractBitcounts), bitcountExtractionTreshold(
					bitcountExtractionTreshold), mergeMergableFunctionCalls(
					mergeMergableFunctionCalls), computeKnownBitsDepth(
					computeKnownBitsDepth), streamReadEoFThreading(
					streamReadEoFThreading), hwtHlsFpCombining(
					hwtHlsFpCombining), MaxIterations(MaxIterations) {
	}

	HwtHlsInstCombinePassOptions& setMergeMergableFunctionCalls(
			bool mergeMergableFunctionCalls) {
		this->mergeMergableFunctionCalls = mergeMergableFunctionCalls;
		return *this;
	}
	HwtHlsInstCombinePassOptions& setStreamReadEoFThreading(
			bool streamReadEoFThreading) {
		this->streamReadEoFThreading = streamReadEoFThreading;
		return *this;
	}

	HwtHlsInstCombinePassOptions& setHwtHlsFpCombining(bool hwtHlsFpCombining) {
		this->hwtHlsFpCombining = hwtHlsFpCombining;
		return *this;
	}
	HwtHlsInstCombinePassOptions& setdbgIrInstrCombineChangeCallbackFn(IrChangeCallbackFn * fn) {
		_dbgIrInstrCombineChangeCallbackFn = fn;
		return *this;
	}
};

}
