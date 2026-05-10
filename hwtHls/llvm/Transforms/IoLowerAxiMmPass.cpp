#include <hwtHls/llvm/Transforms/IoLowerAxiMMPass.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Metadata.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopAnalysisManager.h>

#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

using namespace llvm;

namespace hwtHls {

const char* MemoryOrdering_toString(MemoryOrdering mo) {
	switch (mo) {
	case MemoryOrdering::MEMORDERING_NONE:
		return "MEMORDERING_NONE";
	case MemoryOrdering::MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM:
		return "MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM";
	default:
		llvm_unreachable("Invalid value for MemoryOrdering");
	}
}

MemoryOrdering MemoryOrdering_fromString(const std::string &mo) {
	if (mo == "MEMORDERING_NONE") {
		return MemoryOrdering::MEMORDERING_NONE;
	} else if (mo == "MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM") {
		return MemoryOrdering::MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM;
	} else {
		llvm_unreachable("Invalid value for MemoryOrdering");
	}
}
size_t MetadataIoAxiMM::getWordWidth() const {
	return std::max(wDefault.getBitWidth(), rDefault.getBitWidth());
}
const std::string MetadataIoAxiMM::metadataName_ioAxiMM = "IoAxiMM";

llvm::MDTuple* MetadataIoAxiMM::toMetadata(llvm::LLVMContext &context) {
	SmallVector<Metadata*, 32> metadataValues;
	metadataValues.push_back(MDString::get(context, metadataName_ioAxiMM));

	auto pushApInt = [&metadataValues, &context](const APInt &i) {
		metadataValues.push_back(
				ConstantAsMetadata::get(ConstantInt::get(context, i)));
	};
	pushApInt(arDefault);
	pushApInt(rDefault);
	pushApInt(awDefault);
	pushApInt(wDefault);
	pushApInt(bDefault);

	Type *u64 = IntegerType::get(context, 64);
	auto pushSizePair = [&metadataValues, u64](
			const std::pair<size_t, size_t> &i) {
		metadataValues.push_back(
				ConstantAsMetadata::get(ConstantInt::get(u64, i.first)));
		metadataValues.push_back(
				ConstantAsMetadata::get(ConstantInt::get(u64, i.second)));
	};
	pushSizePair(aId);
	pushSizePair(bId);
	pushSizePair(rId);
	pushSizePair(wId);
	pushSizePair(addr);
	pushSizePair(len);
	pushSizePair(rData);
	pushSizePair(wData);

	Type *u32 = IntegerType::get(context, 32);
	auto pushUnsigned = [&metadataValues, u32](unsigned i) {
		metadataValues.push_back(
				ConstantAsMetadata::get(ConstantInt::get(u32, i)));
	};
	pushUnsigned(dataWidth);
	pushUnsigned(latencyArToR);
	pushUnsigned(latencyAwToW);
	pushUnsigned(latencyWToB);
	pushUnsigned(latencyBToR);
	auto pushStr = [&metadataValues, &context](const std::string &str) {
		metadataValues.push_back(MDString::get(context, str));
	};
	pushStr(MemoryOrdering_toString(memOrdering));
	return MDTuple::getDistinct(context, metadataValues);
}

MetadataIoAxiMM MetadataIoAxiMM::fromMetadata(const llvm::MDTuple &mdTuple) {
	MetadataIoAxiMM metadata;

	auto getAPInt = [&mdTuple](size_t opI) -> APInt {
		Metadata *md = mdTuple.getOperand(opI);
		auto *_ci = dyn_cast<ConstantAsMetadata>(md);
		assert(_ci);
		auto ci = dyn_cast<ConstantInt>(_ci->getValue());
		assert(ci);
		return ci->getValue();
	};

	size_t i = 0;
	assert(mdTuple.getOperand(i++).equalsStr(metadataName_ioAxiMM));
	metadata.arDefault = getAPInt(i++);
	metadata.rDefault = getAPInt(i++);
	metadata.awDefault = getAPInt(i++);
	metadata.wDefault = getAPInt(i++);
	metadata.bDefault = getAPInt(i++);

	auto getSizePair = [&getAPInt](size_t opI0,
			size_t opI1) -> std::pair<size_t, size_t> {
		auto v0 = getAPInt(opI0).getZExtValue();
		auto v1 = getAPInt(opI1).getZExtValue();
		return {v0, v1};
	};

	metadata.aId = getSizePair(i, i + 1);
	i += 2;
	metadata.bId = getSizePair(i, i + 1);
	i += 2;
	metadata.rId = getSizePair(i, i + 1);
	i += 2;
	metadata.wId = getSizePair(i, i + 1);
	i += 2;
	metadata.addr = getSizePair(i, i + 1);
	i += 2;
	metadata.len = getSizePair(i, i + 1);
	i += 2;
	metadata.rData = getSizePair(i, i + 1);
	i += 2;
	metadata.wData = getSizePair(i, i + 1);
	i += 2;

	auto getUnsigned = [&getAPInt](size_t opI) -> unsigned {
		return getAPInt(opI).getZExtValue();
	};

	metadata.dataWidth = getUnsigned(i++);
	metadata.latencyArToR = getUnsigned(i++);
	metadata.latencyAwToW = getUnsigned(i++);
	metadata.latencyWToB = getUnsigned(i++);
	metadata.latencyBToR = getUnsigned(i++);
	Metadata *md = mdTuple.getOperand(i++);
	auto *_mdStr = dyn_cast<MDString>(md);
	metadata.memOrdering = MemoryOrdering_fromString(_mdStr->getString().str());

	return metadata;
}

void findAllLoadsAndStoresAssociatedWithPtr(llvm::Value &V,
		SetVector<LoadInst*> &loads, SetVector<StoreInst*> &stores) {
	assert(V.getType()->isPointerTy());
	for (auto *U : V.users()) {
		if (auto L = dyn_cast<LoadInst>(U)) {
			loads.insert(L);
		} else if (auto S = dyn_cast<StoreInst>(U)) {
			stores.insert(S);
		} else if (auto GEP = dyn_cast<GetElementPtrInst>(U)) {
			findAllLoadsAndStoresAssociatedWithPtr(*GEP, loads, stores);
		} else if (auto CI = dyn_cast<CallInst>(U)) {
			// update all parameter types to new address space by creating of new function prototype
			if (auto II = dyn_cast<IntrinsicInst>(CI)) {
				switch (II->getIntrinsicID()) {
				case Intrinsic::IndependentIntrinsics::lifetime_start:
					continue;
				case Intrinsic::IndependentIntrinsics::lifetime_end:
					continue;
				default:
					llvm_unreachable("Unsupported IntrinsicInst");
				}
			} else {
				llvm_unreachable("Unsupported function");
			}
		} else {
			std::string errStr =
					"NotImplemented: replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace ";
			raw_string_ostream ss(errStr);
			U->print(ss);
			throw std::runtime_error(ss.str());
		}
	}
}

SetVector<BasicBlock*> searchReadModifySection(LoopInfo &LI,
		DomTreeUpdater &DTU, Loop *L, Argument &axiMM,
		const SetVector<LoadInst*> &loads, const SetVector<StoreInst*> &stores,
		const SmallVector<StoreInst*> &storesInCurrentLoop) {
	// :note: this expects only natural loops

	SmallVector<BasicBlock*, 16> toVisit;
	for (auto st : storesInCurrentLoop) {
		toVisit.push_back(st->getParent());
	}
	SetVector<BasicBlock*> selectedBlocks;

	// DFS collect blocks from all StoreInsts to LoadInst (use -> def)
	while (!toVisit.empty()) {
		BasicBlock *BB = toVisit.pop_back_val();
		if (selectedBlocks.count(BB)) {
			continue;
		}

		bool BBContainsLoadFromAxiMMPtr = false;
		bool BBIsLoopHeader = L && L->getHeader() == BB;
		bool blockBeginsWithNonGepOrLoadForAxiMMPtr = false;
		for (auto &Inst : *BB) {
			if (auto *Load = dyn_cast<LoadInst>(&Inst)) {
				if (loads.contains(Load)) {
					BBContainsLoadFromAxiMMPtr = true;
					if (blockBeginsWithNonGepOrLoadForAxiMMPtr) {
						// split block so load is at the beginning
						splitBlockBefore(&*BB, Load, &DTU, &LI, nullptr, "");
						assert(Load->getParent() == BB);
					}
					break;
				} else {
					blockBeginsWithNonGepOrLoadForAxiMMPtr = true;
				}
			} else if (!blockBeginsWithNonGepOrLoadForAxiMMPtr) {
				auto GEP = dyn_cast<GetElementPtrInst>(&Inst);
				blockBeginsWithNonGepOrLoadForAxiMMPtr |= !GEP
						|| GEP->getPointerOperand() != &axiMM;
			}
		}
		selectedBlocks.insert(BB);
		if (BBContainsLoadFromAxiMMPtr)
			continue; // because we search for read-modify-write section the search should stop on load
		if (BBIsLoopHeader)
			continue; // do not cross the parent loop header

		// Add predecessors to the visit stack (DFS)
		for (auto *Pred : predecessors(BB)) {
			toVisit.push_back(Pred);
		}
	}
	return selectedBlocks;
}

bool canReadModifyWriteSectionBeExtractedAsThread(DomTreeUpdater &DTU,
		LoopInfo &LI, const SetVector<BasicBlock*> &selectedBlocks,
		const SmallVector<LoadInst*> &loadsInCurrentLoop,
		const SmallVector<StoreInst*> &storesInCurrentLoop,
		SmallVector<BasicBlock::iterator> &sectionBeginInsertPoints,
		SmallVector<BasicBlock::iterator> &sectionEndInsertPoints) {
	if (loadsInCurrentLoop.size() != 1)
		return false;
	else if (storesInCurrentLoop.empty())
		return false;
	// check if the section can be extracted as a thread
	bool sectionCompatible = true;
	for (auto *selectedBB : selectedBlocks) {
		// search for potential begins of extracted section in this BB
		bool hasPredecessorOutside = false;
		LoadInst *firstLdOfThisBlock = nullptr;
		for (auto *ld : loadsInCurrentLoop) {
			if (ld->getParent() == selectedBB) {
				if (!firstLdOfThisBlock
						|| ld->comesBefore(firstLdOfThisBlock)) {
					firstLdOfThisBlock = ld;
				}
			}
		}
		if (firstLdOfThisBlock) {
			sectionBeginInsertPoints.push_back(firstLdOfThisBlock->getIterator());
		} else {
			for (auto *pred : predecessors(selectedBB)) {
				if (!selectedBlocks.contains(pred)) {
					hasPredecessorOutside = true;
					break;
				}
			}
			if (hasPredecessorOutside) {
				if (selectedBB->hasNPredecessorsOrMore(2)) {
					sectionCompatible = false;
					break;
				}
				sectionBeginInsertPoints.push_back(
						selectedBB->getFirstNonPHIIt());
			}
		}
		// search for potential end of extracted section in this BB
		bool bbHasStore = false;
		for (auto st : storesInCurrentLoop) {
			if (st->getParent() == selectedBB) {
				sectionEndInsertPoints.push_back(st->getNextNode()->getIterator());
				bbHasStore = true;
				break;
			}
		}
		if (!bbHasStore) {
			// search for section end continues
			bool allSuccessorsOutsideOfSection = true;

			for (auto *succ : successors(selectedBB)) {
				if (selectedBlocks.contains(succ)) {
					allSuccessorsOutsideOfSection = false;
				}
			}
			if (allSuccessorsOutsideOfSection) {
				auto TI = selectedBB->getTerminator();
				sectionEndInsertPoints.push_back(TI->getIterator());
			} else {
				for (auto *succ : successors(selectedBB)) {
					if (!selectedBlocks.contains(succ)) {
						if (succ->getSinglePredecessor() != selectedBB) {
							DTU.flush();
							auto opts = CriticalEdgeSplittingOptions(
									&DTU.getDomTree(), &LI, nullptr, nullptr);
							succ = SplitCriticalEdge(selectedBB, succ, opts);
						}
						sectionEndInsertPoints.push_back(
								succ->getFirstNonPHIIt());
					}
				}
			}

		}
	}
	// after all exits of the section were checked it is now known if the section is compatible
	return sectionCompatible;
}

void markReadModifyWriteSectionsAsThread(Function &F, Argument &axiMM,
		const ThreadSplitSectionMetadata &threadMdObj, DomTreeUpdater &DTU,
		LoopInfo &LI, IRBuilder<> &builder, const SetVector<LoadInst*> &loads,
		const SetVector<StoreInst*> &stores) {

	// if this is a read-modify-write pattern separate section beginning with axi.r to axi.b into own thread
	// * load is in the loop, and there is no other access to this io before
	// * load dominates all potential writes in the loop
	// * the extracted section will end after access to axi.b or after the branch to a block which is on CFG path
	//   which contain no other writes

	SetVector<LoadInst*> resolvedLoads;
	SetVector<StoreInst*> resolvedStores;
	for (auto stIt0 = stores.begin(); stIt0 != stores.end(); ++stIt0) {
		if (resolvedStores.contains(*stIt0))
			continue;

		auto L = LI.getLoopFor((*stIt0)->getParent());
		SmallVector<StoreInst*> storesInCurrentLoop;
		SmallVector<LoadInst*> loadsInCurrentLoop;
		storesInCurrentLoop.push_back(*stIt0);
		// find other stores in this loop
		for (auto stIt1 = stIt0 + 1; stIt1 != stores.end(); ++stIt1) {
			if (resolvedStores.contains(*stIt1))
				continue;
			if (LI.getLoopFor((*stIt1)->getParent()) == L) {
				storesInCurrentLoop.push_back(*stIt1);
			}
		}
		for (auto *ld : loads) {
			if (resolvedLoads.contains(ld))
				continue;
			if (LI.getLoopFor(ld->getParent()) == L) {
				loadsInCurrentLoop.push_back(ld);
			}
		}

		SetVector<BasicBlock*> selectedBlocks = searchReadModifySection(LI, DTU,
				L, axiMM, loads, stores, storesInCurrentLoop);
		SmallVector<BasicBlock::iterator> sectionBeginInsertPoints;
		SmallVector<BasicBlock::iterator> sectionEndInsertPoints;
		if (canReadModifyWriteSectionBeExtractedAsThread(DTU, LI,
				selectedBlocks, loadsInCurrentLoop, storesInCurrentLoop,
				sectionBeginInsertPoints, sectionEndInsertPoints)) {
			auto md = threadMdObj.toMetadata(F.getContext());
			for (auto ip : sectionBeginInsertPoints) {
				builder.SetInsertPoint(ip);
				CreateThreadSplitBegin(builder, threadMdObj.name, md);
			}
			for (auto ip : sectionEndInsertPoints) {
				builder.SetInsertPoint(ip);
				CreateThreadSplitEnd(builder, threadMdObj.name, md);
			}

			resolvedLoads.insert(loadsInCurrentLoop.begin(),
					loadsInCurrentLoop.end());
			resolvedStores.insert(storesInCurrentLoop.begin(),
					storesInCurrentLoop.end());
		}
	}
}

/*
 * Mark section from read to end of this block
 * */
void markReadConsummerSection(Function &F, Argument &axiMM,
		const ThreadSplitSectionMetadata &threadMdObj, DomTreeUpdater &DTU,
		LoopInfo &LI, IRBuilder<> &Builder, LoadInst *Ld) {
	auto &BB = *Ld->getParent();
	assert(BB.getUniqueSuccessor() == &BB);

	// :note: lowerAxiMMLoad will create axi.ar store before threadSplitBegin
	auto md = threadMdObj.toMetadata(Builder.getContext());
	Builder.SetInsertPoint(Ld);
	CreateThreadSplitBegin(Builder, threadMdObj.name, md);
	Builder.SetInsertPoint(BB.getTerminator());
	auto sectionEnd = CreateThreadSplitEnd(Builder, threadMdObj.name, md);

	// search section dep->use and collect instructions dependent on Ld
	SmallPtrSet<Instruction*, 32> instructionsDependentOnLd;
	instructionsDependentOnLd.insert(Ld);

	Instruction *lastSideeffectInstr = nullptr;
	for (auto I = Ld->getNextNode()->getIterator();
			I != sectionEnd->getIterator(); I++) {
		if (I->mayHaveSideEffects() || I->isVolatile()) {
			lastSideeffectInstr = &*I;
		}

		for (auto *op : I->operand_values()) {
			if (auto opI = dyn_cast<Instruction>(op)) {
				if (instructionsDependentOnLd.contains(opI)) {
					instructionsDependentOnLd.insert(&*I);
					break;
				}
			}
		}
	}
	auto sinkIP = sectionEnd->getNextNode()->getIterator();
	// sink all instructions irrelevant to Ld out of the section
	for (auto I =
			(lastSideeffectInstr ? lastSideeffectInstr : Ld)->getNextNode()->getIterator();
			I != sectionEnd->getIterator();) {
		assert(!I->mayHaveSideEffects() && !I->isVolatile());
		if (instructionsDependentOnLd.contains(&*I)) {
			I++;
			continue;
		}
		auto _I = I;
		I++;
		_I->moveBefore(sinkIP);
	}

}

MDTuple* MetadataPropertyPath_append(LLVMContext &ctx, MDTuple *cur,
		std::string &toAdd) {
	SmallVector<Metadata*> items;
	if (cur) {
		items.insert(items.end(), cur->op_begin(), cur->op_end());
	}
	auto md = MDString::get(ctx, toAdd);
	items.push_back(md);
	return MDTuple::get(ctx, items);
}

// :note: for parameters meaning see MetadataIoAxiMM doc (tuples are bit offset, width in value for specified channel)
void lowerAxiMMAddrAccess(IRBuilder<> &builder, llvm::APInt &addrDefault,
		std::pair<size_t, size_t> idBitPos,
		std::pair<size_t, size_t> addrBitPos,
		std::pair<size_t, size_t> lenBitPos, size_t dataWidth, Value *axiMMPtr, // current pointer which is used to access axiMM (likely GEP)
		AllocaInst *axiMMAPtr // new tmp pointer used for address channel of axiMM
		) {
	auto gep = dyn_cast<GetElementPtrInst>(axiMMPtr);
	if (!gep) {
		llvm_unreachable(
				"NotImplemented: AXI MM pointer is not GEP, do not know how to extract address");
	}
	if (!isa<Argument>(gep->getPointerOperand())) {
		llvm_unreachable(
				"NotImplemented: AXI MM pointer is GEP but GEP argument is not main axiMM Argument of function, do not know how to extract address");
	}
	auto idx = gep->idx_begin(); // :note: Use iterator of indices
	Value *addr = nullptr;
	auto i0 = dyn_cast<ConstantInt>(idx->get());
	if (!i0 || !i0->isZero())
		llvm_unreachable(
				"NotImplemented: GEP is expected to be in format like: getelementptr inbounds [256 x i66], ptr addrspace(1) %ram, i64 0, i64 %addr, but first index operand is not 0");
	++idx;
	if (idx == gep->idx_end()) {
		llvm_unreachable(
				"NotImplemented: GEP is expected to be in format like: getelementptr inbounds [256 x i66], ptr addrspace(1) %ram, i64 0, i64 %addr, but it has just 1 index");
	}
	if (dataWidth != 8) {
		size_t addrOffsetBits = log2ceil(dataWidth / 8);
		SmallVector<Value*, 3> addrParts;
		addrParts.push_back(builder.getIntN(addrOffsetBits, 0));
		auto idxVal = idx->get();
		auto curIndexWidth = idxVal->getType()->getIntegerBitWidth();
		assert(addrBitPos.second > addrOffsetBits);
		if (curIndexWidth > addrBitPos.second - addrOffsetBits) {
			addrParts.push_back(
					builder.CreateTrunc(idxVal,
							builder.getIntNTy(
									addrBitPos.second - addrOffsetBits)));
		} else {
			addrParts.push_back(idxVal);
			addrParts.push_back(
					builder.getIntN(
							addrBitPos.second - addrOffsetBits - curIndexWidth,
							0));
		}
		addr = CreateBitConcat(&builder, addrParts);

	} else {
		addr = builder.CreateZExtOrTrunc(idx->get(),
				builder.getIntNTy(addrBitPos.second));
	}
	++idx;
	if (idx != gep->idx_end()) {
		llvm_unreachable(
				"NotImplemented: GEP is expected to be in format like: getelementptr inbounds [256 x i66], ptr addrspace(1) %ram, i64 0, i64 %addr, but it has more than 2 indices");
	}
	SmallVector<std::pair<std::pair<size_t, size_t>, Value*>> partsTmp;
	partsTmp.push_back( { idBitPos, nullptr });
	partsTmp.push_back( { addrBitPos, addr });
	partsTmp.push_back( { lenBitPos, nullptr });
	// sort lower bits first
	llvm::sort(partsTmp,
			[](const std::pair<std::pair<size_t, size_t>, Value*> &v0,
					const std::pair<std::pair<size_t, size_t>, Value*> &v1) {
				return v0.first.first < v1.first.first;
			});

	SmallVector<Value*> valueParts;
	size_t nextBegin = 0;
	for (const auto &part : partsTmp) {
		size_t bitOffset, width;
		std::tie(bitOffset, width) = part.first;
		if (!width)
			continue; // skip parts with 0 width
		if (nextBegin != part.first.first) {
			assert(nextBegin < part.first.first);
			// there is some empty space in partsTmp, fill it with value extracted from addrDefault
			auto v = addrDefault.extractBits(width, bitOffset);
			valueParts.push_back(builder.getInt(v));
		}
		assert(part.second && "This member is not optional");
		valueParts.push_back(part.second);
		nextBegin = bitOffset + width;
	}
	if (nextBegin != addrDefault.getBitWidth()) {
		auto v = addrDefault.extractBits(addrDefault.getBitWidth() - nextBegin,
				nextBegin);
		valueParts.push_back(builder.getInt(v));
	}

	auto aStoreValue = CreateBitConcat(&builder, valueParts);
	builder.CreateStore(aStoreValue, axiMMAPtr, /*isVolatile*/true);
}

void lowerAxiMMLoad(IRBuilder<> &Builder, DceWorklist &DCE,
		MetadataIoAxiMM &axiMMIoMd, LoadInst *ld, AllocaInst *axiArTmpAlloca,
		AllocaInst *axiRTmpAlloca) {
	auto predInst = dyn_cast<CallInst>(ld->getPrevNode());
	if (predInst && IsThreadSplitBegin(predInst)) {
		// create ar store before threadSplitBegin so read address request is in original thread
		// (no need to sink as ar will be part of original thread)
		Builder.SetInsertPoint(predInst);
	} else {
		Builder.SetInsertPoint(ld);
	}
	lowerAxiMMAddrAccess(Builder, axiMMIoMd.arDefault, axiMMIoMd.aId,
			axiMMIoMd.addr, axiMMIoMd.len, axiMMIoMd.dataWidth,
			ld->getPointerOperand(), axiArTmpAlloca);
	Builder.SetInsertPoint(ld);
	if (ld->getType()->getIntegerBitWidth() != axiMMIoMd.getWordWidth()) {
		llvm_unreachable(
				"NotImplemented: load from axi MM is expected to be just 1 word");

	}
	// create r load after threadSplitBegin so it is inside of new thread
	// :note: if there is no threadSplitBegin insert everything on place where original LoadInst was
	auto newLd = Builder.CreateLoad(ld->getType(), axiRTmpAlloca, /*isVolatile*/
	true);
	newLd->takeName(ld);
	ld->replaceAllUsesWith(newLd);

	for (Value *op : ld->operand_values()) {
		if (auto opi = dyn_cast<Instruction>(op))
			DCE.insert(*opi);
	}
	ld->eraseFromParent();
}

void lowerAxiMMStore(IRBuilder<> &Builder, DceWorklist &DCE,
		MetadataIoAxiMM &axiMMIoMd, StoreInst *st, AllocaInst *axiAwTmpAlloca,
		AllocaInst *axiWTmpAlloca, AllocaInst *axiBTmpAlloca) {
	// sink or copy GEPs/SExt/ZExt
	// create aw, w store before threadSplitEnd so it is in new extracted thread
	// create b read after threadSplitEnd so it is in original thread
	Builder.SetInsertPoint(st);
	lowerAxiMMAddrAccess(Builder, axiMMIoMd.awDefault, axiMMIoMd.aId,
			axiMMIoMd.addr, axiMMIoMd.len, axiMMIoMd.dataWidth,
			st->getPointerOperand(), axiAwTmpAlloca);
	auto stVal = st->getValueOperand();
	if (stVal->getType()->getIntegerBitWidth() != axiMMIoMd.getWordWidth()) {
		llvm_unreachable(
				"NotImplemented: store to axi MM is expected to be just 1 word");
	}
	Builder.CreateStore(stVal, axiWTmpAlloca, /*isVolatile*/true);
	auto suc = dyn_cast<CallInst>(st->getNextNode());
	if (suc && IsThreadSplitEnd(suc)) {
		// place axi.b load to parent thread
		Builder.SetInsertPoint(suc->getNextNode());
	}
	auto AxiBTy = Builder.getIntNTy(axiMMIoMd.bDefault.getBitWidth());
	auto AxiBLd = Builder.CreateLoad(AxiBTy, axiBTmpAlloca, /*isVolatile*/true);
	if (axiMMIoMd.memOrdering == MemoryOrdering::MEMORDERING_NONE) {
		// put into entirely async thread which will consume axi.b channel inputs
		// so it does not block any other transaction
		ThreadSplitSectionMetadata threadMdObj("axiMM.asynB", true, true, true,
				true, 0, 0);
		auto md = threadMdObj.toMetadata(Builder.getContext());
		Builder.SetInsertPoint(AxiBLd);
		CreateThreadSplitBegin(Builder, threadMdObj.name, md);
		Builder.SetInsertPoint(AxiBLd->getNextNode());
		CreateThreadSplitEnd(Builder, threadMdObj.name, md);
	}
	for (Value *op : st->operand_values()) {
		DCE.insertValue(*op);
	}
	st->eraseFromParent();
}

llvm::PreservedAnalyses IoLowerAxiMMPass::run(llvm::Module &M,
		llvm::ModuleAnalysisManager &AM) {
	auto &FAM =
			AM.getResult<FunctionAnalysisManagerModuleProxy>(M).getManager();
	auto LookupDomTree = [&FAM](Function &F) -> DominatorTree& {
		return FAM.getResult<DominatorTreeAnalysis>(F);
	};
	auto LookupLoopInfo = [&FAM](Function &F) -> LoopInfo& {
		return FAM.getResult<LoopAnalysis>(F);
	};
	bool changed = false;
	IRBuilder<> builder(M.getContext());
	SmallVector<Function*> originalFunctions;
	for (auto &F : M)
		originalFunctions.push_back(&F);
	for (auto *_F : originalFunctions) {
		auto &F = *_F;
		if (F.isDeclaration())
			continue;
		if (!F.hasMetadata(HwtHlsIoMetadata::METADATA_NAME))
			continue;

		auto &DT = LookupDomTree(F);
		auto &LI = LookupLoopInfo(F);
		auto &TLI = FAM.getResult<TargetLibraryAnalysis>(F);
		auto ioMd = HwtHlsIoMetadata_get(F);

		SmallVector<ArgToAddToParentFn> argsToAddToParentFn;
		auto ioArg = F.arg_begin();
		for (auto &ioArgMd : ioMd) {
			assert(ioArg != F.arg_end());
			auto protMd = ioArgMd.ioProtocolMd;
			if (ioArg->hasNUndroppableUsesOrMore(1) && protMd
					&& protMd->getNumOperands() > 1
					&& protMd->getOperand(0).equalsStr(
							MetadataIoAxiMM::metadataName_ioAxiMM)) {
				auto axiMMIoMd = MetadataIoAxiMM::fromMetadata(*protMd);

				// the access to axi io will be dissolved to:
				//  * load: store axi.ar, load from axi.r
				//  * store: store to axi.aw, store to axi.w, load from axi.b
				DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
				SetVector<LoadInst*> loads;
				SetVector<StoreInst*> stores;
				findAllLoadsAndStoresAssociatedWithPtr(*ioArg, loads, stores);
				if (loads.size() == 1 && stores.size() == 1
						&& DT.dominates(loads[0], stores[0])) {
					// this is read-modify-write, extract modify section to separate thread
					ThreadSplitSectionMetadata threadMdObj(
							("axiMM.rmw." + ioArg->getName()).str(), true, true,
							true, true, axiMMIoMd.latencyArToR,
							axiMMIoMd.latencyBToR);
					markReadModifyWriteSectionsAsThread(F, *ioArg, threadMdObj,
							DTU, LI, builder, loads, stores);
				} else if (loads.size() == 1 && stores.size() == 0
						&& loads[0]->getParent()->getUniqueSuccessor()
								== loads[0]->getParent()) {
					// read only in trivial loop, extract data consumer thread
					ThreadSplitSectionMetadata threadMdObj(
							("axiMM.rConsumer." + ioArg->getName()).str(), true,
							true, true, true, axiMMIoMd.latencyArToR, 1);
					markReadConsummerSection(F, *ioArg, threadMdObj, DTU, LI,
							builder, loads[0]);
				} else if (axiMMIoMd.memOrdering
						== MemoryOrdering::MEMORDERING_NONE && loads.size() == 0
						&& stores.size() == 1
						&& stores[0]->getParent()->getUniqueSuccessor()
								== stores[0]->getParent()) {
					// store only in trivial loop, extract axi.b consumer thread
				} else {
					continue; // not an access pattern of the interest
				}
				// create tmp allocas for AXI channels and add them to argsToAddToParentFn so
				// later they are promoted to arguments of this function
				AllocaInst *axiArTmpAlloca = nullptr, *axiRTmpAlloca = nullptr,
						*axiAwTmpAlloca = nullptr, *axiWTmpAlloca = nullptr,
						*axiBTmpAlloca = nullptr;
				builder.SetInsertPoint(F.getEntryBlock().begin());

				auto mkTmpAlloca = [&builder, ioArg, &ioArgMd,
						&argsToAddToParentFn](std::string name,
						IODirection dir, APInt &defVal) {
					size_t w = defVal.getBitWidth();
					auto alloca = builder.CreateAlloca(builder.getIntNTy(w),
							nullptr, ioArg->getName() + "." + name);
					bool isIn = dir == IODirection::IO_DIR_IN;

					HwtHlsIoMetadata md(dir, 0, isIn ? w : 0, isIn ? 0 : w,
							ioArgMd.otherThreadFn, ioArgMd.otherArgIndex, true,
							true,
							0, // hasBlockingLoad, hasBlockingStore,  bufferCapacity
							MetadataPropertyPath_append(builder.getContext(),
									ioArgMd.ioPropertyPath, name) // ioPropertyPath
									);
					argsToAddToParentFn.push_back( { alloca, md });
					return alloca;
				};
				if (loads.size()) {
					axiArTmpAlloca = mkTmpAlloca("ar", IODirection::IO_DIR_OUT,
							axiMMIoMd.arDefault);
					auto rDef = axiMMIoMd.rDefault.zext(
							axiMMIoMd.getWordWidth());
					axiRTmpAlloca = mkTmpAlloca("r", IODirection::IO_DIR_IN,
							rDef);
				}
				if (stores.size()) {
					axiAwTmpAlloca = mkTmpAlloca("aw", IODirection::IO_DIR_OUT,
							axiMMIoMd.awDefault);
					auto wDef = axiMMIoMd.wDefault.zext(
							axiMMIoMd.getWordWidth());
					axiWTmpAlloca = mkTmpAlloca("w", IODirection::IO_DIR_OUT,
							wDef);
					axiBTmpAlloca = mkTmpAlloca("b", IODirection::IO_DIR_IN,
							axiMMIoMd.bDefault);
				}
				DceWorklist DCE(&TLI);
				// lower access to this axiIoArg
				for (auto *ld : loads) {
					lowerAxiMMLoad(builder, DCE, axiMMIoMd, ld, axiArTmpAlloca,
							axiRTmpAlloca);
				}
				for (auto *st : stores) {
					lowerAxiMMStore(builder, DCE, axiMMIoMd, st, axiAwTmpAlloca,
							axiWTmpAlloca, axiBTmpAlloca);
				}
				DCE.runToCompletition();
				changed = true;
			}
			++ioArg;
		}
		updateArgsOfParentFunction(builder, F, argsToAddToParentFn);
		AM.getResult<FunctionAnalysisManagerModuleProxy>(M).getManager().invalidate(F, PreservedAnalyses::none());
	}
	if (changed) {
		// return getLoopPassPreservedAnalyses();
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		PA.preserve<LoopAnalysis>();
		PA.preserve<LoopAnalysisManagerFunctionProxy>();
		PA.preserve<FunctionAnalysisManagerModuleProxy>();
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
