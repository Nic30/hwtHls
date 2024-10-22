#include <hwtHls/llvm/llvmIrBuilder.h>

#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>


namespace py = pybind11;

PYBIND11_MAKE_OPAQUE(std::vector<llvm::Value*>);


namespace hwtHls {

#define COMMON_BIN_OP_ARGS py::arg("LHS"), py::arg("RHS"), py::arg("Name")= llvm::Twine(""), py::arg("HasNUW")=false, py::arg("HasNSW")=false
#define COMMON_BIN_OP_ARGS_WITH_ISEXACT py::arg("LHS"), py::arg("RHS"), py::arg("Name")= llvm::Twine(""), py::arg("isExact")=false

#define F_OP(opName) \
.def(#opName, [](llvm::IRBuilder<> * self, llvm::Value *L, llvm::Value *R, const llvm::Twine &Name) {\
	return self->opName(L, R, Name);\
}, py::return_value_policy::reference)

#define HFloatTmpConfig_PY_ARGS \
	py::arg("isInQFromat"), py::arg("supportSubnormal"), \
	py::arg("exponentOrIntWidth"), py::arg("mantissaOrFracWidth"), \
	py::arg("hasSign"), py::arg("hasIsNaN"), py::arg("hasIsInf"), py::arg("hasIs1"), py::arg("hasIs0")

void register_IRBuilder(pybind11::module_ & m) {
	py::class_<llvm::IRBuilder<>>(m, "IRBuilder")
		.def(py::init<llvm::LLVMContext&>())
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock *TheBB) {
				return self->SetInsertPoint(TheBB);
			}, py::return_value_policy::reference)
		.def("getContext", &llvm::IRBuilder<>::getContext, py::return_value_policy::reference)
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
		.def("CreateStore", &llvm::IRBuilder<>::CreateStore, py::return_value_policy::reference)
		.def("CreateLoad", [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *Ptr, bool isVolatile,
                const llvm::Twine &Name = "") {
				return self->CreateLoad(Ty, Ptr, isVolatile, Name);
			}, py::return_value_policy::reference)
		.def("CreateStreamRead", [](llvm::IRBuilder<> * self, llvm::Value *ioArgPtr, size_t chunkBitWidth, size_t returnBitWidth,
				const llvm::Twine &Name = "") {
				auto I = CreateStreamRead(self, ioArgPtr, chunkBitWidth, returnBitWidth);
				I->setName(Name);
				return I;
			}, py::return_value_policy::reference)
		.def("CreateStreamReadStartOfFrame", &CreateStreamReadStartOfFrame, py::return_value_policy::reference)
		.def("CreateStreamReadEndOfFrame", &CreateStreamReadEndOfFrame, py::return_value_policy::reference)
		.def("CreateStreamWrite", &CreateStreamWrite, py::return_value_policy::reference)
		.def("CreateStreamWriteStartOfFrame", &CreateStreamWriteStartOfFrame, py::return_value_policy::reference)
		.def("CreateStreamWriteEndOfFrame", &CreateStreamWriteEndOfFrame, py::return_value_policy::reference)
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock * bb) {
			self->SetInsertPoint(bb);
		})
		.def("CreateZExt", &llvm::IRBuilder<>::CreateZExt,
				py::arg("V"), py::arg("DestTy"), py::arg("Name")=llvm::Twine(""), py::arg("IsNonNeg")=false,
				py::return_value_policy::reference)
		.def("CreateSExt", &llvm::IRBuilder<>::CreateSExt, py::return_value_policy::reference)
		.def("CreateSelect", &llvm::IRBuilder<>::CreateSelect, py::return_value_policy::reference)
		.def("CreateTrunc", &llvm::IRBuilder<>::CreateTrunc, py::return_value_policy::reference)
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
		.def("CreateSwitch", &llvm::IRBuilder<>::CreateSwitch, py::return_value_policy::reference)
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
		.def("CreateBitCast", &llvm::IRBuilder<>::CreateBitCast, py::arg("V"), py::arg("DestTy"), py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		.def("CreateCastToHFloatTmp", &CreateCastToHFloatTmp,
				py::arg("srcArg"), HFloatTmpConfig_PY_ARGS,
				py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
		.def("CreateCastFromHFloatTmp", &CreateCastFromHFloatTmp,
				py::arg("srcArg"), HFloatTmpConfig_PY_ARGS,
				py::arg("Name")=llvm::Twine(""), py::return_value_policy::reference)
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

}

}
