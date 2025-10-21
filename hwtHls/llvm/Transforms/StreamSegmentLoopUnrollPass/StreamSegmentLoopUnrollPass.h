#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/// Loop unroll for loops which are dependent on some segmented stream IO
//
//  The StreamLoopUnrollPass unrolls all chunk access to access of segment-width
//  This StreamSegmentLoopUnrollPass then unrolls code preprocessed by StreamLoopUnrollPass
//  for each segment of stream IO
//  This pass effectively creates a circuit which processes fixed input/output data bits and
//  muxing the input/output state between them.

// Transformation of packet loop for segmented bus (3 segments)
// * The loop in input code with access aligned to segment boundaries
// * The loop in output code has access aligned to bus word boundary
//
// * The original code of segment is copied N times
// * Each read is removed and block is split on that place
//    Read value is taken from read of bus word.
// * Each segment works always with the same slice of bus word
//   and with one set of liveins at the time.
// * Begin part of split block jumps to end of the same block in the next segment.
// * %word.dispatch is only block with bus read
// * %word.dispatch + %word.latch interprets jump on the boundary of bus word
// * :note: parent loop is not required
// * backedge of %data can be replaced with jump to" %data.load_next_word end"
//   if next loop iteration leads to next load and there
//   is no instruction with side-effect before it (in this case "if d.last")
//
// :attention: if the input code itself does not contain checks for eof/sof/enable
//    even after this transformation the code will process only frames
//    starting on some segments because there is simply no jump to next sof
//    if segment has empty=0, and thus frame sof check is locked to some segments
//    (depending on where the frame may end)
//    To implement expected behavior of processing all sofs in the bus word
//    the original code must contain handling of enable and eof/sof.
//    Then this transformation will expand this handler code to all segments.

class StreamSegmentLoopUnrollPass: public llvm::PassInfoMixin<StreamSegmentLoopUnrollPass> {
public:
	static const std::string METADATA_NAME_io;
	static const std::string METADATA_NAME_allowSoFOnlyFor;

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
