#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/exprCache.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/abcAigToLlvmIr.h>

#include <memory>
// ABC related
#include <aig/aig/aig.h>
#include <base/abc/abc.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>

using namespace llvm;

namespace hwtHls {

AbcAigToLlvmIr::AbcAigToLlvmIr(llvm::Function &F, Abc_Ntk_t *net, IoMap &ioMap_,
							   llvm::BasicBlock &entryBB,
							   llvm::DominatorTree &DT) :
	F(F),
	net_(net),
	entryBB_(entryBB),
	DT_(DT),
	Builder(entryBB.getContext()),
	ioMap(ioMap_),
	exprCache(F),
	tmpBB(nullptr),
	change(false) {
	if (net_ == nullptr) {
		throw std::invalid_argument("AbcAigToLlvmIr: net must not be null");
	}
}

llvm::Value *AbcAigToLlvmIr::getInputValue(Abc_Obj_t *object) const {
	const std::string name = Abc_ObjName(object);

	auto it = ioMap.find(name);
	if (it == ioMap.end()) {
		throw std::runtime_error(
			"No LLVM value was supplied for ABC primary input: " + name);
	}

	llvm::Value *value = it->second;

	if (value == nullptr) {
		throw std::runtime_error("LLVM value for ABC primary input is null: " +
								 name);
	}

	if (!value->getType()->isIntegerTy(1)) {
		throw std::runtime_error(
			"ABC primary input must map to an LLVM i1 value: " + name);
	}

	return value;
}

std::tuple<bool, AbcAigToLlvmIr::RecognizedOps, SmallVector<Value *, 8>>
AbcAigToLlvmIr::_popNegationFromRecognizedOp(
	std::shared_ptr<AbcPatternRecognizer::RecognizedOpResult> res) {
	bool negated = false;
	// pop NOTs from expression
	while (res->op == RecognizedOps::NOT &&
		   res->operands[0]->op != RecognizedOps::NOP) {
		negated = !negated;
		res = res->operands[0];
	}
	SmallVector<Value *, 8> ops;
	for (auto &o : res->operands) {
		assert(o->op == RecognizedOps::NOP);
		assert(o->val);
		ops.push_back(o->val);
	}
	return {negated, res->op, ops};
}

llvm::Value *AbcAigToLlvmIr::_translate(Abc_Obj_t *o, bool negated) {
	assert(!Abc_ObjIsComplement(o));

	AbcCacheKey key{o, negated};
	auto it = translationCache.find(key);
	if (it != translationCache.end()) {
		return it->second;
	}

	llvm::Value *res = nullptr;

	if (Abc_ObjIsPi(o)) {
		res = ioMap.at(Abc_ObjName(o));
		if (negated) {
			assert(isa<Instruction>(res));
			res = Builder.CreateNot(res);
		}
	} else if (Abc_ObjIsPo(o)) {
		// "Should be processed in translate()"
		llvm_unreachable("PO should be processed in translate()");
	} else if (o->Type == Abc_ObjType_t::ABC_OBJ_CONST1) {
		// constant 1, possibly negated
		bool val = !negated;
		res = val ? Builder.getTrue() : Builder.getFalse();
	} else {
		// Try to recognize non-AIG operator patterns
		auto maybe = _recognizeNonAigOperator(o, negated);
		if (maybe && maybe->op != RecognizedOps::NOP) {
			const auto &[negated, op, ops] =
				_popNegationFromRecognizedOp(maybe);

			switch (op) {
			case RecognizedOps::OR:
				res = Builder.CreateOr(ops);
				break;
			case RecognizedOps::AND:
				res = Builder.CreateAnd(ops);
				break;
			case RecognizedOps::XOR: {
				assert(!ops.empty());
				Value *res = ops[0];
				for (unsigned i = 1; i < ops.size(); i++)
					res = Builder.CreateXor(res, ops[i]);
				break;
			}
			case RecognizedOps::TERNARY:
				res = buildTernaryMuxChain(ops);
				break;
			default:
				llvm_unreachable("AbcAigToLlvmIr: Unknown RecognizedOps value");
			}

			if (negated) {
				res = Builder.CreateNot(res);
			}
		} else {
			// Default AIG to LLVM IR conversion:
			// AIG node: o = (~c0 ? o0 : 1) & (~c1 ? o1 : 1)
			// where FaninC0/C1 indicate complemented edges.
			auto o0 = Abc_ObjFanin0(o);
			auto o1 = Abc_ObjFanin1(o);
			bool c0 = Abc_ObjFaninC0(o);
			bool c1 = Abc_ObjFaninC1(o);
			Value *v0 = _translate(o0, c0);
			Value *v1 = _translate(o1, c1);
			res = Builder.CreateAnd(v0, v1);
			if (negated) {
				res = Builder.CreateNot(res);
			}
		}
	}

	translationCache[key] = res;
	return res;
}

llvm::Value *AbcAigToLlvmIr::buildTernaryMuxChain(ArrayRef<llvm::Value *> ops) {
	assert(ops.size() >= 3);
	if (ops.size() == 3) {
		llvm::Value *v0 = ops[0];
		llvm::Value *c = ops[1];
		llvm::Value *v1 = ops[2];
		return Builder.CreateSelect(c, v0, v1);
	}

	// Base mux from last three
	llvm::Value *v0 = ops[ops.size() - 3];
	llvm::Value *c = ops[ops.size() - 2];
	llvm::Value *v1 = ops[ops.size() - 1];
	llvm::Value *res = Builder.CreateSelect(c, v0, v1);

	assert((ops.size() - 3) % 2 == 0);
	// Prepend mux for every (v, c) pair from the prefix
	std::size_t prefixLen = ops.size() - 3;
	for (std::size_t i = 0; i < prefixLen; i += 2) {
		llvm::Value *v = ops[i];
		llvm::Value *cc = ops[i + 1];
		// cc ? v : res
		res = Builder.CreateSelect(cc, v, res);
	}
	return res;
}

llvm::Value *AbcAigToLlvmIr::placeOperandIntoFunction(Value *Op,
													  Instruction *UserIP) {
	auto *I = dyn_cast<Instruction>(Op);
	if (!I)
		return Op; // constants and alike do not need any dominance or CSE check

	if (I->getParent() != tmpBB) {
		assert(DT_.dominates(I, UserIP));
		// the operand is new instruction which was already placed on
		// suitable place
		return Op;
	}

	SmallVector<Value *, 3> newOperands;
	for (auto O : I->operand_values()) {
		auto newO = placeOperandIntoFunction(O, UserIP);
		newOperands.push_back(newO);
	}

	ExprCache::InstrEquivalenceKey Key(*I, exprCache);
	auto Existing = exprCache.InstrEqClasses.find(Key);
	if (Existing != exprCache.InstrEqClasses.end()) {
		// if there is already existing instruction which is equivalent to this
		// use it instead
		for (auto I1 : *Existing->second) {
			if (DT_.dominates(I1, UserIP)) {
				// because equivalent may exist but exactly this instruction was
				// have not been cached yet.
				exprCache.EquivalenceClasses[I] = Existing->second;
				I = I1;
				break;
			}
		}
	}

	// because the operands must dominate UserIP
	// it means that some block defining last operand must be dominated
	// by all other
	// * because new instructions should be only BinaryOperator/SelectInst
	//   after constant propagation, there is always at least 1 operand which is
	//   instruction
	Instruction *EarliestIP = nullptr;
	for (auto *O : newOperands) {
		if (auto *OI = dyn_cast<Instruction>(O)) {
			assert(OI->getParent() && OI->getParent() != tmpBB &&
				   "The operand must be already placed");
			if (EarliestIP) {
				// select earliest insertion point where all operands are defined
				if (OI->getParent() == EarliestIP->getParent()) {
					if (EarliestIP->comesBefore(OI->getNextNode())) {
						EarliestIP = OI->getNextNode();
					}
				} else if (DT_.dominates(OI, EarliestIP)) {
				} else if (DT_.dominates(EarliestIP, OI)) {
					EarliestIP = OI->getNextNode();
				} else {
					llvm_unreachable(
						"Because all primary inputs dominate user it must be "
						"the case that one operand dominates other");
				}
			} else {
				EarliestIP = OI->getNextNode();
			}
		}
	}
	if (isa<PHINode>(EarliestIP)) {
		EarliestIP = &*EarliestIP->getParent()->getFirstInsertionPt();
	}
	{
		// if insertion point is inside of bit vector slices after value, jump over this list
		Value* bitVec = nullptr;
		Value* bitVec0;
		if (EarliestIP->getPrevNode() && isAnyFormOfBitRangeGet(EarliestIP, bitVec) && (
			bitVec == EarliestIP->getPrevNode() || 
			(isAnyFormOfBitRangeGet(EarliestIP->getPrevNode(), bitVec0) && bitVec0 == bitVec))) {
			// IP is the first or later bit vector slice in list
			while (isAnyFormOfBitRangeGet(EarliestIP, bitVec0) && bitVec0 == bitVec) {
				EarliestIP = EarliestIP->getNextNode();
			}
		}
	}
	assert(DT_.dominates(EarliestIP, UserIP));
	I->moveBefore(EarliestIP->getIterator());
	{
		unsigned Oi = 0;
		for (auto *O : newOperands) {
			if (I->getOperand(Oi) != O) {
				change = true;
				I->setOperand(Oi, O);
			}

			Oi++;
		}
	}
	if (Existing != exprCache.InstrEqClasses.end()) {
		Existing->second->push_back(I);
		// because equivalent may exist but exactly this instruction
		// was have not been cached yet.
		exprCache.EquivalenceClasses[I] = Existing->second;
	} else {
		auto NewClass =
			std::make_shared<ExprCache::InstructionEquivalenceClass>();
		NewClass->push_back(I);
		exprCache.EquivalenceClasses[I] = NewClass;
		exprCache.InstrEqClasses.emplace(std::move(Key), std::move(NewClass));
	}
	return I;
}

bool AbcAigToLlvmIr::translate() {
	exprCache.init();
	{
		unsigned bbI = 0;
		for (auto BB : exprCache.RPO) {
			blockIndex[BB] = bbI;
			bbI++;
		}
	}

	SmallVector<std::pair<Instruction *, Value *>> replacements;
	tmpBB = BasicBlock::Create(F.getContext(), "bb.AbcAigToLlvmIr.tmp", &F);
	Builder.SetInsertPoint(tmpBB);
	{
		// construct all new expressions in tmp block
		// (which will temporarily violate def-before-use)
		int outputIndex;
		Abc_Obj_t *output;
		Abc_NtkForEachPo(net_, output, outputIndex) {
			if (output == nullptr) {
				continue;
			}

			Abc_Obj_t *fanin = Abc_ObjFanin0(output);
			const bool negated = Abc_ObjFaninC0(output);
			llvm::Value *value = _translate(fanin, negated);

			const std::string name = Abc_ObjName(output);
			replacements.push_back({ioMap[name], value});
		}
	}
	// accommodate newly created instructions into original code,
	// use exprCache to reuse existing expression if possible.

	// sort the earliest first
	sort(replacements, [this](std::pair<Instruction *, Value *> &repl0,
							  std::pair<Instruction *, Value *> &repl1) {
		return blockIndex[repl0.first->getParent()] <
			   blockIndex[repl1.first->getParent()];
	});
	for (const auto &[origI, _newV] : replacements) {
		if (origI == _newV)
			continue;
		Value *newV = _newV;
		newV = placeOperandIntoFunction(newV, origI->getNextNode());
		if (origI == newV)
			continue;
		if (isa<Instruction>(newV) && !newV->hasName()) {
			newV->takeName(origI);
		}
		origI->replaceAllUsesWith(newV);
		change = true;
	}
	for (auto& I: make_early_inc_range(reverse(*tmpBB))) {
		assert(I.use_empty());
		I.eraseFromParent();
	}
	tmpBB->eraseFromParent();
	tmpBB = nullptr;

	return change;
}

}
