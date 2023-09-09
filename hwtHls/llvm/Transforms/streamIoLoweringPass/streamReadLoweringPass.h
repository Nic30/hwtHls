#pragma once
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {


/**
Lower the read of abstract data type from AMBA AXI-stream interfaces to a read of native interface words.

1. Build CFG of parsing and in stream chunk positions
	* DFS search the SSA for reads and compute the offset
2. Rewrite reads of ADTs to read of words

:note: Problematic features
	* SSA CFG does not correspond to read CFG
		* blocks may not contain reads, there there can be multiple paths between same reads
		* cycles in SSA does not necessary mean a cycle in read CFG


If we could use a global state of the parser it would be simple:
	* we would just generate FSM where for each word we would distribute the data to field variables
	* FSM transition table can be directly generated from readGraph

However on SSA level the parse graph is not linear and many branches of code do contain reads, which may be optional
which complicates the resolution of which read was actually last word, which is required by next read.
In order to solve this problem we must generate variables which will contain the value of this last word
and a variable which will contain the offset in this last word.

The rewrite does:
	* convert all reads to reads of native stream words
	* move as many reads of stream words as possible to parent blocks to simplify their condition
	* generate last word and offset variable
	* use newly generated variables to select the values of the read data
		* in every block the value of offset is resolved
		* if the block requires the value the phi without operands is constructed
		* phi operands are filled in
	* for every read/write which may fail (due to premature end of frame) generate erorr handler jumps

:attention: If there are reads on multiple input streams this may result in changed order in which bus words are accepted
   which may result in deadlock.
 */
class StreamReadLoweringPass: public llvm::PassInfoMixin<StreamReadLoweringPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
