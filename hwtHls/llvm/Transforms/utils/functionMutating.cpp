#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

#include <algorithm>
#include <map>

#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Intrinsics.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

namespace hwtHls {


llvm::Function* mutateFunctionAddArg(llvm::Function &F, llvm::Type *ParamTy,
		const llvm::Twine &ParamName) {
	// :note: based on R600OpenCLImageTypeLoweringPass::addImplicitArgs
	// It is not possible to:
	// * add new argument to args because it is an array
	// * use mutateType+stealArgumentListFrom because it does not update NumArgs
	llvm::FunctionType *Ty = F.getFunctionType();
	std::string Name = F.getName().str();
	llvm::SmallVector<llvm::Type*> ParamTys;
	ParamTys.insert(ParamTys.begin(), Ty->param_begin(), Ty->param_end());
	ParamTys.push_back(ParamTy);
	llvm::FunctionType *NewTy = llvm::FunctionType::get(Ty->getReturnType(),
			ParamTys, Ty->isVarArg());
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
	auto *NewArg = NewF->getArg(NewF->arg_size() - 1);
	NewArg->setName(ParamName);

	NewF->setAttributes(F.getAttributes());
	// do not use CloneFunctionInto, only move all code to new NewF, F is going to be replaced
	NewF->splice(NewF->begin(), &F);
	llvm::SmallVector<std::pair<unsigned, llvm::MDNode*>> MDs;
	F.getAllMetadata(MDs);
	for (const auto &MD : MDs) {
		NewF->setMetadata(MD.first, MD.second);
	}
	F.replaceAllUsesWith(NewF);
	F.eraseFromParent();
	NewF->setName(Name); // set to original name because NewF name has numbers added to prevent name collisions
	return NewF;
}

// https://stackoverflow.com/a/22183350
// https://stackoverflow.com/a/838652
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
bool String_replaceAll(std::string& str, const std::string& from, const std::string& to) {
    bool found =  false;
    if(from.empty())
        return found;
    size_t start_pos = 0;
    while((start_pos = str.find(from, start_pos)) != std::string::npos) {
        str.replace(start_pos, from.length(), to);
        start_pos += to.length(); // In case 'to' contains 'from', like replacing 'x' with 'yx'
        found = true;
    }
    return found;
}

void rewriteAddressSpace(llvm::IRBuilder<> &Builder,
		std::map<llvm::Value*, llvm::Value*> replacements, llvm::Value &V,
		llvm::Type *NewPtrTy, std::function<bool(llvm::User *)>* userFilter) {
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
			rewriteAddressSpace(Builder, replacements, *GEP, NewPtrTy, userFilter);
			assert(GEP->hasNUses(0));
			GEP->eraseFromParent();
			NewGEP->setName(Name); // set name after remove of original instr. to have name without number at end
		} else if (auto CI = dyn_cast<CallInst>(U)) {
			// update all parameter types to new address space by creating of new function prototype
			assert(hwtHls::IsStreamIo(CI));
			Builder.SetInsertPoint(CI);
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
			auto prevPtrName = ".p" + std::to_string(V.getType()->getPointerAddressSpace());
			auto newPtrName = ".p" + std::to_string(replacement->second->getType()->getPointerAddressSpace());
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
		} else {
			std::string errStr =
					"NotImplemented: replaceAlUsesOfArgumentWithPotentiallyChangedAddressSpace ";
			raw_string_ostream ss(errStr);
			U->print(ss);
			throw std::runtime_error(ss.str());
		}
	}
}

void replaceAlUsesOfArgumentWithPotentiallyChangedAddressSpace(
		llvm::IRBuilder<> &Builder, llvm::Argument &Arg,
		llvm::Argument &NewArg, std::function<bool(llvm::User *)>* userFilter) {
	if (Arg.getType() != NewArg.getType()) {
		assert(Arg.getType()->isPointerTy());
		assert(NewArg.getType()->isPointerTy());
		std::map<llvm::Value*, llvm::Value*> replacements =
				{ { &Arg, &NewArg }, };
		rewriteAddressSpace(Builder, replacements, Arg, NewArg.getType(), userFilter);
	} else {
		if (userFilter) {
			Arg.replaceUsesWithIf(&NewArg, [&userFilter](llvm::Use & U) {
				return (*userFilter)(U.getUser());
			});
		} else {
			Arg.replaceAllUsesWith(&NewArg);
		}
	}
	assert(Arg.hasNUses(0));
}

llvm::Function* mutateFunctionShuffleArgs(llvm::Function &F,
		const std::vector<std::size_t> &newOrder) {
	// :see: doc in mutateFunctionAddArg explaining why new function must be created

	llvm::FunctionType *Ty = F.getFunctionType();
	std::string Name = F.getName().str();
	assert(Ty->params().size() == newOrder.size());

	llvm::SmallVector<llvm::Type*> ParamTys;
	ParamTys.insert(ParamTys.begin(), Ty->param_begin(), Ty->param_end());
	reorder<llvm::Type*>(ParamTys, newOrder);
	for (size_t i = 0; i < ParamTys.size(); ++i) {
		auto pTy = ParamTys[i];
		if (auto pTyPtr = dyn_cast<llvm::PointerType>(pTy)) {
			if (pTyPtr->getAddressSpace() != i + 1) {
				// update address space to match argument index + 1
				ParamTys[i] = llvm::PointerType::get(pTy->getContext(), i + 1);
			}
		}
	}

	llvm::FunctionType *NewTy = llvm::FunctionType::get(Ty->getReturnType(),
			ParamTys, Ty->isVarArg());
	llvm::Function *NewF = llvm::Function::Create(NewTy, F.getLinkage(),
			F.getName(), *F.getParent());
	llvm::IRBuilder<> Builder(F.getContext());
	for (auto &NewFArg : NewF->args()) {
		auto &Arg = *F.getArg(newOrder[NewFArg.getArgNo()]);
		if (&NewFArg == &Arg)
			continue; // argument remained on the same index
		auto ArgName = Arg.getName();
		NewFArg.setName(ArgName);
		replaceAlUsesOfArgumentWithPotentiallyChangedAddressSpace(Builder, Arg, NewFArg, nullptr);
	}

	NewF->setAttributes(F.getAttributes());
	// do not use CloneFunctionInto, only move all code to new NewF, F is going to be replaced
	NewF->splice(NewF->begin(), &F);
	llvm::SmallVector<std::pair<unsigned, llvm::MDNode*>> MDs;
	F.getAllMetadata(MDs);
	for (const auto &MD : MDs) {
		NewF->setMetadata(MD.first, MD.second);
	}
	F.replaceAllUsesWith(NewF);
	F.eraseFromParent();
	NewF->setName(Name); // set to original name because NewF name has numbers added to prevent name collisions
	return NewF;
}

}
