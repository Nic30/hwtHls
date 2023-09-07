#include "targets/intrinsic/bitrange.h"
#include <llvm/ADT/StringExtras.h>

using namespace llvm;

namespace hwtHls {
/// taken from private functions in <llvm/IR/Function.cpp>
/// Returns a stable mangling for the type specified for use in the name
/// mangling scheme used by 'any' types in intrinsic signatures.  The mangling
/// of named types is simply their name.  Manglings for unnamed types consist
/// of a prefix ('p' for pointers, 'a' for arrays, 'f_' for functions)
/// combined with the mangling of their component types.  A vararg function
/// type will have a suffix of 'vararg'.  Since function types can contain
/// other function types, we close a function type mangling with suffix 'f'
/// which can't be confused with it's prefix.  This ensures we don't have
/// collisions between two unrelated function types. Otherwise, you might
/// parse ffXX as f(fXX) or f(fX)X.  (X is a placeholder for any other type.)
///
std::string getMangledTypeStr(Type *Ty) {
	std::string Result;
	if (PointerType *PTyp = dyn_cast<PointerType>(Ty)) {
		Result += "p" + utostr(PTyp->getAddressSpace());
	} else if (ArrayType *ATyp = dyn_cast<ArrayType>(Ty)) {
		Result += "a" + utostr(ATyp->getNumElements())
				+ getMangledTypeStr(ATyp->getElementType());
	} else if (StructType *STyp = dyn_cast<StructType>(Ty)) {
		if (!STyp->isLiteral()) {
			Result += "s_";
			Result += STyp->getName();
		} else {
			Result += "sl_";
			for (auto Elem : STyp->elements())
				Result += getMangledTypeStr(Elem);
		}
		// Ensure nested structs are distinguishable.
		Result += "s";
	} else if (FunctionType *FT = dyn_cast<FunctionType>(Ty)) {
		Result += "f_" + getMangledTypeStr(FT->getReturnType());
		for (size_t i = 0; i < FT->getNumParams(); i++)
			Result += getMangledTypeStr(FT->getParamType(i));
		if (FT->isVarArg())
			Result += "vararg";
		// Ensure nested function types are distinguishable.
		Result += "f";
	} else if (VectorType *VTy = dyn_cast<VectorType>(Ty)) {
		ElementCount EC = VTy->getElementCount();
		if (EC.isScalable())
			Result += "nx";
		Result += "v" + utostr(EC.getKnownMinValue())
				+ getMangledTypeStr(VTy->getElementType());
	} else if (Ty) {
		switch (Ty->getTypeID()) {
		default:
			llvm_unreachable("Unhandled type");
		case Type::VoidTyID:
			Result += "isVoid";
			break;
		case Type::MetadataTyID:
			Result += "Metadata";
			break;
		case Type::HalfTyID:
			Result += "f16";
			break;
		case Type::BFloatTyID:
			Result += "bf16";
			break;
		case Type::FloatTyID:
			Result += "f32";
			break;
		case Type::DoubleTyID:
			Result += "f64";
			break;
		case Type::X86_FP80TyID:
			Result += "f80";
			break;
		case Type::FP128TyID:
			Result += "f128";
			break;
		case Type::PPC_FP128TyID:
			Result += "ppcf128";
			break;
		case Type::X86_MMXTyID:
			Result += "x86mmx";
			break;
		case Type::X86_AMXTyID:
			Result += "x86amx";
			break;
		case Type::IntegerTyID:
			Result += "i" + utostr(cast<IntegerType>(Ty)->getBitWidth());
			break;
		}
	}
	return Result;
}

std::string Intrinsic_getName(const std::string &baseName,
		ArrayRef<Type*> Tys) {
	std::string Result = baseName;
	for (Type *Ty : Tys) {
		Result += "." + getMangledTypeStr(Ty);
	}
	return Result;
}

void AddDefaultFunctionAttributes(Function &TheFn) {
	// :note: must be compatible with llvm::wouldInstructionBeTriviallyDead
	//TheFn.addFnAttr(Attribute::ArgMemOnly);
	TheFn.addFnAttr(Attribute::NoFree);
	TheFn.addFnAttr(Attribute::NoUnwind);
	TheFn.addFnAttr(Attribute::WillReturn);
	TheFn.setCallingConv(CallingConv::C);
}

void IRBuilder_setInsertPointBehindPhi(IRBuilder<> &builder, llvm::Instruction *I) {
	builder.SetInsertPoint(I);
	auto insPoint = builder.GetInsertPoint();
	while (dyn_cast<PHINode>(&*insPoint)) {
		++insPoint;
	}
	builder.SetInsertPoint(&*insPoint);
}

}
