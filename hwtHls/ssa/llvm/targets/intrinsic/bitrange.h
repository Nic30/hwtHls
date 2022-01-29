#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

//class BitrangeGetInst: public llvm::CallInst {
//	static const llvm::Intrinsic::ID _ID = llvm::Intrinsic::num_intrinsics + 1;
//public:
//	static inline bool classof(const llvm::IntrinsicInst *I) {
//		return I->getIntrinsicID() == _ID;
//	}
//
//	static inline bool classof(const Value *V) {
//		std::cout << "################## classof called" << std::endl;
//
//		return llvm::isa<llvm::IntrinsicInst>(V)
//				&& classof(llvm::cast<llvm::IntrinsicInst>(V));
//	}
//	bool isCommutative() const {
//		return false;
//	}
//	bool mayWriteToMemory() const {
//		return false;
//	}
//	bool mayReadFromMemory() const {
//		return true;
//	}
//	bool mayHaveSideEffects() const {
//		return false;
//	}
//	bool isSafeToRemove() const {
//		return true;
//	}
//	bool isIdenticalTo(const Instruction *I) const {
//		std::cout << "################## called" << std::endl;
//		if (const BitrangeGetInst *BG = llvm::dyn_cast<BitrangeGetInst>(I)) {
//			auto OtherArgs = BG->arg_begin();
//			for (const llvm::Use &U : args()) {
//				const llvm::Use &OtherU = *OtherArgs;
//				if (U.get() != OtherU.get())
//					return false;
//				++OtherArgs;
//			}
//			return true;
//		}
//		return false;
//	}
//
//};
//
//class BitrangeSetInst: public llvm::CallInst {
//	static const llvm::Intrinsic::ID _ID = llvm::Intrinsic::num_intrinsics + 2;
//public:
//	static inline bool classof(const llvm::IntrinsicInst *I) {
//		return I->getIntrinsicID() == _ID;
//	}
//
//	static inline bool classof(const Value *V) {
//		return llvm::isa<llvm::IntrinsicInst>(V)
//				&& classof(llvm::cast<llvm::IntrinsicInst>(V));
//	}
//	bool isCommutative() const {
//		return false;
//	}
//	bool mayReadFromMemory() const {
//		return false;
//	}
//
//	bool mayWriteToMemory() const {
//		return true;
//	}
//};
extern const std::string BitRangeGetName;
llvm::CallInst* CreateBitRangeGet(llvm::IRBuilder<> *Builder,
		llvm::Value *bitVec, llvm::Value *lowBitNo, size_t bitWidth);

extern const std::string BitConcatName;
llvm::CallInst* CreateBitConcat(llvm::IRBuilder<> *Builder,
		llvm::ArrayRef<llvm::Value*> OpsHighFirst);
