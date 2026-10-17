#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/abcAigToLlvmIr.h>
#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/exprCache.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#include <memory>
// #include <unordered_set>
// ABC related
#include <aig/aig/aig.h>
#include <base/abc/abc.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;

// #define AbcAigToLlvmIr_TRACE

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
	assert(res);
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
bool definedBefore(llvm::DominatorTree &DT, Instruction *I0, Instruction *I1) {
	return DT.dominates(I0, I1) ||
		   (I0->getParent() == I1->getParent() && I0->comesBefore(I1));
}
bool definedBeforeOrEqual(llvm::DominatorTree &DT, Instruction *I0,
						  Instruction *I1) {
	return I0 == I1 || definedBefore(DT, I0, I1);
}
llvm::Value *AbcAigToLlvmIr::placeOperandIntoFunction(Value *Op,
													  Instruction *User) {
	auto *I = dyn_cast<Instruction>(Op);
	if (!I)
		return Op; // constants and alike do not need any dominance or CSE check
#ifdef AbcAigToLlvmIr_TRACE
	dbgs() << "Op: " << Op << " " << *Op << "\n";
	dbgs() << "UserIP: " << User << " " << *User << "\n";
#endif
	assert(User->getParent() != tmpBB);

	if (I->getParent() != tmpBB) {
		if (!definedBeforeOrEqual(DT_, I, User)) {
			errs() << "I: " << I << " " << *I << "\n";
			errs() << "UserIP: " << User << " " << *User << "\n";
			llvm_unreachable("Broken dominance of already placed instruction");
		}
		// the operand is new instruction which was already placed on
		// suitable place
		return Op;
	}

	SmallVector<Value *, 3> newOperands;
	for (auto O : I->operand_values()) {
		auto newO = placeOperandIntoFunction(O, User);
		newOperands.push_back(newO);
	}

	ExprCache::InstrEquivalenceKey Key(*I, exprCache);
	auto Existing = exprCache.InstrEqClasses.find(Key);
	if (Existing != exprCache.InstrEqClasses.end()) {
		// if there is already existing instruction which is equivalent to this
		// use it instead
		for (auto _I1 = Existing->second->begin();
			 _I1 != Existing->second->end(); ++_I1) {
			Instruction *I1 = *_I1;
			// find existing instance which is available for User
			if (definedBefore(DT_, I1, User)) {
				if (!is_contained(*Existing->second, I)) {
					// because equivalent may exist but exactly this instruction
					// was have not been cached yet.
					exprCache.EquivalenceClasses[I] = Existing->second;
				}
				// select most top equvalent of I
				for (auto *I2 : make_range(++_I1, Existing->second->end())) {
					if (definedBefore(DT_, I2, I1)) {
						I1 = I2;
					}
				}
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
	Instruction *LatestDef = nullptr;
	for (auto *O : newOperands) {
		if (auto *OI = dyn_cast<Instruction>(O)) {
			assert(OI->getParent() && OI->getParent() != tmpBB &&
				   "The operand must be already placed");
			if (LatestDef) {
				// select earliest insertion point where all operands are
				// defined
				if (definedBeforeOrEqual(DT_, LatestDef, OI)) {
					LatestDef = OI;
				} else if (definedBefore(DT_, OI, LatestDef)) {
				} else {
					llvm_unreachable(
						"Because all primary inputs dominate user it must be "
						"the case that one operand dominates other");
				}
			} else {
				LatestDef = OI;
			}
		}
	}
	if (isa<PHINode>(LatestDef->getNextNode())) {
		LatestDef =
			&*LatestDef->getParent()->getFirstInsertionPt()->getPrevNode();
	}
	{
		// if insertion point is inside of bit vector slices after value, jump
		// over this list
		Value *bitVec = nullptr;
		Value *bitVec0;
		if (isAnyFormOfBitRangeGet(LatestDef->getNextNode(), bitVec) &&
			(bitVec == LatestDef ||
			 (isAnyFormOfBitRangeGet(LatestDef, bitVec0) &&
			  bitVec0 == bitVec))) {
			// IP is the first or later bit vector slice in list
			while (isAnyFormOfBitRangeGet(LatestDef->getNextNode(), bitVec0) &&
				   bitVec0 == bitVec) {
				LatestDef = LatestDef->getNextNode();
			}
		}
	}
	assert(definedBefore(DT_, LatestDef, User));
	assert(I != LatestDef);
#ifdef AbcAigToLlvmIr_TRACE
	dbgs() << "moveAfter: " << I << "" << *I << " " << LatestDef << " "
		   << *LatestDef << "\n";
#endif
	assert(LatestDef->getParent() != tmpBB);
	if (I->getParent() == tmpBB)
		I->moveBefore(LatestDef->getNextNode()->getIterator());
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
///// Sort \p Worklist topologically by data dependence.
/////
///// Primary inputs are already-placed operand instructions. They initialize
///the
///// ready list and release dependent worklist instructions, but are not part
///of
///// the sorted output.
// std::vector<Instruction *> topologicalSortForDanglingInstructions(
//	ArrayRef<Instruction *> instructions,
//	const DenseMap<BasicBlock *, unsigned> &BlockIndex) {
//	if (instructions.size() < 2)
//		return instructions;
//
//	// Remaining worklist dependencies for each worklist instruction.
//	std::unordered_map<Instruction *, unsigned> PendingDepsCnt;
//	PendingDepsCnt.reserve(2 * instructions.size());
//
//	// Primary inputs are placed operands outside the worklist.
//	SetVector<Instruction *> PrimaryInputs;
//	std::unordered_set<Instruction *> allInstrucitons(instructions.begin(),
//													  instructions.end());
//	for (Instruction *I : instructions) {
//		assert(I && "null instruction");
//		assert((isa<BinaryOperator>(I) ||
//				isa<SelectInst>(I)) &&
//			   "unsupported instruction type");
//
//		unsigned depCnt = 0;
//		for (Value *Op : I->operand_values()) {
//			auto *OpInst = dyn_cast<Instruction>(Op);
//			if (!OpInst)
//				continue;
//
//			assert(OpInst != I && "instruction depends on itself");
//			++depCnt;
//			if (!allInstrucitons.contains(OpInst)) {
//				PrimaryInputs.insert(OpInst);
//			}
//		}
//		PendingDepsCnt[I] = depCnt;
//	}
//	// most early at last position, because Ready is processed from the end
//	std::vector<Instruction *> readyVec;
//	readyVec.reserve(PrimaryInputs.size());
//	readyVec.insert_range(readyVec.begin(), PrimaryInputs);
//	llvm::sort(readyVec, [&](Instruction *A, Instruction *B) -> bool {
//		auto BlockA = BlockIndex.find(A->getParent());
//		auto BlockB = BlockIndex.find(B->getParent());
//		assert(BlockA != BlockIndex.end() && "missing block index for input");
//		assert(BlockB != BlockIndex.end() && "missing block index for input");
//
//		if (BlockA->second != BlockB->second)
//			return BlockA->second >= BlockB->second;
//
//		assert(A->getParent() == B->getParent() &&
//			   "comesBefore requires instructions in the same block");
//		return B->comesBefore(A);
//	});
//
//	// Kahn's algorithm. Primary inputs seed the queue, but are not emitted.
//	SetVector<Instruction*> Ready;
//	Ready.insert_range(readyVec);
//	std::vector<Instruction *> Sorted;
//	Sorted.reserve(instructions.size());
//
//	while (!Ready.empty()) {
//		Instruction *Cur = Ready.pop_back_val();
//		// Primary inputs are processed but not emitted.
//		if (allInstrucitons.contains(Cur))
//			Sorted.push_back(Cur);
//
//		// Release worklist users directly through the def-use chain.
//		for (User *U : Cur->users()) {
//			auto *UserInst = dyn_cast<Instruction>(U);
//			if (!UserInst || !allInstrucitons.contains(UserInst))
//				continue;
//
//			auto &Cnt = PendingDepsCnt[UserInst];
//			assert(Cnt > 0 && "inconsistent pending dependency count");
//
//			if (--Cnt == 0)
//				Ready.insert(UserInst);
//		}
//	}
//
//	// A cycle prevents some worklist instructions from becoming ready.
//	if (Sorted.size() != instructions.size())
//		llvm_unreachable("data-dependence cycle in instruction list");
//	return Sorted;
// }

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
		// :note: it is required to construct instruction from outputs to inputs
		// because
		//        we want to recognize the largest operand in AIG.

		// Vec_Ptr_t * vNodes = Abc_NtkDfs(net_, /*fCollectAll*/0); //
		// fCollectAll collects also dangling nodes Abc_Obj_t * pObj; int i;
		// Vec_PtrForEachEntry(Abc_Obj_t *, vNodes, pObj, i) {
		//     // pObj is visited after all of its fanins
		//     // Do your per-node work here.
		// }
		//
		// Vec_PtrFree(vNodes);

		int outputIndex;
		Abc_Obj_t *output;
		Abc_NtkForEachPo(net_, output, outputIndex) {
			if (output == nullptr) {
				continue;
			}

			Abc_Obj_t *fanin = Abc_ObjFanin0(output);
			const bool negated = Abc_ObjFaninC0(output);
			Value *value = _translate(fanin, negated);

			const std::string name = Abc_ObjName(output);
			auto outI = dyn_cast<Instruction>(ioMap[name]);
			assert(outI);
			replacements.push_back({outI, value});
		}
	}
	// accommodate newly created instructions into original code,
	// use exprCache to reuse existing expression if possible.

	// sort the earliest first
	sort(replacements, [this](std::pair<Instruction *, Value *> &repl0,
							  std::pair<Instruction *, Value *> &repl1) {
		auto BBi0 = blockIndex[repl0.first->getParent()];
		auto BBi1 = blockIndex[repl1.first->getParent()];
		if (BBi0 == BBi1) {
			return repl0.first->comesBefore(repl1.first);
		} else {
			return BBi0 < BBi1;
		}
	});

	for (const auto &[origI, _newV] : replacements) {
		if (origI == _newV)
			continue;
#ifdef AbcAigToLlvmIr_TRACE
		dbgs() << "Processing " << origI << " " << *origI << "\n";
#endif
		Value *newV = _newV;
		newV = placeOperandIntoFunction(newV, origI);
		if (origI == newV)
			continue;
		if (isa<Instruction>(newV) && !newV->hasName()) {
			newV->takeName(origI);
		}
		origI->replaceAllUsesWith(newV);
		change = true;
	}
	for (auto &I : make_early_inc_range(reverse(*tmpBB))) {
		assert(I.use_empty());
		I.eraseFromParent();
	}
	tmpBB->eraseFromParent();
	tmpBB = nullptr;
	return change;
}

}
