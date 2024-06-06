#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/// Loop unroll for loops which are dependent on some stream IO
//
//  This form of loop unroll also copies loop body N-times,
//  however this works more like predicated vectorization as each loop body represents
//  a functional unit which processes one chunk of the data. Thus loop body represents a lane.
//  Each lane is guarded by "if" which enables lane if stream offset is of value matching this lane dedication.
//  If data chunk boundary is not aligned to stream word boundary the chunk processing is postponed
//  to next iteration until the chunk is completed, the offset is then always aligned to the beginning of the word.
//
//  :note: If chunk is crossing word boundary, the chunk size is too large
//    or it does not matter, that there is 1 iteration latency,
//    because complete chunk is requested.
//    Thus this does not affect throughput or optimality of the result.
//  :note: The number of lanes is parametrized, maximum number is ceil(data_width/chunk_width)
//  :note: Lanes are represented as a serial codes linked in series which resides in the original loop.
//         (as it is common in the case of loop unroll)
//         The number of bytes processed by lane can be variable.
//  :note: This pass handles both input and output stream IO.
class StreamLoopUnrollPass: public llvm::PassInfoMixin<StreamLoopUnrollPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
