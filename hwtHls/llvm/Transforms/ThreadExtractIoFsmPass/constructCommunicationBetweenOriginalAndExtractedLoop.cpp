#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/constructCommunicationBetweenOriginalAndExtractedLoop.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

void resolveExportedValues(LoopInfo &LI, Loop *L, ValueToValueMapTy &VMap,
		ValueToValueMapTy &VMapNewToOld,
		SetVector<Value*> &newInstructionsInNewFn,
		std::map<Loop*, LoopExports> &loopExports) {
	for (Loop *subLoop : *L) {
		resolveExportedValues(LI, subLoop, VMap, VMapNewToOld,
				newInstructionsInNewFn, loopExports);
	}
	LoopExports &loopExport = loopExports[L];
	//errs() << " L:" << *L << "\n";
	for (BasicBlock *_BB : L->blocks()) {
		//errs() << "BB: " << _BB->getName() << "\n";
		if (LI.getLoopFor(_BB) != L)
			continue; // this BB will be processed in some child loop.
		auto BB = dyn_cast<BasicBlock>(VMap[_BB]);
		assert(BB);
		for (auto &I : *BB) {
			bool isNewI = newInstructionsInNewFn.contains(&I);
			if (isNewI || I.isTerminator()) {
				// if instruction has dependency defined outside of this loop the dependency should be in beforeHeaderExports
				for (auto *op : I.operand_values()) {
					auto opI = dyn_cast<Instruction>(op);
					if (!opI)
						continue;
					if (newInstructionsInNewFn.contains(opI))
						continue;
					auto oldOpI = dyn_cast<Instruction>(VMapNewToOld[opI]);
					assert(oldOpI);
					if (L->contains(oldOpI))
						continue;
					loopExport.beforeHeaderExports.insert(oldOpI);
					//errs() << "beforeHeaderExports: " << * oldOpI << "\n";
				}
			}
			if (!isNewI) {
				// if instruction has use outside inside or after this loop in extracted code
				for (auto U : I.users()) {
					auto UI = dyn_cast<Instruction>(U);
					if (!UI)
						continue;
					if (!newInstructionsInNewFn.contains(UI) && !UI->isTerminator())
						continue;

					auto oldI = dyn_cast<Instruction>(VMapNewToOld[&I]);
					assert(oldI);
					bool added = false;
					for (auto* subL: L->getSubLoops()) {
						LoopExports &subLoopExport = loopExports[subL];
						if (subLoopExport.beforeHeaderSection.contains(_BB)) {
							// if the value is defined before some child loop, it must be exported on that place
							// because there is no export location after loop
							subLoopExport.beforeHeaderExports.insert(oldI);
							added = true;
						}
					}
					if (!added) {
						// if the value is not defined before any child loop it it safe to export it at this loop end
						loopExport.beforeExitOrLatchExports.insert(oldI);
						//errs() << "beforeExitOrLatchExports: " << * oldI << "\n";
					}
					break;
				}
			}
		}
	}

}

ArrayRef<Value*> castArrayRefOfInstructionToValue(ArrayRef<Instruction*> arr) {
	// We can create a new ArrayRef pointing to the same data with new
	return ArrayRef<Value*>(reinterpret_cast<Value* const*>(arr.data()),
			arr.size());
}

HwtHlsIoMetadata ExportFromOndThreadToNewThread_createAllocaAndStoreInOld(
		IRBuilder<> &Builder, BasicBlock::iterator allocaInsertPoint,
		Instruction *storeInsertPoint, const SetVector<Instruction*> &values,
		Function &F, Function &extractedF,
		SmallVector<ArgToAddToParentFn> &argsToAddToOldFn,
		AllocaInst *&tmpAlloca, size_t &addedArgI, IntegerType *&valueTy) {
	Builder.SetInsertPoint(storeInsertPoint);
	auto allInConcat = CreateBitConcat(&Builder,
			castArrayRefOfInstructionToValue(values.getArrayRef()));
	valueTy = dyn_cast<IntegerType>(allInConcat->getType());
	Builder.SetInsertPoint(allocaInsertPoint);
	addedArgI = F.arg_size() + argsToAddToOldFn.size();
	tmpAlloca = Builder.CreateAlloca(valueTy, addedArgI);
	Builder.SetInsertPoint(storeInsertPoint);
	Builder.CreateStore(allInConcat, tmpAlloca, true);
	HwtHlsIoMetadata mdSrc;
	mdSrc.direction = IODirection::IO_DIR_OUT;
	mdSrc.writeWordWidth = valueTy->getIntegerBitWidth();
	mdSrc.otherArgIndex = addedArgI;
	mdSrc.otherThreadFn = &extractedF;
	argsToAddToOldFn.push_back( { tmpAlloca, mdSrc });
	return mdSrc;
}

void ExportFromOndThreadToNewThread_createAllocaAndLoadInNew(
		IRBuilder<> &Builder, BasicBlock::iterator allocaInsertPoint,
		Instruction *loadInsertPoint, Function &F, Function &extractedF,
		IntegerType *valueTy, size_t addedArgI, ValueToValueMapTy &VMap,
		const SetVector<Instruction*> &values, AllocaInst *&tmpAlloca,
		SmallVector<ArgToAddToParentFn> &argsToAddToNewFn,
		SetVector<Value*> &newInstructionsInNewFn) {
	Builder.SetInsertPoint(allocaInsertPoint);
	tmpAlloca = Builder.CreateAlloca(valueTy, addedArgI);
	newInstructionsInNewFn.insert(tmpAlloca);

	Builder.SetInsertPoint(loadInsertPoint);
	auto allInConcatNew = Builder.CreateLoad(valueTy, tmpAlloca);
	newInstructionsInNewFn.insert(allInConcatNew);
	size_t bitOffset = 0;
	for (auto *v : values) {
		assert(bitOffset < valueTy->getIntegerBitWidth());
		size_t w = v->getType()->getIntegerBitWidth();
		Value *vInNew = &*VMap[v];
		auto newVReplacement = CreateBitRangeGetConst(&Builder, allInConcatNew,
				bitOffset, w);
		newInstructionsInNewFn.insert(newVReplacement);
		newVReplacement->takeName(vInNew);
		vInNew->replaceAllUsesWith(newVReplacement);
		bitOffset += w;
	}
	HwtHlsIoMetadata mdDst;
	mdDst.direction = IODirection::IO_DIR_IN;
	mdDst.writeWordWidth = valueTy->getIntegerBitWidth();
	mdDst.otherArgIndex = addedArgI;
	mdDst.otherThreadFn = &F;
	argsToAddToNewFn.push_back( { tmpAlloca, mdDst });
}

void constructCommunicationBetweenOriginalAndExtractedLoop(IRBuilder<> &Builder,
		Function &F, Function &extractedF,
		SmallVector<ArgToAddToParentFn> &argsToAddToOldFn,
		SmallVector<ArgToAddToParentFn> &argsToAddToNewFn,
		std::map<Loop*, LoopExports> &loopExports,
		SetVector<Instruction*> &alreadyExported, ValueToValueMapTy &VMap,
		ValueToValueMapTy &VMapNewToOld,
		BasicBlock::iterator allocaInsertPointInOld,
		BasicBlock::iterator allocaInsertPointInNew, Loop *L,
		SetVector<Value*> &newInstructionsInNewFn) {
	// :note: F has already remove extracted instructions
	LoopExports &loopExport = loopExports[L];
	// [todo] check the dominance it is not guaranteed because
	//        we are not capturing the value in the point of definition but in loop preheader
	loopExport.beforeHeaderExports.remove_if([&alreadyExported](Instruction *v) {
		return alreadyExported.contains(v);
	});
	//errs() << "beforeHeader of " << *L;
	if (loopExport.beforeHeaderExports.size()) {
		//for (auto *I : loopExport.beforeHeaderExports) {
		//	errs() << "    " << *I << "\n";
		//}
		BasicBlock *preHeader = L->getLoopPreheader();
		if (!preHeader) {
			// if the header does not have
			// https://stackoverflow.com/questions/5774428/insert-a-statement-before-the-execution-of-a-loop
			llvm_unreachable("[todo] form a dedicated preheader");
		}

		size_t addedArgI;
		IntegerType *valueTy = nullptr;
		ExportFromOndThreadToNewThread_createAllocaAndStoreInOld(Builder,
				allocaInsertPointInOld, preHeader->getTerminator(),
				loopExport.beforeHeaderExports, F, extractedF, argsToAddToOldFn,
				loopExport.beforeHeaderInOld, addedArgI, valueTy);
		// :attention: the pre-header section does not necessary be just 1 block
		//  and thus preHeaderNew->getFirstInsertionPt() may not be the correct place
		auto preHeaderNew = dyn_cast<BasicBlock>(&*VMap[preHeader]);
		ExportFromOndThreadToNewThread_createAllocaAndLoadInNew(Builder,
				allocaInsertPointInNew, &*preHeaderNew->getFirstInsertionPt(), F,
				extractedF, valueTy, addedArgI, VMap,
				loopExport.beforeHeaderExports, loopExport.beforeHeaderInNew,
				argsToAddToNewFn, newInstructionsInNewFn);
	} else {
		//errs() << "    <none>\n";
	}

	alreadyExported.insert(loopExport.beforeHeaderExports.begin(),
			loopExport.beforeHeaderExports.end());
	for (Loop *cLoop : *L) {
		constructCommunicationBetweenOriginalAndExtractedLoop(Builder, F,
				extractedF, argsToAddToOldFn, argsToAddToNewFn, loopExports,
				alreadyExported, VMap, VMapNewToOld, allocaInsertPointInOld,
				allocaInsertPointInNew, cLoop, newInstructionsInNewFn);
	}

	loopExport.beforeExitOrLatchExports.remove_if(
			[&alreadyExported](Instruction *v) {
				return alreadyExported.contains(v);
			});
	//errs() << "beforeExit of " << *L;
	if (loopExport.beforeExitOrLatchExports.size()) {
		//for (auto *I : loopExport.beforeExitOrLatchExports) {
		//	errs() << "    " << *I << "\n";
		//}

		SmallVector<Loop::Edge> edgesForExport;
		L->getExitEdges(edgesForExport);
		SmallVector<BasicBlock*> latches;
		L->getLoopLatches(latches);
		auto header = L->getHeader();
		for (auto latch : latches) {
			edgesForExport.push_back( { latch, header });
		}
		std::map<BasicBlock*, size_t> cntOfExportingEdgeFromBB;
		for (const auto& [src, _] : edgesForExport) {
			auto cur = cntOfExportingEdgeFromBB.find(src);
			if (cur == cntOfExportingEdgeFromBB.end()) {
				cntOfExportingEdgeFromBB[src] = 1;
			} else {
				cur->second++;
			}
		}
		std::set<BasicBlock*> exitBBsWithExportAtEnd;
		auto headerInNew = dyn_cast<BasicBlock>(&*VMap[header]);
		for (const auto& [src, dst] : edgesForExport) {
			if (cntOfExportingEdgeFromBB[src]
					== src->getTerminator()->getNumSuccessors()) {
				// every branch from this bb will result in export
				// Store of exported variables may be constructed there
				if (exitBBsWithExportAtEnd.contains(src)) {
					// export already constructed
				} else {
					// :note: store is placed before each exit or reenter in the original loop
					//        load is placed in header of extracted loop
					size_t addedArgI;
					IntegerType *valueTy;
					ExportFromOndThreadToNewThread_createAllocaAndStoreInOld(
							Builder, allocaInsertPointInOld,
							src->getTerminator(),
							loopExport.beforeExitOrLatchExports, F, extractedF,
							argsToAddToOldFn, loopExport.beforeExitOrLatchInOld,
							addedArgI, valueTy);

					ExportFromOndThreadToNewThread_createAllocaAndLoadInNew(
							Builder, allocaInsertPointInNew,
							&*headerInNew->getFirstInsertionPt(), F, extractedF,
							valueTy, addedArgI, VMap,
							loopExport.beforeExitOrLatchExports,
							loopExport.beforeExitOrLatchInNew, argsToAddToNewFn,
							newInstructionsInNewFn);

					exitBBsWithExportAtEnd.insert(src);
				}

			} else {
				// only some branches from this bb will result in export
				// The store of exported variables must be only on some edges
				llvm_unreachable("[todo]");
			}
		}
	} else {
		// errs() << "    <none>\n";
	}
}

}
