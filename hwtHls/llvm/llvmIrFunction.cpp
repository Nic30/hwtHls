#include <hwtHls/llvm/llvmIrFunction.h>

#include <algorithm>
#include <map>

#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/Transforms/Utils/ValueMapper.h>

#include <hwtHls/llvm/llvmIrCommon.h>
#include <hwtHls/llvm/llvmIrMetadata.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

#include <pybind11/stl.h>

namespace py = pybind11;

namespace hwtHls {

template<typename T>
T* valueCaster(llvm::Value *V) {
	if (auto *_v = llvm::dyn_cast<T>(V)) {
		return _v;
	} else {
		return (T*) nullptr;
	}
}

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
/*
 * Mutate type of pointer instructions to use new address space
 * */
void rewriteAddressSpace(llvm::IRBuilder<> &Builder,
		std::map<llvm::Value*, llvm::Value*> replacements, llvm::Value &V,
		llvm::Type *NewPtrTy) {
	using namespace llvm;
	assert(V.getType()->isPointerTy());
	auto replacement = replacements.find(&V);
	for (auto *U : make_early_inc_range(V.users())) {
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
			rewriteAddressSpace(Builder, replacements, *GEP, NewPtrTy);
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
			auto prevPtrName = ".p" + std::to_string(V.getType()->getPointerAddressSpace()) + ".";
			auto newPtrName = ".p" + std::to_string(replacement->second->getType()->getPointerAddressSpace()) + ".";
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
		llvm::Argument &NewArg) {
	if (Arg.getType() != NewArg.getType()) {
		assert(Arg.getType()->isPointerTy());
		assert(NewArg.getType()->isPointerTy());
		std::map<llvm::Value*, llvm::Value*> replacements =
				{ { &Arg, &NewArg }, };
		rewriteAddressSpace(Builder, replacements, Arg, NewArg.getType());
	} else {
		Arg.replaceAllUsesWith(&NewArg);
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
		replaceAlUsesOfArgumentWithPotentiallyChangedAddressSpace(Builder, Arg, NewFArg);
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

void register_Function(pybind11::module_ & m) {
	py::class_<llvm::Function, std::unique_ptr<llvm::Function, py::nodelete>, llvm::GlobalValue> Function(m, "Function");
	Function.def("__repr__",  &printToStr<llvm::Function>)
		.def("Create",
			[](llvm::FunctionType *Ty, llvm::Function::LinkageTypes Linkage,
					const llvm::Twine &N, llvm::Module &M) {
				return llvm::Function::Create(Ty, Linkage, N, M);
			}, //py::keep_alive<0, 1>(), py::keep_alive<0, 2>(),
			   //py::keep_alive<0, 3>(), py::keep_alive<0, 4>()
			py::return_value_policy::reference_internal) /*keep dependencies alive while Function exists */
		.def("getGlobalIdentifier", [](llvm::Function *self) { return self->getGlobalIdentifier();})
		.def("getParent", [](llvm::Function & F) {return F.getParent();}, py::return_value_policy::reference_internal)
		.def("args", [](llvm::Function *self) {
				return py::make_iterator(self->arg_begin(), self->arg_end(),
						py::return_value_policy::reference);
			 }, py::keep_alive<0, 1>()) /* Keep Function alive while iterator is used */
		.def("arg_size", &llvm::Function::arg_size)
		.def("getArg", &llvm::Function::getArg, py::return_value_policy::reference_internal)
		.def("mutateFunctionAddArg", &mutateFunctionAddArg,  py::arg("ParamTy"), py::arg("ParamName"),
				"create a new function with parameter added and move function body into it",
				py::return_value_policy::reference_internal)
		.def("mutateFunctionShuffleArgs", &mutateFunctionShuffleArgs, py::arg("newOrder"),
				"create a new function with parameters shuffled",
				py::return_value_policy::reference_internal)
		.def("__iter__", [](llvm::Function &F) {
				return py::make_iterator(F.begin(), F.end());
			 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("getMetadata", [](llvm::Function * I, llvm::StringRef Kind) {
				return reinterpret_cast<MDNodeWithDeletedDelete*>(I->getMetadata(Kind));
		})
		.def("setMetadata", [](llvm::Function * F, llvm::StringRef Kind, MDNodeWithDeletedDelete *Node) {
			F->setMetadata(Kind, Node);
		})
		.def("getIntrinsicID", &llvm::Function::getIntrinsicID)
		.def("addFnAttrKind", [](llvm::Function*F, llvm::Attribute::AttrKind Attr) {
			F->addFnAttr(Attr);
		})
		.def("getEntryBlock", [](llvm::Function *self) {
			return &self->getEntryBlock();
		}, py::return_value_policy::reference_internal);

	m.def("ValueToFunction", &valueCaster<llvm::Function>);
	py::class_<llvm::Argument, std::unique_ptr<llvm::Argument, py::nodelete>, llvm::Value>(m, "Argument")
		.def("setName", &llvm::Argument::setName)
		.def("getName", &llvm::Argument::getName)
		.def("getType", &llvm::Argument::getType)
		.def("getArgNo", &llvm::Argument::getArgNo)
		.def("getParent", [](llvm::Argument * self) { return self->getParent(); }, py::return_value_policy::reference_internal)
		;
	m.def("ValueToArgument", &valueCaster<llvm::Argument>);

	py::class_<llvm::Attribute, std::unique_ptr<llvm::Attribute, py::nodelete>> Attribute(m, "Attribute");
	py::enum_<llvm::Attribute::AttrKind> AttrKind(Attribute, "AttrKind");
	AttrKind.value("None",            llvm::Attribute::AttrKind::None           );
#define GET_ATTR_NAMES
#define _QUOTE(x) #x
#define ATTRIBUTE_ENUM(name, name_snakecase)  AttrKind.value(_QUOTE(name), llvm::Attribute::AttrKind::name);
#include <llvm/IR/Attributes.inc>
	AttrKind.export_values();

	m.def("AddDefaultFunctionAttributes", &AddDefaultFunctionAttributes);

	py::class_<llvm::FunctionCallee> FunctionCallee(m, "FunctionCallee");
	FunctionCallee.def(py::init<llvm::Function *>());

	auto Intrinsic = m.def_submodule("Intrinsic");
	py::enum_<llvm::Intrinsic::IndependentIntrinsics> IndependentIntrinsics(Intrinsic, "IndependentIntrinsics");
	for (unsigned I= llvm::Intrinsic::IndependentIntrinsics::abs; I <= llvm::Intrinsic::xray_typedevent; ++I) {
		auto _name = llvm::Intrinsic::getBaseName(I);
		assert(_name.starts_with("llvm."));
		std::string name = _name.substr(std::string("llvm.").length()).str();
		std::replace(name.begin(), name.end(), '.', '_');
		IndependentIntrinsics.value(name.c_str(), llvm::Intrinsic::IndependentIntrinsics(I));
	}
	IndependentIntrinsics.export_values();

}

}
