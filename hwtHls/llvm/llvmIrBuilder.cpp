#include <hwtHls/llvm/llvmIrBuilder.h>

#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

namespace py = pybind11;

PYBIND11_MAKE_OPAQUE(std::vector<llvm::Value*>);


namespace hwtHls {

void register_IRBuilder(pybind11::module_ & m) {
	py::class_<llvm::IRBuilder<>>(m, "IRBuilder")
		.def(py::init<llvm::LLVMContext&>())
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock *TheBB) {
				return self->SetInsertPoint(TheBB);
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
		.def("CreateNeg", &llvm::IRBuilder<>::CreateNeg, py::return_value_policy::reference)
		.def("CreateAdd", &llvm::IRBuilder<>::CreateAdd, py::return_value_policy::reference)
		.def("CreateSub", &llvm::IRBuilder<>::CreateSub, py::return_value_policy::reference)
		.def("CreateMul", &llvm::IRBuilder<>::CreateMul, py::return_value_policy::reference)
		.def("CreateUDiv", &llvm::IRBuilder<>::CreateUDiv, py::return_value_policy::reference)
		.def("CreateSDiv", &llvm::IRBuilder<>::CreateSDiv, py::return_value_policy::reference)
		.def("CreateLShr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool isExact=false) {
			return self->CreateLShr(LHS, RHS, Name, isExact);
		 })
		.def("CreateShl", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool HasNUW = false, bool HasNSW = false) {
			return self->CreateShl(LHS, RHS, Name, HasNUW, HasNSW);
		})
		.def("CreateRetVoid", &llvm::IRBuilder<>::CreateRetVoid)
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
		.def("CreateZExt", &llvm::IRBuilder<>::CreateZExt, py::return_value_policy::reference)
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
		})
		.def("CreateGEP",  [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *Ptr, std::vector<llvm::Value *>& IdxList) {
			return self->CreateGEP(Ty, Ptr, IdxList, "", true);
		}, py::return_value_policy::reference)
		.def("CreateCall", [](llvm::IRBuilder<> * self, llvm::FunctionCallee Callee,
                std::vector<llvm::Value *> Args, const llvm::Twine &Name = "") {
			return self->CreateCall(Callee, Args, Name);
		}, py::arg("Callee"), py::arg("Args"), py::arg("Name")=llvm::Twine(""));

    	py::bind_vector<std::vector<llvm::Value*>>(m, "VectorValuePtr");
		py::implicitly_convertible<py::list, std::vector<llvm::Value*>>();

}

}
