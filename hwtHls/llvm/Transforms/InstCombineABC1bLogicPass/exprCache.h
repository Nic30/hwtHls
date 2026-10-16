#pragma once

#include <llvm/ADT/Hashing.h>
#include <llvm/ADT/MapVector.h>
#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>

#include <map>
#include <vector>

namespace hwtHls {

class ExprCache {
public:
	/// A class of structurally equivalent BinaryOperator or SelectInst
	/// instructions.
	///
	/// The first instruction in the vector is the stable representative of the
	/// class.
	using InstructionEquivalenceClass = std::vector<llvm::Instruction *>;

	/// A key identifying an instruction equivalence class.
	struct InstrEquivalenceKey {
		llvm::hash_code Hash;
		llvm::Instruction &I;
		llvm::SmallVector<llvm::Value *, 3> ops;
		InstrEquivalenceKey(llvm::Instruction &I, ExprCache &cache);
		InstrEquivalenceKey(llvm::Instruction &I,
							llvm::SmallVector<llvm::Value *, 3> &ops);
		llvm::hash_code computeHash() const;
		// Returns true if two keys describe structurally equivalent
		// expressions, but the RepresentativeInstruction does not have to be
		// the same.
		bool operator==(const InstrEquivalenceKey &RHS) const;
	};

	struct InstrEquivalenceKeyHasher {
		size_t operator()(const InstrEquivalenceKey &Key) const {
			return Key.Hash;
		}
	};

	ExprCache(llvm::Function &F);

	llvm::Value *getRepresentativeOperand(llvm::Value *Op);
	/// Collect cached instructions in an order where operands appear before
	/// users.
	std::vector<llvm::Instruction *> getCachedInstructionsInTopologicalOrder();

	/// Returns true if \p I participates in equivalence-class computation.
	virtual bool isCachedInstruction(const llvm::Instruction &I) {
		return llvm::isa<llvm::BinaryOperator>(I) ||
			   llvm::isa<llvm::SelectInst>(I);
	}
	/// For every instruction in \p Instructions, return its structural
	/// equivalence class.
	void init();
	llvm::Function &F;
	llvm::ReversePostOrderTraversal<llvm::Function *> RPO;
	std::map<llvm::Instruction *, std::shared_ptr<InstructionEquivalenceClass>>
		EquivalenceClasses;

	std::unordered_map<
		InstrEquivalenceKey, std::shared_ptr<InstructionEquivalenceClass>,
		InstrEquivalenceKeyHasher, std::equal_to<InstrEquivalenceKey>>
		InstrEqClasses;
};

}