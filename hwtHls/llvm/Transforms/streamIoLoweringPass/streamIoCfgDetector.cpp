#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>

#include <algorithm>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

namespace hwtHls {

llvm::raw_ostream& StreamChunkLastMeta::print(llvm::raw_ostream &OS) const {
	OS << "<StreamChunkLastMeta isLast:" << isLast << " isLastExpr:";
	if (isLastExpr) {
		OS << *isLastExpr;
	} else {
		OS << "nullptr";
	}
	if (prevWordMayBePending) {
		OS << " prevWordMayBePending";
	}
	OS << ">";
	return OS;
}

llvm::raw_ostream& StreamEoFMeta::print(llvm::raw_ostream &OS) const {
	OS << "<StreamEoFMeta ";
	if (inlinedToPredecessors) {
		OS << " inlinedToPredecessors";
	}
	OS << ">";
	return OS;
}

StreamIoDetector::StreamIoDetector(size_t DATA_WIDTH,
		const llvm::SetVector<const HlsReadOrWrite*> &allStms) :
		DATA_WIDTH(DATA_WIDTH), allStms(allStms) {
	cfg[nullptr] = { };
}

void StreamIoDetector::_addTransition(const HlsReadOrWrite *src,
		size_t dstInWordOffset, const HlsReadOrWrite *dst) {
	auto succIt = cfg.find(src);
	if (succIt == cfg.end()) {
		llvm::SetVector<std::pair<size_t, const HlsReadOrWrite*>> sucList;
		sucList.insert( { dstInWordOffset, dst });
		cfg[src] = sucList;
	} else {
		succIt->second.insert( { dstInWordOffset, dst });
	}
	if (cfg.find(dst) == cfg.end()) {
		cfg[dst] = { };
	}
}

void StreamIoDetector::_detectIoAccessGraphs(const HlsReadOrWrite *predecessor,
		size_t predEndOffset, const llvm::BasicBlock &block,
		std::set<
				std::tuple<const HlsReadOrWrite*, size_t,
						const llvm::BasicBlock*>> &seenBlocks,
		std::set<std::pair<size_t, const llvm::BasicBlock*>> &seenBlockOffsets) {
	bool wasAlreadySeen = seenBlocks.find(
			{ predecessor, predEndOffset, &block }) != seenBlocks.end();
	if (wasAlreadySeen) {
		// this block was already seen exactly with same predecessor and offset and was already processed
		return;
	} else {
		seenBlocks.insert( { predecessor, predEndOffset, &block });
	}
	// check if this block was already seen with this offset to resolve if we should search further
	// or end on first IO
	bool offsetWasAlreadySeen = seenBlockOffsets.find(
			{ predEndOffset, &block }) != seenBlockOffsets.end();
	if (!offsetWasAlreadySeen) {
		seenBlockOffsets.insert( { predEndOffset, &block });
	}

	for (const llvm::Instruction &_instr : block) {
		const llvm::CallInst *instr = dyn_cast<const llvm::CallInst>(&_instr);
		if (instr && allStms.count(instr) != 0) {
			if (cfg.find(instr) != cfg.end() && cfg[predecessor].count( {
					predEndOffset, instr }) != 0) {
				// already seen with this offset and already resolved
				return;
			}
			_addTransition(predecessor, predEndOffset, instr);
			if (offsetWasAlreadySeen) {
				// if wasAlreadySeen we just added the transition to a first io in the block and do not follow others
				// because the block was already analyzed with this offset
				return;
			}
			if (IsStreamIoEndOfFrame(instr)) {
				predecessor = nullptr;
				predEndOffset = 0;
			} else {
				predecessor = instr;
				size_t w;
				if (IsStreamIoStartOfFrame(instr)) {
					w = 0;
				} else {
					w = streamIoGetOrigChunkBitWidth(instr);
				}
				predEndOffset = (predEndOffset + w) % DATA_WIDTH;
			}
		}
	}
	for (auto suc : llvm::successors(&block)) {
		_detectIoAccessGraphs(predecessor, predEndOffset, *suc, seenBlocks,
				seenBlockOffsets);
	}
}

void StreamIoDetector::detectIoAccessGraphs(
		const llvm::BasicBlock &startBlock) {
	std::set<std::tuple<const HlsReadOrWrite*, size_t, const llvm::BasicBlock*>> seenBlocks;
	std::set<std::pair<size_t, const llvm::BasicBlock*>> seenBlockOffsets;
	_detectIoAccessGraphs(nullptr, 0, startBlock, seenBlocks, seenBlockOffsets);
}
void StreamIoDetector::resolvePossibleOffset() {
	inWordOffset[nullptr] = { };
	inWordOffset[nullptr].push_back(0);
	predecessors[nullptr] = { };
	for (auto *stm : allStms) {
		inWordOffset[stm] = { };
		predecessors[stm] = { };
	}

	auto resolveSuccessors = [this](const HlsReadOrWrite *pred) {
		auto &successors = cfg[pred];
		for (auto &suc : successors) {
			inWordOffset[suc.second].push_back(suc.first);
			predecessors[suc.second].insert(pred);
		}
	};
	for (auto pred : allStms) {
		resolveSuccessors(pred);
	}
	resolveSuccessors(nullptr);

	for (auto &item : inWordOffset) {
		auto &offsets = item.second;
		// sort and make unique
		std::sort(offsets.begin(), offsets.end());
		offsets.erase(std::unique(offsets.begin(), offsets.end()),
				offsets.end());
	}
}

llvm::raw_ostream& StreamIoDetector::print(llvm::raw_ostream &OS) const {
	OS << "<StreamIoDetector \n";
	for (const auto *io : allStms) {
		OS << *io << "     off: [";
		const auto &offsets = inWordOffset.find(io)->second;
		bool first = true;
		for (auto o : offsets) {
			if (first) {
				first = false;
			} else {
				OS << ", ";
			}
			OS << o;
		}
		OS << "] meta:";
		const auto meta = ioInstrMeta.find(io);
		if (meta == ioInstrMeta.end()) {
			OS << "none";
		} else {
			OS << *meta->second;
		}
		OS << "\n        predecs:";
		for (const auto pred : predecessors.find(io)->second) {
			OS << "        ";
			if (pred)
				OS << *pred;
			else
				OS << "nullptr";
			OS << "\n";
		}
	}
	OS << ">";
	return OS;
}
//const llvm::BasicBlock* StreamIoDetector::findStartBlock() {
//	return _findStartBlock(cfg[nullptr]);
//}
//const llvm::BasicBlock* StreamIoDetector::_findStartBlock(
//		const llvm::SetVector<std::pair<size_t, const HlsReadOrWrite*>> &firstInstrs) {
//	std::vector<const llvm::BasicBlock*> startBlocks;
//	for (const auto &I : firstInstrs) {
//		if (std::find(startBlocks.begin(), startBlocks.end(), I.second->getParent()) == startBlocks.end())
//			startBlocks.push_back(I.second->getParent());
//	}
//	if (startBlocks.size() == 1) {
//		return startBlocks[0];
//	} else {
//		return _findCommonPredecessorOfBlocks(startBlocks);
//	}
//}
//void StreamIoDetector::_collectAllPredecessors(const llvm::BasicBlock &BB,
//		std::set<const llvm::BasicBlock*> &seen) {
//	for (const auto &pred : llvm::predecessors(&BB)) {
//		if (seen.find(pred) == seen.end()) {
//			seen.insert(pred);
//			_collectAllPredecessors(*pred, seen);
//		}
//	}
//}
//const llvm::BasicBlock* StreamIoDetector::_findCommonPredecessorOfBlocks(
//		const std::vector<const llvm::BasicBlock*> &blocks) {
//	if (blocks.size() == 1)
//		return blocks[0];
//
//	// find common predecessor
//	std::set<const llvm::BasicBlock*> preds;
//	for (const auto b : blocks) {
//		std::set<const llvm::BasicBlock*> _preds;
//		_preds.insert(b);
//		_collectAllPredecessors(*b, _preds);
//		preds.insert(_preds.begin(), _preds.end());
//		if (!preds.size())
//			throw std::runtime_error("Must have some common predecessor");
//	}
//	// select the predecessors which does not have any predecessor as successor
//	llvm::SmallVector<const llvm::BasicBlock*> _preds;
//	for (const auto &p : preds) {
//		std::set<const llvm::BasicBlock*> sucs;
//		for (const auto &_suc : llvm::predecessors(p)) {
//			if (preds.find(_suc) == preds.end()) {
//				sucs.insert(_suc);
//			}
//		}
//		if (sucs.size() == 0) {
//			_preds.push_back(p);
//		} else if (sucs.size() == 1) {
//			if (*sucs.begin() == p)
//				_preds.push_back(p);
//		}
//	}
//	if (_preds.size() > 1) {
//		throw std::runtime_error("Multiple undistinguishable predecessors"); // _preds
//	} else if (_preds.size() == 0) {
//		throw std::runtime_error("No common predecessor for blocks"); //  [b.label for b in blocks]
//	} else {
//		return *preds.begin();
//	}
//}

}
