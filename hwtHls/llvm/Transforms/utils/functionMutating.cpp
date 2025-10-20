#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

#include <algorithm>

#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/Metadata.h>
#include <llvm/ADT/DenseMap.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/StreamSegmentLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

namespace hwtHls {

llvm::Function* mutateFunctionAddArgs(llvm::Function &F,
		llvm::ArrayRef<llvm::Type*> ParamTys,
		llvm::ArrayRef<llvm::Twine> ParamNames) {
	// :note: based on R600OpenCLImageTypeLoweringPass::addImplicitArgs
	// It is not possible to:
	// * add new argument to args because it is an array
	// * use mutateType+stealArgumentListFrom because it does not update NumArgs
	llvm::FunctionType *Ty = F.getFunctionType();
	std::string Name = F.getName().str();
	llvm::SmallVector<llvm::Type*> _ParamTys;
	_ParamTys.insert(_ParamTys.begin(), Ty->param_begin(), Ty->param_end());
	_ParamTys.insert(_ParamTys.end(), ParamTys.begin(), ParamTys.end());
	llvm::FunctionType *NewTy = llvm::FunctionType::get(Ty->getReturnType(),
			_ParamTys, Ty->isVarArg());
	llvm::Function *NewF = llvm::Function::Create(NewTy, F.getLinkage(),
			F.getName(), *F.getParent());

	auto NewFArgIt = NewF->arg_begin();
	for (auto &Arg : F.args()) {
		auto ArgName = Arg.getName();
		NewFArgIt->setName(ArgName);
		Arg.replaceAllUsesWith(&*NewFArgIt);
		assert(Arg.hasNUses(0));
		++NewFArgIt;
	}
	auto newParamI = F.arg_size();
	for (auto name : ParamNames) {
		auto *NewArg = NewF->getArg(newParamI);
		NewArg->setName(name);
		newParamI++;
	}

	NewF->setAttributes(F.getAttributes());
	// do not use CloneFunctionInto, only move all code to new NewF, F is going to be replaced
	NewF->splice(NewF->begin(), &F);
	llvm::SmallVector<std::pair<unsigned, llvm::MDNode*>> MDs;
	F.getAllMetadata(MDs);
	assert(!F.getMetadata(HwtHlsIoMetadata::METADATA_NAME) && "NotImplemented");
	for (const auto &MD : MDs) {
		NewF->setMetadata(MD.first, MD.second);
	}
	F.replaceAllUsesWith(NewF);
	NewF->removeFromParent();
	F.getParent()->getFunctionList().insertAfter(F.getIterator(), NewF);
	F.eraseFromParent();
	NewF->setName(Name); // set to original name because NewF name has numbers added to prevent name collisions
	return NewF;
}

llvm::Function* mutateFunctionAddArg(llvm::Function &F, llvm::Type *ParamTy,
		const llvm::Twine &ParamName) {
	llvm::SmallVector<llvm::Type*> ParamTys;
	ParamTys.push_back(ParamTy);
	llvm::SmallVector<llvm::Twine> ParamNames;
	ParamNames.push_back(ParamName);
	return mutateFunctionAddArgs(F, ParamTys, ParamNames);
}

// https://stackoverflow.com/a/22183350
// https://stackoverflow.com/a/838652
// :param order: vector of indices where the item should be put in output in current index
//               e.g [1, 0] specifies the item which was originally at index 1 should be put on index 0 in output
template<typename T>
void reorder(llvm::SmallVector<T> &data, std::vector<std::size_t> order) {
	/* reorder data according to order */
	/* every move puts an element into place */
	/* time complexity is O(n) */
	for (size_t i = 0; i < order.size(); i++) {
		if (i != order[i]) {
			T tA = data[i];
			size_t j = i;
			size_t k;
			while (i != (k = order[j])) {
				data[j] = data[k];
				order[j] = j;
				j = k;
			}
			data[j] = tA;
			order[j] = j;
		}
	}
}

// https://stackoverflow.com/a/3418285
bool String_replaceAll(std::string &str, const std::string &from,
		const std::string &to) {
	bool found = false;
	if (from.empty())
		return found;
	size_t start_pos = 0;
	while ((start_pos = str.find(from, start_pos)) != std::string::npos) {
		str.replace(start_pos, from.length(), to);
		start_pos += to.length(); // In case 'to' contains 'from', like replacing 'x' with 'yx'
		found = true;
	}
	return found;
}

void rewriteAddressSpace(llvm::IRBuilder<> &Builder,
		std::map<llvm::Value*, llvm::Value*> replacements, llvm::Value &V,
		llvm::Type *NewPtrTy, std::function<bool(llvm::User*)> *userFilter) {
	using namespace llvm;
	assert(V.getType()->isPointerTy());
	auto replacement = replacements.find(&V);
	for (auto *U : make_early_inc_range(V.users())) {
		if (userFilter && !(*userFilter)(U))
			continue;
		if (auto L = dyn_cast<LoadInst>(U)) {
			assert(replacement != replacements.end());
			L->setOperand(L->getPointerOperandIndex(), replacement->second);
		} else if (auto S = dyn_cast<StoreInst>(U)) {
			assert(replacement != replacements.end());
			S->setOperand(S->getPointerOperandIndex(), replacement->second);
		} else if (auto GEP = dyn_cast<GetElementPtrInst>(U)) {
			Builder.SetInsertPoint(GEP);
			std::string Name = GEP->getName().str();
			assert(replacement != replacements.end());
			SmallVector<Value*> indices;
			for (Use &indx : GEP->indices()) {
				indices.push_back(indx.get());
			}
			Value *NewGEP = Builder.CreateGEP(GEP->getSourceElementType(),
					replacement->second, indices, Name, GEP->isInBounds());
			assert(!replacements.contains(GEP));
			replacements[GEP] = NewGEP;
			rewriteAddressSpace(Builder, replacements, *GEP, NewPtrTy,
					userFilter);
			assert(GEP->hasNUses(0));
			GEP->eraseFromParent();
			NewGEP->setName(Name); // set name after remove of original instr. to have name without number at end
		} else if (auto CI = dyn_cast<CallInst>(U)) {
			// update all parameter types to new address space by creating of new function prototype
			Builder.SetInsertPoint(CI);
			if (auto II = dyn_cast<IntrinsicInst>(CI)) {
				switch (II->getIntrinsicID()) {
				case Intrinsic::IndependentIntrinsics::lifetime_start:
					Builder.CreateLifetimeStart(replacement->second);
					CI->eraseFromParent();
					continue;
				case Intrinsic::IndependentIntrinsics::lifetime_end:
					Builder.CreateLifetimeEnd(replacement->second);
					CI->eraseFromParent();
					continue;
				default:
					llvm_unreachable("Unsupported IntrinsicInst");
				}
			} else {
				assert(hwtHls::IsStreamIo(CI));
			}
			std::string Name = CI->getName().str();
			SmallVector<Value*, 8> Args;
			SmallVector<Type*, 8> ArgTys;
			for (Use &A : CI->args()) {
				auto ArgVal = A.get();
				auto Ty = ArgVal->getType();
				if (Ty == V.getType()) {
					ArgVal = replacement->second;
					Ty = ArgVal->getType();
				}
				Args.push_back(ArgVal);
				ArgTys.push_back(Ty);
			}
			Type *RetTy = CI->getType();

			Module &M = *Builder.GetInsertBlock()->getParent()->getParent();
			auto &CalledFn = *CI->getCalledFunction();
			auto FnName = CalledFn.getName().str();
			auto prevPtrName = ".p"
					+ std::to_string(V.getType()->getPointerAddressSpace());
			auto newPtrName =
					".p"
							+ std::to_string(
									replacement->second->getType()->getPointerAddressSpace());
			assert(String_replaceAll(FnName, prevPtrName, newPtrName));
			Function *TheFn = cast<Function>(
					M.getOrInsertFunction(FnName,
							FunctionType::get(RetTy, ArgTys, false),
							CalledFn.getAttributes()).getCallee());
			CallInst *NewCI = Builder.CreateCall(TheFn, Args);
			NewCI->copyIRFlags(CI);
			NewCI->copyMetadata(*CI);
			NewCI->setMemoryEffects(CI->getMemoryEffects());

			CI->replaceAllUsesWith(NewCI);
			CI->eraseFromParent();
			NewCI->setName(Name);
		} else if (auto addrCast = dyn_cast<AddrSpaceCastInst>(U)) {
			if (addrCast->getType() == NewPtrTy) {
				addrCast->replaceAllUsesWith(replacement->second);
			} else {
				Builder.SetInsertPoint(addrCast);
				auto repl = Builder.CreateAddrSpaceCast(replacement->second, addrCast->getType());
				repl->takeName(addrCast);
				addrCast->replaceAllUsesWith(repl);
				addrCast->eraseFromParent();
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

// :note: may return nullptr if the metadata is discarded
llvm::MDNode* recursivelyUpdateMetadataIoArgIndexes(llvm::MDNode *md,
		llvm::ArrayRef<std::string> mdNamesToUpdate,
		llvm::ArrayRef<std::optional<size_t>> oldArgToNewArgIndex) {
	if (llvm::MDTuple *t = dyn_cast<llvm::MDTuple>(md)) {
		bool arg1IsIoArgIndex = false;
		if (t->operands().size() >= 2) {
			auto &op0 = t->getOperand(0);
			if (auto op0str = llvm::cast<llvm::MDString>(op0.get())) {
				auto strVal = op0str->getString();
				for (auto &targetMdName : mdNamesToUpdate) {
					if (strVal == targetMdName) {
						arg1IsIoArgIndex = true;
						break;
					}
				}
			}
		}

		llvm::SmallVector<llvm::Metadata*> newOps;
		bool opsChanged = false;
		size_t opI = 0;
		for (auto &op : t->operands()) {
			llvm::Metadata *opV = op.get();
			llvm::Metadata *newOpV = opV;
			if (arg1IsIoArgIndex && opI == 1) {
				auto v = llvm::cast<llvm::ValueAsMetadata>(newOpV)->getValue();
				llvm::ConstantInt *argIc = llvm::dyn_cast<llvm::ConstantInt>(v);
				assert(argIc);
				size_t oldArgI = argIc->getZExtValue();
				if (oldArgI >= oldArgToNewArgIndex.size()) {
					llvm::errs() << *t;
					std::string errTmp =
							"recursivelyUpdateMetadataIoArgIndexes: Metadata references some IO argument of function which have never existed: ";
					llvm::raw_string_ostream errSS(errTmp);
					errSS << *t;
					throw std::runtime_error(errSS.str());
				}
				auto newArgI = oldArgToNewArgIndex[oldArgI];
				if (!newArgI.has_value()) {
					llvm::errs() << *t;
					std::string errTmp =
							"recursivelyUpdateMetadataIoArgIndexes: Metadata references IO argument of function which was just removed: ";
					llvm::raw_string_ostream errSS(errTmp);
					errSS << *t;
					throw std::runtime_error(errSS.str());
				}
				if (newArgI.value() != oldArgI) {
					auto newC = llvm::ConstantInt::get(argIc->getType(),
							newArgI.value());
					newOpV = llvm::ValueAsMetadata::getConstant(newC);
					opsChanged = true;
				}
			} else {
				if (auto opVMdn = llvm::dyn_cast<llvm::MDNode>(opV)) {
					newOpV = recursivelyUpdateMetadataIoArgIndexes(opVMdn,
							mdNamesToUpdate, oldArgToNewArgIndex);
					if (newOpV != opV)
						opsChanged = true;
				}
			}
			newOps.push_back(newOpV);
			++opI;
		}
		if (!opsChanged) {
			return md;
		} else if (t->isDistinct()) {
			assert(!t->isTemporary());
			return llvm::MDTuple::getDistinct(md->getContext(), newOps);
		} else {
			assert(!t->isTemporary());
			return llvm::MDTuple::get(md->getContext(), newOps);
		}
	} else {
		return md;
	}
}

void replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(
		llvm::IRBuilder<> &Builder, llvm::Value &V, llvm::Value &NewV,
		std::function<bool(llvm::User*)> *userFilter) {
	assert(V.getType()->isPointerTy());
	assert(NewV.getType()->isPointerTy());
	if (V.getType() != NewV.getType()) {
		std::map<llvm::Value*, llvm::Value*> replacements = { { &V, &NewV }, };
		rewriteAddressSpace(Builder, replacements, V, NewV.getType(),
				userFilter);
	} else {
		if (userFilter) {
			V.replaceUsesWithIf(&NewV, [&userFilter](llvm::Use &U) {
				return (*userFilter)(U.getUser());
			});
		} else {
			V.replaceAllUsesWith(&NewV);
		}
	}
}

void mutateFunctionShuffleArgs_updateStreamTmpAllocaMDs(llvm::Function *NewF,
		const llvm::SmallVector<std::optional<size_t> > &oldArgToNewArgIndex,
		size_t argsToDiscardFromEndCnt,
		llvm::DenseMap<llvm::MDNode*, llvm::MDNode*> &updatedMds) {
	auto &Ctx = NewF->getContext();
	auto StreamChannelPropsMdId = Ctx.getMDKindID(
			StreamChannelProps::METADATA_NAME_TMP_VAR_DATA_OFFSET);
	for (llvm::Instruction &I : *NewF->begin()) {
		if (llvm::isa<llvm::AllocaInst>(&I)) {
			if (auto md = I.getMetadata(StreamChannelPropsMdId)) {
				auto updatedMd = updatedMds.find(md);
				if (updatedMd != updatedMds.end()) {
					I.setMetadata(StreamChannelPropsMdId, updatedMd->second);
				} else {
					auto mdTuple = llvm::dyn_cast<llvm::MDTuple>(md);
					auto v = llvm::cast<llvm::ValueAsMetadata>(
							mdTuple->getOperand(0).get())->getValue();
					auto curIoArgI =
							llvm::dyn_cast<llvm::ConstantInt>(v)->getZExtValue();
					assert(curIoArgI < oldArgToNewArgIndex.size());
					auto _newIoArgI = oldArgToNewArgIndex[curIoArgI];
					assert(
							_newIoArgI.has_value()
									&& "Tmp StreamChannelProps AllocaInst metadata still uses removed IO");
					auto newIoArgI = _newIoArgI.value();
					assert(
							(newIoArgI
									< oldArgToNewArgIndex.size()
											- argsToDiscardFromEndCnt)
									&& "Tmp StreamChannelProps AllocaInst metadata still uses removed IO");
					llvm::MDNode *newMd = md;
					if (newIoArgI != curIoArgI) {
						newMd = llvm::MDTuple::get(Ctx,
								{ llvm::ValueAsMetadata::getConstant(
										llvm::ConstantInt::get(
												llvm::IntegerType::getInt32Ty(
														Ctx), newIoArgI)) });
						I.setMetadata(StreamChannelPropsMdId, newMd);
					}
					updatedMds[md] = newMd;
				}
			}
		}
	}
}

void mutateFunctionShuffleArgs_updateStreamLoopMDs(llvm::Function *NewF,
		const llvm::SmallVector<std::optional<size_t> > &oldArgToNewArgIndex,
		llvm::DenseMap<llvm::MDNode*, llvm::MDNode*> &updatedMds) {
	std::array<std::string, 2> mdNamesToUpdate = {
			StreamLoopUnrollPass::METADATA_NAME,
			StreamSegmentLoopUnrollPass::METADATA_NAME_io };
	for (auto &BB : *NewF) {
		auto Ter = BB.getTerminator();
		if (!Ter)
			continue;

		llvm::MDNode *loopMd = Ter->getMetadata(llvm::LLVMContext::MD_loop);
		if (loopMd) {
			auto updatedMd = updatedMds.find(loopMd);
			if (updatedMd != updatedMds.end()) {
				Ter->setMetadata(llvm::LLVMContext::MD_loop, updatedMd->second);
			} else {
				// :note: we do not update all uses of this metadata as it may be used also in other functions
				// which are not a target of this update
				auto newMd = recursivelyUpdateMetadataIoArgIndexes(loopMd,
						mdNamesToUpdate, oldArgToNewArgIndex);
				if (newMd != loopMd) {
					Ter->setMetadata(llvm::LLVMContext::MD_loop, newMd);
				}
				updatedMds[loopMd] = newMd;
			}
		}
		//for (auto &I: BB) {
		//
		//}
	}
}

void mutateFunctionShuffleArgs_updateLatenciesFromPredecessorIo(
		llvm::Function *NewF,
		llvm::SmallVector<hwtHls::HwtHlsIoMetadata> &hwtHlsIoMD,
		const std::vector<std::size_t> &newOrder) {
	for (auto &newIoMd : hwtHlsIoMD) {
		if (newIoMd.latenciesFromPredecessorIo) {
			llvm::SmallVector<int> latencies;
			newIoMd.getLatenciesFromPredecessorIo(latencies);
			reorder<int>(latencies, newOrder);
			latencies.resize(hwtHlsIoMD.size());
			newIoMd.setLatenciesFromPredecessorIo(NewF->getContext(),
					latencies);
		}
	}
}

void mutateFunctionShuffleArgs_updateRefrenceToThisFInOtherFnMd(
		llvm::Function *NewF,
		const llvm::SmallVector<size_t> &newArgToOldArgIndex,
		const llvm::SmallVector<hwtHls::HwtHlsIoMetadata> &hwtHlsIoMD,
		std::optional<std::function<bool(const llvm::Function&)> > shouldUpdateOfOtherFnMd) {
	// update references to this F arguments in other function metadata
	for (size_t newArgI = 0; newArgI < NewF->arg_size(); newArgI++) {
		size_t oldArgI = newArgToOldArgIndex[newArgI];
		if (oldArgI != newArgI) {
			const auto &md = hwtHlsIoMD[newArgI];
			if (!md.otherThreadFn)
				continue;

			if (shouldUpdateOfOtherFnMd.has_value()
					&& !shouldUpdateOfOtherFnMd.value()(*md.otherThreadFn))
				continue;

			assert(md.otherThreadFn != NewF);
			auto _otherMd = HwtHlsIoMetadata_get(*md.otherThreadFn,
					md.otherArgIndex);
			if (_otherMd.has_value()) {
				HwtHlsIoMetadata otherMd = _otherMd.value();
				assert(otherMd.otherThreadFn == NewF);
				assert(otherMd.otherArgIndex == oldArgI);
				otherMd.otherArgIndex = newArgI;
				HwtHlsIoMetadata_set(*md.otherThreadFn, md.otherArgIndex,
						otherMd);
			}
		}
	}
}

llvm::Function* mutateFunctionShuffleArgs(llvm::Function &F,
		const std::vector<std::size_t> &newOrder,
		size_t argsToDiscardFromEndCnt,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd) {
	// :see: doc in mutateFunctionAddArg explaining why new function must be created
	assert(argsToDiscardFromEndCnt <= F.arg_size());
	llvm::FunctionType *Ty = F.getFunctionType();
	std::string Name = F.getName().str();
	assert(Ty->params().size() == newOrder.size());

	llvm::SmallVector<llvm::Type*> ParamTys;
	ParamTys.insert(ParamTys.begin(), Ty->param_begin(), Ty->param_end());
	auto hwtHlsIoMD = HwtHlsIoMetadata_get(F);
	reorder<HwtHlsIoMetadata>(hwtHlsIoMD, newOrder);
	reorder<llvm::Type*>(ParamTys, newOrder);
	llvm::SmallVector<size_t> newArgToOldArgIndex;
	newArgToOldArgIndex.resize(F.arg_size());
	for (size_t srcI = 0; srcI < ParamTys.size(); ++srcI) {
		newArgToOldArgIndex[srcI] = srcI;
	}
	reorder<size_t>(newArgToOldArgIndex, newOrder);

	{
		// filter out removed items from ParamTys, ArgAddrWidthMetadata
		size_t newArgCnt = F.arg_size() - argsToDiscardFromEndCnt;
		hwtHlsIoMD.resize(newArgCnt);
		ParamTys.resize(newArgCnt);
		newArgToOldArgIndex.resize(newArgCnt);
		// update arg pointer type address space
		for (size_t i = 0; i < ParamTys.size(); ++i) {
			auto pTy = ParamTys[i];
			if (auto pTyPtr = dyn_cast<llvm::PointerType>(pTy)) {
				if (pTyPtr->getAddressSpace() != i + 1) {
					// update address space to match new final argument index + 1
					ParamTys[i] = llvm::PointerType::get(pTy->getContext(),
							i + 1);
				}
			}
		}
	}

	llvm::FunctionType *NewTy = llvm::FunctionType::get(Ty->getReturnType(),
			ParamTys, Ty->isVarArg());
	llvm::Function *NewF = llvm::Function::Create(NewTy, F.getLinkage(),
			F.getName(), *F.getParent());
	llvm::IRBuilder<> Builder(F.getContext());
	// update address space and name for new args
	for (auto &NewFArg : NewF->args()) {
		auto &Arg = *F.getArg(newArgToOldArgIndex[NewFArg.getArgNo()]);
		if (&NewFArg == &Arg)
			continue; // argument remained on the same index

		auto ArgName = Arg.getName();
		NewFArg.setName(ArgName);
		replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(Builder, Arg,
				NewFArg, nullptr);
	}

	NewF->setAttributes(F.getAttributes());
	// do not use CloneFunctionInto, only move all code to new NewF, F is going to be replaced
	NewF->splice(NewF->begin(), &F);
	llvm::SmallVector<std::pair<unsigned, llvm::MDNode*>> MDs;
	F.getAllMetadata(MDs);
	for (const auto &MD : MDs) {
		NewF->setMetadata(MD.first, MD.second);
	}

	NewF->setMetadata(HwtHlsIoMetadata::METADATA_NAME, nullptr);
	mutateFunctionShuffleArgs_updateLatenciesFromPredecessorIo(NewF, hwtHlsIoMD,
			newOrder);
	HwtHlsIoMetadata_set(*NewF, hwtHlsIoMD);

	F.replaceAllUsesWith(NewF);
	NewF->removeFromParent();
	F.getParent()->getFunctionList().insertAfter(F.getIterator(), NewF);
	F.eraseFromParent();
	NewF->setName(Name); // set to original name because NewF name has numbers added to prevent name collisions

	// update references to this F arguments in other function metadata
	mutateFunctionShuffleArgs_updateRefrenceToThisFInOtherFnMd(NewF,
			newArgToOldArgIndex, hwtHlsIoMD, shouldUpdateOfOtherFnMd);
	llvm::SmallVector<std::optional<size_t>> oldArgToNewArgIndex;
	oldArgToNewArgIndex.resize(NewF->arg_size() + argsToDiscardFromEndCnt);
	for (size_t newArgI = 0; newArgI < NewF->arg_size(); newArgI++) {
		size_t oldArgI = newArgToOldArgIndex[newArgI];
		oldArgToNewArgIndex[oldArgI] = newArgI;
	}
	// update references to to this F arguments in metadata of instructions
	llvm::DenseMap<llvm::MDNode*, llvm::MDNode*> updatedMds;
	mutateFunctionShuffleArgs_updateStreamLoopMDs(NewF, oldArgToNewArgIndex,
			updatedMds);
	mutateFunctionShuffleArgs_updateStreamTmpAllocaMDs(NewF,
			oldArgToNewArgIndex, argsToDiscardFromEndCnt, updatedMds);

	return NewF;
}

}
