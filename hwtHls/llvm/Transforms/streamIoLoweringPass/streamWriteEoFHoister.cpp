#include "streamWriteEoFHoister.h"
#include "../../targets/intrinsic/streamIo.h"
#include <llvm/Transforms/Utils/CodeMoverUtils.h>

using namespace llvm;

namespace hwtHls {

StreamWriteEoFHoister::StreamWriteEoFHoister(
		const StreamChannelProps &streamProps, StreamIoDetector &cfg,
		llvm::DominatorTree &DT, const llvm::PostDominatorTree &PDT,
		llvm::DependenceInfo &DI) :
		streamProps(streamProps), cfg(cfg), DT(DT), PDT(PDT), DI(DI) {
}

//std::optional<bool> StreamWriteEoFHoister::_isLastWrite(
//		const StreamIoDetector::HlsReadOrWrite *instr) {
//	bool allAreEoFs = true;
//	bool allAreNotEoFs = true;
//	for (auto &_predSucc : cfg.cfg[instr]) {
//		const StreamIoDetector::HlsReadOrWrite *predSucc = _predSucc.second;
//		bool isEoF = IsStreamWriteEndOfFrame(predSucc);
//		allAreEoFs &= isEoF;
//		allAreNotEoFs &= !isEoF;
//	}
//	if (!allAreEoFs && !allAreNotEoFs) {
//		return {};
//	} else if (allAreEoFs) {
//		return false;
//	} else {
//		assert(allAreNotEoFs);
//		return false;
//	}
//}

StreamWriteEoFHoister::StreamEoFReachInfo* StreamWriteEoFHoister::_tryToGetConditionToEnableEoFProbe(
		llvm::BasicBlock &curBlock, llvm::BasicBlock::iterator blockIt) {
	bool isSeachFromBegin = blockIt == curBlock.begin();
	auto cur = AllInfos.find( { &curBlock, isSeachFromBegin });
	StreamEoFReachInfo *info = nullptr;
	if (cur != AllInfos.end()) {
		return cur->second.get();
	} else {
		auto tmp = std::make_unique<StreamEoFReachInfo>();
		info = tmp.get();
		AllInfos[ { &curBlock, isSeachFromBegin }] = std::move(tmp);
	}

	// search for next IO it may exits and it may be EoF or another write
	for (auto I = blockIt; I != curBlock.end(); ++I) {
		if (auto *CI = dyn_cast<CallInst>(&*I)) {
			if (streamProps.ios.count(CI)) {
				if (IsStreamWrite(CI)) {
					info->mayBeNotEof = true;
					break;
				} else if (IsStreamWriteEndOfFrame(CI)) {
					info->mayBeEof = true;
					break;
				} else {
					throw std::runtime_error(
							(streamProps.ioArg->getName()
									+ ": read must never have StartOfFrame as a successor,"
											" because there must be EndOfFrame first").str());
				}
			}
		}
	}
	if (info->mayBeEof || info->mayBeNotEof) {
		// search recursion ends because some other IO was found and we do not need to probe successor blocks
	} else {
		// continue search in successor blocks until some other IO is found
		auto *T = curBlock.getTerminator();
		if (auto *BR = dyn_cast<llvm::BranchInst>(T)) {
			auto *TBB = BR->getSuccessor(0);
			auto *T = _tryToGetConditionToEnableEoFProbe(*TBB, TBB->begin());
			if (BR->isConditional()) {
				auto *FBB = BR->getSuccessor(1);
				auto *F = _tryToGetConditionToEnableEoFProbe(*FBB,
						FBB->begin());
				info->mayBeEof = T->mayBeEof | F->mayBeEof;
				info->mayBeNotEof = T->mayBeNotEof | F->mayBeNotEof;
				assert(
						(info->mayBeEof | info->mayBeNotEof)
								&& "must be followed by another IO because we started the search from not EoF");
				info->brCond = dyn_cast<Instruction>(BR->getCondition());
				assert(info->brCond);
			} else {
				info->mayBeEof = T->mayBeEof;
				info->mayBeNotEof = T->mayBeNotEof;
			}
		} else {
			throw std::runtime_error(
					std::string("NotImplemented: ") + __func__
							+ ": block ending with unknown terminator");
		}
	}

	return info;
}

std::pair<llvm::Value*, std::optional<bool>> StreamWriteEoFHoister::prepareEoFCondition(
		llvm::IRBuilder<> &Builder, Instruction *Write,
		llvm::BasicBlock *curBlock) {
	assert(AllInfos.size() == 0);
	_tryToGetConditionToEnableEoFProbe(*curBlock,
			++BasicBlock::iterator(Write));
	auto res = _prepareEoFCondition(Builder, Write, curBlock, false);
	AllInfos.clear();
	std::optional<bool> isLast;
	if (res.first == nullptr) {
		isLast = res.second;
	}
	return {res.first, isLast};

}
std::pair<llvm::Value*, bool> StreamWriteEoFHoister::_prepareEoFCondition(
		llvm::IRBuilder<> &Builder, Instruction *MovePos,
		llvm::BasicBlock *curBlock, bool fromBlockBeginning) {
	StreamEoFReachInfo *Info =
			AllInfos[ { curBlock, fromBlockBeginning }].get();
	assert(Info != nullptr);
	if (Info->mayBeEof && Info->mayBeNotEof) {
		auto *TER = curBlock->getTerminator();
		auto *BR = dyn_cast<llvm::BranchInst>(TER);
		if (Info->brCond) {
			assert(BR->isConditional());
			auto *TBB = BR->getSuccessor(0);
			auto *FBB = BR->getSuccessor(1);
			//StreamEoFReachInfo *T = AllInfos[ { TBB, true }].get();
			//StreamEoFReachInfo *F = AllInfos[ { FBB, true }].get();
			if (llvm::isSafeToMoveBefore(*Info->brCond, *MovePos, DT, &PDT, &DI, /*CheckForEntireBlock*/
			true)) {
				Info->brCond->moveBefore(MovePos);
			} else {
				throw std::runtime_error(
						"NotImplemented: can not move condition for EOF before potentially last write");
			}
			auto TLastExpr = _prepareEoFCondition(Builder, MovePos, TBB, true);
			auto FLastExpr = _prepareEoFCondition(Builder, MovePos, FBB, true);
			if (TLastExpr.first == nullptr && FLastExpr.first == nullptr) {
				// simplified case where each successor have only one possibility of EoF/non-EoF
				if (TLastExpr.second && !FLastExpr.second) {
					return {Info->brCond, false};
				} else {
					assert(
							!TLastExpr.second && FLastExpr.second
									&& "Because this block may end up in EoF or non-EoF booth variants must be in successors");
					return {Builder.CreateNot(Info->brCond), false};
				}
			} else {
				// create a SelectInst to select between EoF condition variants
				auto ToVal = [&Builder](std::pair<llvm::Value*, bool> &v) {
					if (v.first != nullptr) {
						return v.first;
					} else {
						return (llvm::Value*) ConstantInt::getBool(
								Builder.getContext(), v.second);
					}
				};
				Value *TCaseVal = ToVal(TLastExpr);
				Value *FCaseVal = ToVal(FLastExpr);
				return {Builder.CreateSelect(Info->brCond, TCaseVal, FCaseVal), false};
			}
		} else {
			return _prepareEoFCondition(Builder, MovePos, BR->getSuccessor(0),
					true);
		}
	} else {
		assert(
				(Info->mayBeEof | Info->mayBeNotEof)
						&& "must be followed by another IO because we started the search from not EoF");
		return {nullptr, Info->mayBeEof}; // check is useless because  there is only one possibility
	}
}

//llvm::Value* StreamWriteEoFHoister::_tryToGetConditionToEnableEoF(
//		/*Union[HlsStmWriteStartOfFrame, HlsStmWriteAxiStream]*/const StreamIoDetector::HlsReadOrWrite *curWrite) {
//	//auto *curBlock = curWrite->getParent();
//	//std::set<const BasicBlock*> successorsWithEoF;
//	//for (BasicBlock *suc : llvm::successors(curBlock)) {
//	//	// allow for linear sequences of blocks
//	//	auto _suc = suc;
//	//	bool eofFound = false;
//	//	for (;;) {
//	//		for (Instruction *_instr : *_suc) {
//	//			if (CallInst *instr = dyn_cast<CallInst>(_instr)) {
//	//				if (cfg.allStms.count(instr) != cfg.allStms.end()) {
//	//					if (IsStreamWriteEndOfFrame(instr)) {
//	//						eofFound = true;
//	//					}
//	//					break;
//	//				}
//	//			}
//	//		}
//	//		if (eofFound) {
//	//			break;
//	//		} else {
//	//			auto *br = dyn_cast<BranchInst>(_suc->getTerminator());
//	//			if (br->isUnconditional()) {
//	//				// follow linear sequence of blocks
//	//				_suc = br->getSuccessor(0);
//	//			} else {
//	//				// there is some branching, we do not follow it because the hoisting of code
//	//				// on such branches is not implemented on this level yet
//	//				break;
//	//			}
//	//		}
//	//	}
//	//	if (eofFound)
//	//		successorsWithEoF.insert(suc);
//	//}
//	//if (!successorsWithEoF)
//	//	return nullptr;
//
//	//std::set<llvm::Value*> importantConditions;
//	//bool firstEoFTargetSeen = false;
//	//for cond, suc, _ in reversed(curBlock.successors.targets):
//	//    if firstEoFTargetSeen:
//	//        importantConditions.add(cond)
//	//    elif suc in successorsWithEoF:
//	//        firstEoFTargetSeen = True
//	//        if cond is not None:
//	//            importantConditions.add(cond)
//	//
//	//hoistSuccess, writePosition = ssaTryHoistBeforeInSameBlock(curWrite, importantConditions);
//	//if (hoistSuccess) {
//	//	// build the condition from parts
//	//	builder.setInsertPoint(curWrite);
//	//	isLastCond, _ = _resolveBranchGroupCondition(ssaBuilder,
//	//			iter(curBlock.successors.targets), successorsWithEoF)
//	//	assert( isLastCond != nullptr);
//	//	return isLastCond;
//	//} else {
//	//	return nullptr;
//	//}
//}

void StreamWriteEoFHoister::prepareLastExpressionForWrites() {
	llvm::SmallVector<const StreamIoDetector::HlsReadOrWrite*> eofs;
	auto &instrMeta = cfg.ioInstrMeta;
	// collect EoFs and construct meta for write instructions
	for (auto *write : streamProps.ios) {
		if (IsStreamWrite(write)) {
			std::optional<bool> isLast; // = _isLastWrite(write);
			llvm::Value *isLastExpr;
			IRBuilder<> Builder(write);
			std::tie(isLastExpr, isLast) = prepareEoFCondition(Builder, write,
					write->getParent());
			auto meta = std::make_unique<StreamChunkLastMeta>(isLast,
					isLastExpr);
			instrMeta[write] = std::move(meta);
		} else if (IsStreamWriteEndOfFrame(write)) {
			eofs.push_back(write);
		}
	}
	// create meta of EoFs and resolve if this was inlined into predecessors
	for (auto *eof : eofs) {
		bool inlinedToPredecessors = true; // is inlined to predecessor if every predecessor knows if it is last or not somehow.
		for (const StreamIoDetector::HlsReadOrWrite *pred : cfg.predecessors[eof]) {
			auto predMeta = instrMeta.find(pred);
			if (predMeta == instrMeta.end()) {
				inlinedToPredecessors = false;
				break;
			} else {
				auto &_predMeta =
						*dynamic_cast<StreamChunkLastMeta*>(predMeta->second.get());
				if (!_predMeta.isLast.has_value()
						&& _predMeta.isLastExpr == nullptr) {
					inlinedToPredecessors = false;
					break;
				}
			}
		}
		auto meta = std::make_unique<StreamEoFMeta>(inlinedToPredecessors);
		instrMeta[eof] = std::move(meta);
	}

	// for each write resolve if it needs to take previous write data in account or this write is begin of a new bus word
	for (auto *write : cfg.allStms) {
		if (IsStreamWrite(write)) {
			auto meta =
					dynamic_cast<StreamChunkLastMeta*>(instrMeta[write].get());
			assert(meta);
			bool prevWordMayBePending = false;
			for (const StreamIoDetector::HlsReadOrWrite *pred : cfg.predecessors[write]) {
				auto predMeta = instrMeta.find(pred);
				if (predMeta != instrMeta.end()) {
					auto &_predMeta =
							*dynamic_cast<StreamChunkLastMeta*>(predMeta->second.get());
					if (!_predMeta.isLast.has_value()
							&& _predMeta.isLastExpr == nullptr)
						prevWordMayBePending = true;
					break;
				}
			}
			meta->prevWordMayBePending = prevWordMayBePending;
		}
	}
}

}
