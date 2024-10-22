#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace hwtHls {

/*
 * Intrinsic function for conversion to HFloatTmp which is just double in LLVM but this instruction
 * CastToHFloatTmp/CastFromHFloatTmp holds the info about type specialization for later lowering.
 * (The HFloatTmp exists because LLVM does support just some floating type variants and this is to allow any floating type.
 *  :see: llvm::Type::TypeID)
 *
 * */
struct HFloatTmpConfig {
	std::uint8_t exponentOrIntWidth;
	std::uint8_t mantissaOrFracWidth;
	bool isInQFromat;
	bool supportSubnormal;
	bool hasSign;
	bool hasIsNaN;
	bool hasIsInf;
	bool hasIs1;
	bool hasIs0;

	static constexpr size_t MEMBER_CNT = 9;
	bool operator==(const HFloatTmpConfig &other) const;
	size_t getBitWidth() const {
		return exponentOrIntWidth + mantissaOrFracWidth + hasSign + hasIsNaN
				+ hasIsInf + hasIs1 + hasIs0;
	}
	size_t __hash__() const;
	static HFloatTmpConfig fromCallArgs(llvm::CallInst &CI, size_t argsToSkip =
			1);
};

#define __HFloatTmpConfig_PARAMS_WITH_DEFAULT \
	std::uint8_t exponentOrIntWidth, std::uint8_t mantissaOrFracWidth,  \
	bool isInQFromat = false, bool supportSubnormal = true, \
	bool hasSign = true, bool hasIsNaN = false, bool hasIsInf = false,  \
	bool hasIs1 = false, bool hasIs0 = false

extern const std::string CastToHFloatTmpName;
llvm::CallInst* CreateCastToHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, __HFloatTmpConfig_PARAMS_WITH_DEFAULT,
		const llvm::Twine &Name = "");
bool IsCastToHFloatTmp(const llvm::CallInst *C);
bool IsCastToHFloatTmp(const llvm::Function *F);

extern const std::string CastFromHFloatTmpName;
llvm::CallInst* CreateCastFromHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, __HFloatTmpConfig_PARAMS_WITH_DEFAULT,
		const llvm::Twine &Name = "");
bool IsCastFromHFloatTmp(const llvm::CallInst *C);
bool IsCastFromHFloatTmp(const llvm::Function *F);

bool IsCastFromHFloatTmp(const llvm::CallInst *C);
bool IsCastFromHFloatTmp(const llvm::Function *F);
bool IsHwtHlsFp(const llvm::CallInst *C);
bool IsHwtHlsFp(const llvm::Function *F);

// This code was used to generate declarations
// .. code-block::python
//    binOps = ["FAdd", "FSub", "FMul", "FDiv"]
//    template = """\
//    extern const std::string hwtHlsFp{0:s}Name;
//    llvm::CallInst* CreateHwtHlsFp{0:s}( __CreateHwtHlsFpBinOpParams);
//    bool IsHwtHlsFp{0:s}(const llvm::CallInst *C);
//    bool IsHwtHlsFp{0:s}(const llvm::Function *F);
//    """
//    for opName in binOps:
//        print(template.format(opName))

/**
 * Specialized intrinsic functions which are replacing llvm floatingpoint intrinsic and operators
 * after HFloatTmpLoweringPass
 * :note: Thins are not defined using macro to make search in code easier
 * **/
#define __CreateHwtHlsFpBinOpParams llvm::IRBuilder<> *Builder, llvm::Value *op0, llvm::Value *op1,\
	__HFloatTmpConfig_PARAMS_WITH_DEFAULT, const llvm::Twine &Name = ""

extern const std::string hwtHlsFpFAddName;
llvm::CallInst* CreateHwtHlsFpFAdd(__CreateHwtHlsFpBinOpParams);
bool IsHwtHlsFpFAdd(const llvm::CallInst *C);
bool IsHwtHlsFpFAdd(const llvm::Function *F);

extern const std::string hwtHlsFpFSubName;
llvm::CallInst* CreateHwtHlsFpFSub(__CreateHwtHlsFpBinOpParams);
bool IsHwtHlsFpFSub(const llvm::CallInst *C);
bool IsHwtHlsFpFSub(const llvm::Function *F);

extern const std::string hwtHlsFpFMulName;
llvm::CallInst* CreateHwtHlsFpFMul(__CreateHwtHlsFpBinOpParams);
bool IsHwtHlsFpFMul(const llvm::CallInst *C);
bool IsHwtHlsFpFMul(const llvm::Function *F);

extern const std::string hwtHlsFpFDivName;
llvm::CallInst* CreateHwtHlsFpFDiv(__CreateHwtHlsFpBinOpParams);
bool IsHwtHlsFpFDiv(const llvm::CallInst *C);
bool IsHwtHlsFpFDiv(const llvm::Function *F);

extern const std::string hwtHlsFpFRemName;
llvm::CallInst* CreateHwtHlsFpFRem(__CreateHwtHlsFpBinOpParams);
bool IsHwtHlsFpFRem(const llvm::CallInst *C);
bool IsHwtHlsFpFRem(const llvm::Function *F);
}
