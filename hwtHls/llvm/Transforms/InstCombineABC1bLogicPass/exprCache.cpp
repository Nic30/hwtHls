#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/exprCache.h>

#include <llvm/ADT/DenseMap.h>
#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Operator.h>
#include <llvm/Support/ErrorHandling.h>

#include <algorithm>
#include <memory>
#include <unordered_set>

using namespace llvm;

namespace hwtHls {

bool ExprCache::InstrEquivalenceKey::operator==(
	const ExprCache::InstrEquivalenceKey &RHS) const {
	auto &LHS = *this;
	if (LHS.Hash != RHS.Hash)
		return false;

	const Instruction &LI = LHS.I;
	const Instruction &RI = RHS.I;
	if (LI.getRawSubclassOptionalData() != RI.getRawSubclassOptionalData())
		return false;

	if (LI.getOpcode() != RI.getOpcode())
		return false;

	if (LI.getType() != RI.getType())
		return false;

	if (LHS.ops.size() != RHS.ops.size())
		return false;

	return std::equal(LHS.ops.begin(), LHS.ops.end(), RHS.ops.begin());
}

ExprCache::InstrEquivalenceKey::InstrEquivalenceKey(Instruction &I,
													ExprCache &cache) :
	I(I) {
	for (Value *Op : I.operands()) {
		Value *OpRepr = cache.getRepresentativeOperand(Op);
		ops.push_back(OpRepr);
	}
	if (const auto *BO = dyn_cast<BinaryOperator>(&I);
		BO && BO->isCommutative()) {
		sort(ops);
	}
	Hash = computeHash();
}

ExprCache::InstrEquivalenceKey::InstrEquivalenceKey(
	Instruction &I, llvm::SmallVector<llvm::Value *, 3> &ops) :
	I(I), ops(ops) {
	Hash = computeHash();
}

llvm::hash_code ExprCache::InstrEquivalenceKey::computeHash() const {
	hash_code H = hash_combine(hash_value(I.getOpcode()),
							   hash_value(I.getRawSubclassOptionalData()));
	for (Value *Op : ops) {
		H = hash_combine(H, hash_value(Op));
	}
	return H;
}

ExprCache::ExprCache(llvm::Function &F) :
	F(F), RPO(&F) {}

std::vector<Instruction *>
ExprCache::getCachedInstructionsInTopologicalOrder() {
	std::vector<Instruction *> Ordered;
	std::unordered_set<Instruction *> Visited;

	for (BasicBlock *BB : RPO) {
		for (Instruction &I : *BB) {
			if (!isCachedInstruction(I))
				continue;

			for (Value *Op : I.operands()) {
				if (!Op)
					llvm_unreachable("Instruction has a null operand");

				if (auto *OpI = dyn_cast<Instruction>(Op)) {
					if (!isCachedInstruction(*OpI))
						continue;

					if (!Visited.contains(OpI))
						llvm_unreachable(
							"Instruction operand was not visited before its "
							"user; input is not valid SSA");
				}
			}

			Visited.insert(&I);
			Ordered.push_back(&I);
		}
	}

	return Ordered;
}

Value *ExprCache::getRepresentativeOperand(Value *Op) {
	assert(Op);

	if (auto *OpI = dyn_cast<Instruction>(Op)) {
		if (isCachedInstruction(*OpI)) {
			auto It = EquivalenceClasses.find(OpI);
			if (It == EquivalenceClasses.end())
				llvm_unreachable(
					"Equivalence instruction operand processed before "
					"its equivalence class was created");

			auto Class = It->second;
			assert(Class);
			assert(!Class->empty());
			Instruction *Representative = Class->front();
			assert(Representative);
			return Representative;
		}
	}

	return Op;
}

void ExprCache::init() {
	auto Ordered = getCachedInstructionsInTopologicalOrder();
	for (Instruction *I : Ordered) {
		InstrEquivalenceKey Key(*I, *this);

		auto Existing = InstrEqClasses.find(Key);

		if (Existing != InstrEqClasses.end()) {
			auto Class = Existing->second;

			if (Class->empty())
				llvm_unreachable("Existing equivalence class is empty");

			Class->push_back(I);
			EquivalenceClasses[I] = Class;
		} else {
			auto NewClass = std::make_shared<InstructionEquivalenceClass>();
			NewClass->push_back(I);
			EquivalenceClasses[I] = NewClass;
			InstrEqClasses.emplace(std::move(Key), std::move(NewClass));
		}
	}
}

}