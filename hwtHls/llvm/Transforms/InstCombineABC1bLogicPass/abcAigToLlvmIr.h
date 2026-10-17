#pragma once
#include <string>
#include <unordered_map>

#include <llvm/ADT/ArrayRef.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Value.h>

// ABC includes
#include <aig/aig/aig.h>
#include <base/abc/abc.h>

#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/exprCache.h>
#include <hwtHls/netlist/abc/patternRecognize.h>

namespace hwtHls {

class AbcAigToLlvmIr : public AbcPatternRecognizer<llvm::Value *> {
public:
	using IoMap = std::unordered_map<std::string, llvm::Value *>;
	AbcAigToLlvmIr(llvm::Function &F, Abc_Ntk_t *net, IoMap &ioMap,
				   llvm::BasicBlock &entryBB, llvm::DominatorTree &DT);

	/*
	 * Translate every primary output in the ABC network.
	 *
	 * :note: The translated values will replace original outputs provided in ioMap.
	 */
	bool translate();

protected:
	struct AbcCacheKey {
		Abc_Obj_t *object;
		bool negated;

		bool operator==(const AbcCacheKey &other) const {
			return object == other.object && negated == other.negated;
		}
	};

	struct AbcCacheKeyHasher {
		std::size_t operator()(const AbcCacheKey &key) const noexcept {
			const auto objectBits =
				reinterpret_cast<std::uintptr_t>(key.object);

			return std::hash<std::uintptr_t>{}(objectBits) ^
				   (std::hash<bool>{}(key.negated) << 1);
		}
	};

	llvm::Function &F;
	Abc_Ntk_t *net_;
	llvm::BasicBlock &entryBB_;
	llvm::DominatorTree &DT_;
	llvm::IRBuilder<> Builder;
	// :note: name of port must be used because everything else will change
	IoMap ioMap;
	// to minimize duplication of common subexpression when placing new
	// instruction to Functino
	ExprCache exprCache;
	llvm::DenseMap<llvm::BasicBlock *, unsigned> blockIndex;
	// for mapping ABC<->llvm IR
	std::unordered_map<AbcCacheKey, llvm::Value *, AbcCacheKeyHasher>
		translationCache;
	// block used to construct temporary instructions before final placing into
	// Function original BBs
	llvm::BasicBlock *tmpBB;
	bool change;

	llvm::Value *placeOperandIntoFunction(llvm::Value *op,
										  llvm::Instruction *user);

	std::tuple<bool, RecognizedOps, llvm::SmallVector<llvm::Value *, 8>>
	_popNegationFromRecognizedOp(
		std::shared_ptr<AbcPatternRecognizer::RecognizedOpResult> res);
	virtual llvm::Value *_translate(Abc_Obj_t *o, bool negated) override;
	llvm::Value *getInputValue(Abc_Obj_t *object) const;
	llvm::Value *buildTernaryMuxChain(llvm::ArrayRef<llvm::Value *> ops);
};

} // namespace hwtHls