#pragma once

#include <set>
#include <llvm/IR/BasicBlock.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

namespace hwtHls {

/*
 * Structure for pattern with linear sequence of blocks with a common successor which is on T branch,
 * exit can has only BB0-n predecessors:
 *
 * .. code-block::text
 *      BB0-BB1 ...
 *        \ |  /
 *        exit
 *
 * :attention: there may be some additional blocks in between blocks in chain (BB0, BB1, ...)
 * */
struct CfgFragmentChainOfblocksWithSameSucc {
public:
	struct BasicBlockAndBrCond {
		llvm::BasicBlock *BB;
		llvm::Value *toExitBrCond; // for last block in chain this is allowed to be nullptr
		bool toExitBrCondIsNegated; // if true exit bb is successor 0 else 1

		BasicBlockAndBrCond(llvm::BasicBlock *BB, llvm::Value *toExitBrCond,
				bool toExitBrCondIsNegated) :
				BB(BB), toExitBrCond(toExitBrCond), toExitBrCondIsNegated(
						toExitBrCondIsNegated) {
		}
	};

	llvm::SmallVector<BasicBlockAndBrCond> blocks;
	llvm::BasicBlock *exit;

	CfgFragmentChainOfblocksWithSameSucc();

	static std::pair<llvm::BasicBlock*, std::optional<BasicBlockAndBrCond>> detectOne(
			llvm::BasicBlock &BB, llvm::BasicBlock &exit);
	//static std::optional<CfgFragmentChainOfblocksWithSameSucc> detect(
	//		llvm::BasicBlock &exitBB);
	template<typename ResultT = CfgFragmentChainOfblocksWithSameSucc,
			typename PartResultT = BasicBlockAndBrCond>
	static std::optional<ResultT> detect(llvm::BasicBlock &exitBB, ResultT &res,
			llvm::BasicBlock *searchBeginOverride = nullptr,
			bool exitMayHaveAdditionalPreds = false);
};

template<typename ResultT, typename PartResultT>
std::optional<ResultT> CfgFragmentChainOfblocksWithSameSucc::detect(
		llvm::BasicBlock &exitBB, ResultT &res,
		llvm::BasicBlock *searchBeginOverride,
		bool exitMayHaveAdditionalPreds) {
	if (pred_empty(&exitBB))
		return {};

	res.exit = &exitBB;
	llvm::BasicBlock *BBSearchStart = *predecessors(&exitBB).begin(); // pick any predecessor block
	if (searchBeginOverride)
		BBSearchStart = searchBeginOverride;

	auto *BB = BBSearchStart;
	std::set<llvm::BasicBlock*> seen;
	llvm::SmallVector<PartResultT> blocksFromUpSearch; // in bottom to top order
	if (BB == &exitBB)
		return {}; // exitBB itself is a loop this can not be a linear sequence of predecessors

	// search up
	llvm::BasicBlock *bbTUpSeachNextForDown = nullptr;
	for (;;) {
		if (seen.contains(BB)) {
			// BB is a part of cycle and thus it can not be a linear sequence
			break;
		} else {
			seen.insert(BB);
		}
		llvm::BasicBlock *_bbTUpSeachNextForDown;
		std::optional<PartResultT> frag;
		std::tie(_bbTUpSeachNextForDown, frag) = res.detectOne(*BB, *res.exit);
		if (!bbTUpSeachNextForDown) {
			// capture only on begin of "to up" search (on most down block)
			bbTUpSeachNextForDown = _bbTUpSeachNextForDown;
		}
		if (_bbTUpSeachNextForDown) {
			blocksFromUpSearch.push_back(frag.value());
		}
		if (pred_size(BB) != 1) {
			// not a continuation of linear sequence
			// but first is allowed to have multiple predecessors because whole
			// linear sequence of blocks is allowed to to be entered from multiple blocks
			break;
		}
		BB = *predecessors(BB).begin();
		if (BB == &exitBB)
			break; // exitBB jumps at the first block in predecessor sequence
	}
	// convert from bottom to top order to top to bottom order
	for (PartResultT &BBItem : reverse(blocksFromUpSearch)) {
		res.blocks.push_back(BBItem);
	}
	BB = bbTUpSeachNextForDown ? bbTUpSeachNextForDown : BBSearchStart;
	if (BB != res.exit) {
		seen.erase(BB);
		// search down
		for (;;) {
			bool first = res.blocks.empty() || BB == res.blocks[0].BB;
			if (!first && pred_size(BB) != 1) {
				break; // block BB in chain has predecessor which is not a predecessor in chain
			} else if (seen.contains(BB)) {
				break; // cycle found, this can not be linear sequence of blocks ending in exit
			} else {
				seen.insert(BB);
			}

			std::optional<PartResultT> frag;
			std::tie(BB, frag) = res.detectOne(*BB, *res.exit);
			if (!first && frag.has_value()) {
				assert(
						!llvm::any_of(res.blocks,
								[BB, &frag](PartResultT &item) {
									return item.BB == frag.value().BB;
								})
								&& "The duplicate item can be only bug in this function");
				res.blocks.push_back(frag.value());
			}
			if (!BB) {
				break; // next pattern part not detected
			} else if (BB == res.exit
					|| (!res.blocks.empty() && BB == res.blocks[0].BB)) {
				// allow jump from last BB back to first
				break;
			}
			// else continue search on next successor which is not exit
		}
	}
	if (!exitMayHaveAdditionalPreds
			&& res.blocks.size() != pred_size(&exitBB)) {
		return {};
	} else {
		return res;
	}
}

}
