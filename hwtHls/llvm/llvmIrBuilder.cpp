#include <hwtHls/llvm/llvmIrBuilder.h>
#include <hwtHls/llvm/llvmIrMetadata.h>

#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/BuildLibCalls.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>


namespace py = pybind11;

PYBIND11_MAKE_OPAQUE(std::vector<llvm::Value*>);


namespace hwtHls {

#define COMMON_BIN_OP_ARGS_SHORT        py::arg("LHS"), py::arg("RHS"), py::arg("Name")= llvm::Twine("")
#define COMMON_BIN_OP_ARGS              py::arg("LHS"), py::arg("RHS"), py::arg("Name")= llvm::Twine(""), py::arg("HasNUW")=false, py::arg("HasNSW")=false
#define COMMON_BIN_OP_ARGS_WITH_ISEXACT py::arg("LHS"), py::arg("RHS"), py::arg("Name")= llvm::Twine(""), py::arg("isExact")=false

#define F_UN_OP(opName) \
.def(#opName, [](llvm::IRBuilder<> * self, llvm::Value *V, const llvm::Twine &Name) {\
	return self->opName(V, Name);\
}, py::return_value_policy::reference)

#define F_OP(opName) \
.def(#opName, [](llvm::IRBuilder<> * self, llvm::Value *L, llvm::Value *R, const llvm::Twine &Name) {\
	return self->opName(L, R, Name);\
}, py::return_value_policy::reference)

// Value *CreateTrunc(Value *V, Type *DestTy, const Twine &Name = "")
#define CAST_OP(opName) \
.def(#opName, [](llvm::IRBuilder<> * self, llvm::Value *V, llvm::Type *DestTy, const llvm::Twine &Name) {\
		if (V->getType()->isIntegerTy() && \
			DestTy->isIntegerTy() && \
			V->getType()->getIntegerBitWidth() > DestTy->getIntegerBitWidth()) {\
			 /*some form of trunc, use CreateBitRangeGetConst to put truncat close to src*/ \
			 return CreateBitRangeGetConst(self, V, 0, DestTy->getIntegerBitWidth(), Name);       \
		}                                                                                   \
		return self->opName(V, DestTy, Name);                                               \
    },                                                                                       \
	py::arg("V"), py::arg("DestTy"), py::arg("Name")=llvm::Twine(""),\
	py::return_value_policy::reference)


void register_IRBuilder(pybind11::module_ & m) {
	/*
	 * :attention: pybind11 does does not know that llvm::IRBuilderBase and other llvm::IRBuilder<> variants
	 *             are compatible with IRBuilder, the builder must be manually casted
	 * */
	py::class_<llvm::IRBuilder<>>(m, "IRBuilder")
		.def(py::init<llvm::LLVMContext&>())
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock *TheBB) {
				return self->SetInsertPoint(TheBB);
			}, py::return_value_policy::reference)
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock * TheBB, llvm::BasicBlock::iterator IP) {
				self->SetInsertPoint(TheBB, IP);
			})
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock * TheBB, llvm::Instruction* I) {
				self->SetInsertPoint(TheBB, I->getIterator());
			})
		.def("saveIP",	&llvm::IRBuilder<>::saveIP)
		.def("restoreIP",	&llvm::IRBuilder<>::restoreIP)
		.def("getContext", &llvm::IRBuilder<>::getContext, py::return_value_policy::reference)
		.def("CreateAlloca", [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *ArraySize = nullptr, const llvm::Twine &Name = "") {
				return self->CreateAlloca(Ty, ArraySize, Name);
			}, py::return_value_policy::reference)
		.def("CreateAnd", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
				return self->CreateAnd(LHS, RHS, Name);
			}, py::return_value_policy::reference)
		.def("CreateOr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
				return self->CreateOr(LHS, RHS, Name);
			}, py::return_value_policy::reference)
		.def("CreateXor", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
				return self->CreateXor(LHS, RHS, Name);
			}, py::return_value_policy::reference)
		.def("CreateNeg", &llvm::IRBuilder<>::CreateNeg,
				py::return_value_policy::reference)
		.def("CreateAdd", &llvm::IRBuilder<>::CreateAdd,
				COMMON_BIN_OP_ARGS, py::return_value_policy::reference)
		.def("CreateSub", &llvm::IRBuilder<>::CreateSub,
				COMMON_BIN_OP_ARGS, py::return_value_policy::reference)
		.def("CreateMul", &llvm::IRBuilder<>::CreateMul,
				COMMON_BIN_OP_ARGS, py::return_value_policy::reference)
		.def("CreateUDiv", &llvm::IRBuilder<>::CreateUDiv,
				COMMON_BIN_OP_ARGS_WITH_ISEXACT, py::return_value_policy::reference)
		.def("CreateSDiv", &llvm::IRBuilder<>::CreateSDiv,
				COMMON_BIN_OP_ARGS_WITH_ISEXACT, py::return_value_policy::reference)
		.def("CreateAShr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool isExact=false) {
			return self->CreateAShr(LHS, RHS, Name, isExact);
		 }, COMMON_BIN_OP_ARGS_WITH_ISEXACT)
		.def("CreateLShr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool isExact=false) {
			return self->CreateLShr(LHS, RHS, Name, isExact);
		 }, COMMON_BIN_OP_ARGS_WITH_ISEXACT, py::return_value_policy::reference)
		.def("CreateShl", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool HasNUW = false, bool HasNSW = false) {
			return self->CreateShl(LHS, RHS, Name, HasNUW, HasNSW);
		}, COMMON_BIN_OP_ARGS, py::return_value_policy::reference)
		.def("CreateRetVoid", &llvm::IRBuilder<>::CreateRetVoid, py::return_value_policy::reference)
		.def("CreateStore", [](llvm::IRBuilder<> &self, llvm::Value *Val, llvm::Value *Ptr, bool isVolatile = false) {
				if (!Val->getType()->isSized())
					throw std::runtime_error("StoreInst is implemented only for sized types");
				return self.CreateStore(Val, Ptr, isVolatile);
			}, py::arg("Val"), py::arg("Ptr"), py::arg("isVolatile") = false,
			py::return_value_policy::reference)
		.def("CreateMemCpy", [](llvm::IRBuilder<> &self,
				llvm::Value *Dst, llvm::MaybeAlign DstAlign, llvm::Value *Src,
                llvm::MaybeAlign SrcAlign, uint64_t Size,
                bool isVolatile = false, MDNodeWithDeletedDelete *TBAATag = nullptr,
                MDNodeWithDeletedDelete *TBAAStructTag = nullptr,
                MDNodeWithDeletedDelete *ScopeTag = nullptr,
                MDNodeWithDeletedDelete *NoAliasTag = nullptr) {
			return self.CreateMemCpy(Dst, DstAlign, Src, SrcAlign, Size, isVolatile, TBAATag, TBAAStructTag, ScopeTag, NoAliasTag);
		},
			py::arg("Dst"), py::arg("DstAlign"), py::arg("Src"),
			py::arg("SrcAlign"), py::arg("Size"),
			py::arg("isVolatile") = false, py::arg("TBAATag") = static_cast<MDNodeWithDeletedDelete*>(nullptr),
		    py::arg("TBAAStructTag") = static_cast<MDNodeWithDeletedDelete*>(nullptr),
		    py::arg("ScopeTag") = static_cast<MDNodeWithDeletedDelete*>(nullptr),
		    py::arg("NoAliasTag") = static_cast<MDNodeWithDeletedDelete*>(nullptr),
			py::return_value_policy::reference
		)
		.def("CreateLoad", [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *Ptr, bool isVolatile,
                const llvm::Twine &Name = "") {
				if (!Ty->isSized())
					throw std::runtime_error("LoadInst is implemented only for sized types");
				return self->CreateLoad(Ty, Ptr, isVolatile, Name);
			}, py::arg("Ty"), py::arg("Ptr"), py::arg("isVolatile") = false, py::arg("Name")=llvm::Twine(""),
			py::return_value_policy::reference)
		.def("CreateStreamRead", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr, size_t chunkBitWidth, size_t returnBitWidth,
				bool isReliable, const llvm::Twine &Name = "") {
				auto I = CreateStreamRead(self, ioArgPtr, chunkBitWidth, returnBitWidth, isReliable);
				I->setName(Name);
				return I;
			},py::arg("ioArgPtr"), py::arg("chunkBitWidth"), py::arg("returnBitWidth"),
			  py::arg("isReliable"), py::arg("Name") = llvm::Twine(""), py::return_value_policy::reference)
		.def("CreateStreamReadStartOfFrame", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr) {
				return CreateStreamReadStartOfFrame(self, ioArgPtr);
			}, py::return_value_policy::reference)
		.def("CreateStreamReadEndOfFrame", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr) {
			return CreateStreamReadEndOfFrame(self, ioArgPtr);
		}, py::return_value_policy::reference)
		.def("CreateStreamWrite", [](llvm::IRBuilder<> *Builder, llvm::Value *ioArgPtr,
				llvm::Value *valueToWrite, llvm::Value *writeMask, llvm::Value *isEoF) {
			return CreateStreamWrite(Builder, ioArgPtr, valueToWrite, writeMask, isEoF);
		}, py::return_value_policy::reference)
		.def("CreateStreamWriteStartOfFrame", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr) {
			return CreateStreamWriteStartOfFrame(self, ioArgPtr);
		}, py::return_value_policy::reference)
		.def("CreateStreamWriteEndOfFrame", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr) {
			return CreateStreamWriteEndOfFrame(self, ioArgPtr);
		}, py::return_value_policy::reference)
		.def("CreateZExt", &llvm::IRBuilder<>::CreateZExt,
				py::arg("V"), py::arg("DestTy"), py::arg("Name")=llvm::Twine(""), py::arg("IsNonNeg")=false,
				py::return_value_policy::reference)
		CAST_OP(CreateSExt)
		CAST_OP(CreateZExtOrTrunc)
		CAST_OP(CreateSExtOrTrunc)
		CAST_OP(CreateFPToUI)
		CAST_OP(CreateFPToSI)
		CAST_OP(CreateUIToFP)
		CAST_OP(CreateSIToFP)
		CAST_OP(CreateFPTrunc)
		CAST_OP(CreateFPExt)
		CAST_OP(CreatePtrToInt)
		CAST_OP(CreateIntToPtr)
		CAST_OP(CreateBitCast)
		CAST_OP(CreateAddrSpaceCast)
		CAST_OP(CreateZExtOrBitCast)
		CAST_OP(CreateSExtOrBitCast)
		CAST_OP(CreateTruncOrBitCast)
		CAST_OP(CreatePointerCast)
		CAST_OP(CreateTrunc)
		.def("CreateSelect", &llvm::IRBuilder<>::CreateSelect, py::return_value_policy::reference)
		.def("CreatePHI", &llvm::IRBuilder<>::CreatePHI, py::return_value_policy::reference)
		.def("CreateICmpEQ", &llvm::IRBuilder<>::CreateICmpEQ, py::return_value_policy::reference)
		.def("CreateICmpNE", &llvm::IRBuilder<>::CreateICmpNE, py::return_value_policy::reference)
		.def("CreateICmpSGE", &llvm::IRBuilder<>::CreateICmpSGE, py::return_value_policy::reference)
		.def("CreateICmpUGE", &llvm::IRBuilder<>::CreateICmpUGE, py::return_value_policy::reference)
		.def("CreateICmpSGT", &llvm::IRBuilder<>::CreateICmpSGT, py::return_value_policy::reference)
		.def("CreateICmpUGT", &llvm::IRBuilder<>::CreateICmpUGT, py::return_value_policy::reference)
		.def("CreateICmpSLE", &llvm::IRBuilder<>::CreateICmpSLE, py::return_value_policy::reference)
		.def("CreateICmpULE", &llvm::IRBuilder<>::CreateICmpULE, py::return_value_policy::reference)
		.def("CreateICmpSLT", &llvm::IRBuilder<>::CreateICmpSLT, py::return_value_policy::reference)
		.def("CreateICmpULT", &llvm::IRBuilder<>::CreateICmpULT, py::return_value_policy::reference)
		.def("CreateBr", &llvm::IRBuilder<>::CreateBr, py::return_value_policy::reference)
		.def("CreateCondBr", [](llvm::IRBuilder<> * self, llvm::Value *Cond, llvm::BasicBlock *True, llvm::BasicBlock *False,
				llvm::Instruction *MDSrc) {
				return self->CreateCondBr(Cond, True, False, MDSrc);
			}, py::return_value_policy::reference)
		.def("CreateSwitch", [](llvm::IRBuilder<> & self, llvm::Value *V, llvm::BasicBlock *Dest, unsigned NumCases = 10,
				MDNodeWithDeletedDelete *BranchWeights = nullptr,
				MDNodeWithDeletedDelete *Unpredictable = nullptr) {
					return self.CreateSwitch(V, Dest, NumCases, BranchWeights, Unpredictable);
				},
				py::arg("V"),
				py::arg("Dest"),
				py::arg("NumCases")=10,
				py::arg("BranchWeights")=(MDNodeWithDeletedDelete *)nullptr,
				py::arg("Unpredictable")=(MDNodeWithDeletedDelete *)nullptr,
				py::return_value_policy::reference)
		.def("CreateBitRangeGet", &CreateBitRangeGet, py::return_value_policy::reference)
		.def("CreateBitRangeGetConst", &CreateBitRangeGetConst, py::return_value_policy::reference)
		.def("CreateBitConcat", [](llvm::IRBuilder<> * self, std::vector<llvm::Value*> & OpsLowFirst) {
			return CreateBitConcat(self, OpsLowFirst);
		}, py::return_value_policy::reference)
		.def("CreateGEP",  [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *Ptr, std::vector<llvm::Value *>& IdxList) {
			return self->CreateGEP(Ty, Ptr, IdxList, "", true);
		}, py::return_value_policy::reference)
		.def("CreateCall", [](llvm::IRBuilder<> * self, llvm::FunctionCallee Callee,
                std::vector<llvm::Value *> Args, const llvm::Twine &Name = "") {
			return self->CreateCall(Callee, Args, Name);
		}, py::arg("Callee"), py::arg("Args"), py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		.def("CreateAssumption", [](llvm::IRBuilder<> * self, llvm::Value *Cond) {
			return self->CreateAssumption(Cond);
		})
		.def("CreateCastToHFloatTmp", [](llvm::IRBuilder<>& Builder,
				llvm::Value *srcArg, const HFloatTmpConfig &cfg,  const llvm::Twine &Name) {
					auto t = srcArg->getType();
					if (!t->isIntegerTy()) {
						throw std::runtime_error("IRBuilder::CreateCastToHFloatTmp accepts only values of int type (which represents raw bits of a value)");
					} else if (t->getIntegerBitWidth() != cfg.getBitWidth()) {
						throw std::runtime_error("IRBuilder::CreateCastToHFloatTmp srcArg width is different than expected by srcCfg");
					}
					return CreateCastToHFloatTmp(Builder, srcArg, cfg, Name);
				},
				py::arg("srcArg"), py::arg("cfg"),
				py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		.def("CreateCastFromHFloatTmp", [](llvm::IRBuilder<>& Builder,
				llvm::Value *srcArg, const HFloatTmpConfig &cfg, const llvm::Twine &Name) {
					auto t = srcArg->getType();
					if (!t->isDoubleTy()) {
						throw std::runtime_error("IRBuilder::CreateCastFromHFloatTmp accepts only values of double type (which represent HFloatTmp type)");
					}

					return CreateCastFromHFloatTmp(Builder, srcArg, cfg, Name);
				},
				py::arg("srcArg"), py::arg("cfg"),
				py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		// CreateCastHFloatTmpToHFloatTmp and CreateCastHFloatTmpToHFloatTmpRaw both implement FPToUI, FPToSI, UIToFP, SIToFP like conversions
		// first variant works with double which represents HFloatTmp and raw with IntegerType which represents raw bits of value
		.def("CreateCastHFloatTmpToHFloatTmp", [](llvm::IRBuilder<>& Builder,
				llvm::Value *srcArg, const HFloatTmpConfig &cfg, const llvm::Twine &Name) {
					auto t = srcArg->getType();
					if (!t->isDoubleTy()) {
						throw std::runtime_error("IRBuilder::CreateCastHFloatTmpToHFloatTmp accepts only values of double type");
					}
					return CreateCastHFloatTmpToHFloatTmp(Builder, srcArg, cfg, Name);
				},
				py::arg("srcArg"), py::arg("cfg"),
				py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
    	.def("CreateCastHFloatTmpToHFloatTmpRaw", [](llvm::IRBuilder<>& Builder,
    			llvm::Value *srcArg, const HFloatTmpConfig &srcCfg, const HFloatTmpConfig &dstCfg, const llvm::Twine &Name) {
					auto t = srcArg->getType();
					if (!t->isIntegerTy()) {
						throw std::runtime_error("IRBuilder::CreateCastHFloatTmpToHFloatTmpRaw accepts only values of int type (which represents raw bits of a value)");
					} else if (t->getIntegerBitWidth() != srcCfg.getBitWidth()) {
						throw std::runtime_error("IRBuilder::CreateCastHFloatTmpToHFloatTmpRaw srcArg width is different than expected by srcCfg");
					}
					return CreateCastHFloatTmpToHFloatTmpRaw(Builder, srcArg, srcCfg, dstCfg, Name);
    			},
    			py::arg("srcArg"), py::arg("srcCfg"), py::arg("dstCfg"),
    			py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		F_UN_OP(CreateFNeg)
		F_OP(CreateFAdd)
		F_OP(CreateFSub)
		F_OP(CreateFMul)
		F_OP(CreateFDiv)
		F_OP(CreateFRem)
		F_OP(CreateFCmpOEQ)
		F_OP(CreateFCmpOGT)
		F_OP(CreateFCmpOGE)
		F_OP(CreateFCmpOLT)
		F_OP(CreateFCmpOLE)
		F_OP(CreateFCmpONE)
		F_OP(CreateFCmpORD)
		F_OP(CreateFCmpUNO)
		F_OP(CreateFCmpUEQ)
		F_OP(CreateFCmpUGT)
		F_OP(CreateFCmpUGE)
		F_OP(CreateFCmpULT)
		F_OP(CreateFCmpULE)
		F_OP(CreateFCmpUNE)
		.def("CreateFCmp", [](llvm::IRBuilder<> * self, llvm::CmpInst::Predicate p, llvm::Value *L, llvm::Value *R, const llvm::Twine &Name) {\
			return self->CreateFCmp(p, L, R, Name);\
		}, py::return_value_policy::reference)
		.def("CreateIntrinsic", [](llvm::IRBuilder<> * self,
					llvm::Type * RetTy,
					int ID,
					std::vector<llvm::Value *> Args,
					llvm::Instruction *FMFSource=nullptr,
					const llvm::Twine &Name="") {
				return self->CreateIntrinsic(RetTy, ID, Args, FMFSource, Name);
			},
			py::arg("RetTy"),
			py::arg("ID"),
			py::arg("Args"),
			py::arg("FMFSource")=(llvm::Instruction *)nullptr,
			py::arg("Name")=llvm::Twine(""),
			py::return_value_policy::reference
		);

    	py::bind_vector<std::vector<llvm::Value*>>(m, "VectorValuePtr");
		py::implicitly_convertible<py::list, std::vector<llvm::Value*>>();

		py::class_<llvm::IRBuilder<>::InsertPoint>(m, "InsertPoint")
		.def("getBlock", &llvm::IRBuilder<>::InsertPoint::getBlock, py::return_value_policy::reference);

	// https://stackoverflow.com/questions/73486177/llvm-how-to-add-libc-library-function-to-ir-module
	// llvm::FunctionType *fun_type = llvm::FunctionType::get(doubleTy, {doubleTy}, false);
	// llvm::getOrInsertLibFunc(module.get(), TLI, llvm::LibFunc_tan, fun_type);
	m.def("getOrInsertLibFunc_1", [](llvm::Module *M, const llvm::TargetLibraryInfo &TLI,
			llvm::LibFunc TheLibFunc, llvm::Type *RetTy, llvm::Type*Arg0Ty) {
		if (!TLI.has(TheLibFunc))
		  throw std::runtime_error("Creating call to non-existing library function.");

		return llvm::getOrInsertLibFunc(M, TLI, TheLibFunc, RetTy, Arg0Ty);
	}, py::return_value_policy::reference);
	m.def("getOrInsertLibFunc_2", [](llvm::Module *M, const llvm::TargetLibraryInfo &TLI,
			llvm::LibFunc TheLibFunc, llvm::Type *RetTy, llvm::Type*Arg0Ty, llvm::Type*Arg1Ty) {
		if (!TLI.has(TheLibFunc))
		  throw std::runtime_error("Creating call to non-existing library function.");
		return llvm::getOrInsertLibFunc(M, TLI, TheLibFunc, RetTy, Arg0Ty,  Arg1Ty);
	}, py::return_value_policy::reference);

}

}
