#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteEoFHoister.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

#include <llvm/IR/Dominators.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Transforms/Utils/CodeMoverUtils.h>

using namespace llvm;

namespace hwtHls {

StreamWriteEoFHoister::StreamWriteEoFHoister(
		const StreamChannelProps &streamProps, StreamIoDetector &cfg,
		llvm::DominatorTree &DT, const llvm::PostDominatorTree &PDT,
		llvm::LoopInfo &LI, llvm::DependenceInfo &DI) :
		streamProps(streamProps), cfg(cfg), DT(DT), PDT(PDT), LI(LI), DI(DI) {
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
	} else if (isa<UnreachableInst>(curBlock.getTerminator())) {
		return nullptr;
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
		auto *Term = curBlock.getTerminator();

		if (auto *BR = dyn_cast<llvm::BranchInst>(Term)) {
			auto *TBB = BR->getSuccessor(0);
			auto *T = _tryToGetConditionToEnableEoFProbe(*TBB, TBB->begin());
			if (BR->isConditional()) {
				auto *FBB = BR->getSuccessor(1);
				auto *F = _tryToGetConditionToEnableEoFProbe(*FBB,
						FBB->begin());
				info->mayBeEof = (T && T->mayBeEof) | (F && F->mayBeEof);
				info->mayBeNotEof = (T && T->mayBeNotEof)
						| (F && F->mayBeNotEof);
				assert(
						(info->mayBeEof | info->mayBeNotEof)
								&& "must be followed by another IO because we started the search from not EoF");

			} else {
				info->mayBeEof = (T && T->mayBeEof);
				info->mayBeNotEof = (T && T->mayBeNotEof);
			}
		} else if (auto *Sw = dyn_cast<llvm::SwitchInst>(Term)) {
			for (auto &Case : Sw->cases()) {
				auto *SucBB = _tryToGetConditionToEnableEoFProbe(
						*Case.getCaseSuccessor(),
						Case.getCaseSuccessor()->begin());
				info->mayBeEof |= (SucBB && SucBB->mayBeEof);
				info->mayBeNotEof |= (SucBB && SucBB->mayBeNotEof);
			}
			assert(
					(info->mayBeEof | info->mayBeNotEof)
							&& "must be followed by another IO because we started the search from not EoF");

		} else {
			throw std::runtime_error(
					std::string("NotImplemented: ") + __func__
							+ ": block ending with unknown terminator "
							+ Term->getOpcodeName(Term->getOpcode()));
		}
	}
	errs() << "_tryToGetConditionToEnableEoFProbe: " << curBlock.getName()
			<< "  " << info->mayBeEof << " " << info->mayBeNotEof << "\n";
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
// Try to hoist V in a position which dominates MovePos so the V is always available on MovePos
bool StreamWriteEoFHoister::_hoistRecursivelyIfPossible(Instruction *V,
		Instruction *MovePos) {
	if (DT.dominates(V, MovePos))
		return true; // no hoisting required because V already dominates MovePos

	if (!DT.dominates(MovePos, V)) {
		// in the case that this is not just a simple hoist in linear sequence of blocks pick common dominator
		MovePos = DT.findNearestCommonDominator(V, MovePos);
		assert(
				MovePos->isTerminator()
						&& "Expected terminator of dominator block");
	}

	if (llvm::isSafeToMoveBefore(*V, *MovePos, DT, &PDT, &DI, /*CheckForEntireBlock*/
	true)) {
		V->moveBefore(MovePos);
		return true;
	} else {
		for (auto dep : V->operand_values()) {
			if (auto DepI = dyn_cast<Instruction>(dep)) {
				if (!_hoistRecursivelyIfPossible(DepI, MovePos)) {
					return false;
				}
			}
		}
		if (llvm::isSafeToSpeculativelyExecute(V, nullptr, nullptr, &DT)) {
			V->moveBefore(MovePos);
			return true;
		}
	}
	if (llvm::isSafeToMoveBefore(*V, *MovePos, DT, &PDT, &DI, /*CheckForEntireBlock*/
	true)) {
		V->moveBefore(MovePos);
		return true;
	}
	return false;
}

bool eofIsKnown(const std::pair<llvm::Value*, std::optional<bool>> &EofTuple) {
	if (!EofTuple.first && !EofTuple.second.has_value()) {
		return false;
	}
	return true;
}

// :attention: this works only if other write/eof is not outside of current loop
//   because we do not know yet:
//    * if this is a last iteration
//    * other iteration are going to execute this write again
std::pair<llvm::Value*, std::optional<bool>> StreamWriteEoFHoister::_prepareEoFCondition(
		llvm::IRBuilder<> &Builder, Instruction *MovePos,
		llvm::BasicBlock *curBlock, bool fromBlockBeginning) {
	StreamEoFReachInfo *Info =
			AllInfos[ { curBlock, fromBlockBeginning }].get();
	errs() << "_prepareEoFCondition: " << curBlock->getName()
			<< " fromBlockBeginning " << Info->mayBeEof << " "
			<< Info->mayBeNotEof << "\n";
	assert(Info != nullptr);

	if (Info->mayBeEof && Info->mayBeNotEof) {
		bool isLoopLatch = false;
		for (auto *Suc : successors(curBlock)) {
			auto LSuc = LI.getLoopFor(Suc);
			if (LSuc->contains(curBlock)) {
				isLoopLatch = true;
				break;
			}
		}
		if (isLoopLatch) {
			// if this is a loop latch the EoF condition can not be hoisted
			// because for next iteration we do not know which path in CFG will be taken
			return {nullptr, {}};
		}

		auto ToVal = [&Builder](std::pair<llvm::Value*, std::optional<bool>> &v) {
			if (v.first != nullptr) {
				return v.first;
			} else {
				return (llvm::Value*) ConstantInt::getBool(Builder.getContext(),
						v.second.value());
			}
		};
		auto *Term = curBlock->getTerminator();
		if (auto *BR = dyn_cast<llvm::BranchInst>(Term)) {
			if (BR->isConditional()) {
				auto *BrCond = dyn_cast<Instruction>(BR->getCondition());
				assert(
						BrCond
								&& "If it is not instruction this branch should be already optimized-out");
				auto *TBB = BR->getSuccessor(0);
				auto *FBB = BR->getSuccessor(1);

				if (!_hoistRecursivelyIfPossible(BrCond, MovePos)) {
					std::string tmp;
					llvm::raw_string_ostream ss(tmp);
					ss
							<< "NotImplemented: can not move condition for EOF before potentially last write (BranchInst condition) ";
					BrCond->print(ss);
					ss << " before ";
					MovePos->print(ss);
					throw std::runtime_error(ss.str());
				}
				auto TLastExpr = _prepareEoFCondition(Builder, MovePos, TBB,
						true);
				auto FLastExpr = _prepareEoFCondition(Builder, MovePos, FBB,
						true);
				if (TLastExpr.first == nullptr && FLastExpr.first == nullptr) {
					// simplified case where each successor have only one possibility of EoF/non-EoF
					if (!TLastExpr.second.has_value()
							|| FLastExpr.second.has_value()) {
						return {nullptr, {}};
					} else if (TLastExpr.second.value()
							&& !FLastExpr.second.value()) {
						return {BrCond, false};
					} else {
						assert(
								!TLastExpr.second.value()
										&& FLastExpr.second.value()
										&& "Because this block may end up in EoF or non-EoF booth variants must be in successors");
						return {Builder.CreateNot(BrCond), false};
					}
				} else {
					if (!eofIsKnown(TLastExpr) || !eofIsKnown(FLastExpr)) {
						return {nullptr, {}};
					}
					// create a SelectInst to select between EoF condition variants
					Value *TCaseVal = ToVal(TLastExpr);
					Value *FCaseVal = ToVal(FLastExpr);
					return {Builder.CreateSelect(BrCond, TCaseVal, FCaseVal), false};
				}
			} else {
				return _prepareEoFCondition(Builder, MovePos,
						BR->getSuccessor(0), true);
			}
		} else if (auto Sw = dyn_cast<llvm::SwitchInst>(Term)) {
			auto *Cond = dyn_cast<Instruction>(Sw->getCondition());
			assert(
					Cond
							&& "If it is not instruction this branch should be already optimized-out");
			if (!_hoistRecursivelyIfPossible(Cond, MovePos)) {
				throw std::runtime_error(
						"NotImplemented: can not move condition for EOF before potentially last write (SwitchInst condition)");
			}
			auto *DefBB = Sw->getDefaultDest();
			assert(DefBB);
			auto CondIsEofTuple = _prepareEoFCondition(Builder, MovePos, DefBB,
					true);
			if (!eofIsKnown(CondIsEofTuple) || !eofIsKnown(CondIsEofTuple)) {
				return {nullptr, {}};
			}
			Value *IsEoF = ToVal(CondIsEofTuple);
			for (auto &Case : Sw->cases()) {
				auto *SucBB = Case.getCaseSuccessor();
				auto *CV = Case.getCaseValue();
				auto SucLastExpr = _prepareEoFCondition(Builder, MovePos, SucBB,
						true);
				if (!eofIsKnown(SucLastExpr) || !eofIsKnown(SucLastExpr)) {
					return {nullptr, {}};
				}
				auto *IsEoFFromSuc = ToVal(SucLastExpr);
				IsEoF = Builder.CreateSelect(Builder.CreateICmpEQ(Cond, CV),
						IsEoFFromSuc, IsEoF);
			}
			return {IsEoF, false};

		} else {
			throw std::runtime_error(
					std::string("NotImplemented: ") + __func__
							+ ": block ending with unknown terminator "
							+ Term->getOpcodeName(Term->getOpcode()));
		}
	} else {
		assert(
				(Info->mayBeEof | Info->mayBeNotEof)
						&& "must be followed by another IO because we started the search from not EoF");
		return {nullptr, Info->mayBeEof}; // check is useless because  there is only one possibility
	}
}

//llvm::Value* StreamWriteEoFHoister::_tryToGetConditionToEnableEoF(
//		/*Union[HlsStmWriteStartOfFrame, HlsStmWriteAxi4Stream]*/const StreamIoDetector::HlsReadOrWrite *curWrite) {
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
			if (isLastExpr && !isLastExpr->hasName()) {
				isLastExpr->setName(streamProps.ioArg->getName() + ".eof");
			}
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
