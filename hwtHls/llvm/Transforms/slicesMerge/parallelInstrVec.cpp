#include <hwtHls/llvm/Transforms/slicesMerge/parallelInstrVec.h>
#include <llvm/IR/BasicBlock.h>
#include <algorithm>
#include <limits>
#include <set>

using namespace llvm;

namespace hwtHls {

std::pair<std::vector<std::size_t>::iterator, ParallelInstVec::iterator> ParallelInstVec::getInstrAfter(
		Instruction *I) {
	auto IIndex = std::numeric_limits<size_t>::max();
	auto indexOfInstrAfter = std::lower_bound(
			thisOrderedAsInParentBlock.begin(),
			thisOrderedAsInParentBlock.end(), IIndex,
			[I, this, IIndex](size_t _lhs, size_t _rhs) -> bool {
				Instruction *lhs;
				Instruction *rhs;
				if (_lhs == IIndex)
					lhs = I;
				else
					lhs = (*this)[_lhs].I;
				if (_rhs == IIndex)
					rhs = I;
				else
					rhs = (*this)[_rhs].I;

				assert(lhs->getParent() == rhs->getParent());
				return lhs->comesBefore(rhs);
			});
	if (indexOfInstrAfter == thisOrderedAsInParentBlock.end())
		return {indexOfInstrAfter, end()};
	else
		return {indexOfInstrAfter, begin() + *indexOfInstrAfter};
}

ParallelInstVec::iterator ParallelInstVec::insertSorted(Instruction *I,
		bool hasSwappedOperands) {
	if (size() == 0) {
		thisOrderedAsInParentBlock.push_back(0);
	} else if ((*this)[thisOrderedAsInParentBlock.back()].I->comesBefore(I)) {
		// check for most likely the case
		assert(begin()->I->getParent() == I->getParent());
		thisOrderedAsInParentBlock.push_back(size());
	} else {
		assert(begin()->I->getParent() == I->getParent());
		auto instrAfter = getInstrAfter(I);
		thisOrderedAsInParentBlock.insert(instrAfter.first, size());
	}
	push_back( { I, hasSwappedOperands, false });
	return end() - 1;
}

bool ParallelInstVec::canInsert(Instruction *I) {
	// check if none of instructions parallelInstrOnSameVec are used between found instruction and this
	if (empty())
		return true;
	auto instrAfter = getInstrAfter(I);
	std::set<Instruction*> parInstr;
	for (auto &I : *this) {
		parInstr.insert(I.I);
	}
	std::set<Instruction*> dependentOnPredParInstr;
	std::set<Instruction*> dependentOnNewI;
	dependentOnNewI.insert(I);

	Instruction *FirstI = iterInBlockOrder_begin().getInstrIt()->I;
	BasicBlock &BB = *FirstI->getParent();
	bool beforeI = true;
	bool beforeInstructionsChecked = false;
	auto AnyOperandDependsOnInstructions = [](Instruction &I,
			const std::set<Instruction*> &instructions) {
		for (Value *V : I.operand_values()) {
			if (auto *OpI = dyn_cast<Instruction>(V)) {
				if (instructions.find(OpI) != instructions.end()) {
					return true;
				}
			}
		}
		return false;
	};
	for (auto _I = FirstI->getIterator(); _I != BB.end(); ++_I) {
		if (instrAfter.second != end() && &*_I == instrAfter.second->I) {
			// block iterator stepped on instruction which is after this instruction
			beforeI = false;
		}
		if (beforeI) {
			if (AnyOperandDependsOnInstructions(*_I, dependentOnPredParInstr)) {
				dependentOnPredParInstr.insert(&*_I);
			} else if (parInstr.find(&*_I) != parInstr.end()) {
				dependentOnPredParInstr.insert(&*_I);
			}
		} else {
			if (!beforeInstructionsChecked) {
				if (AnyOperandDependsOnInstructions(*I,
						dependentOnPredParInstr))
					return false; // I was found to be dependent on predecessors in vec
				beforeInstructionsChecked = true;
			}

			if (AnyOperandDependsOnInstructions(*_I, dependentOnNewI)) {
				if (parInstr.find(&*_I) != parInstr.end()) {
					// some successor instruction in vec was found to be dependent on I
					return false;
				} else {
					dependentOnNewI.insert(&*_I);
				}
			}
		}
	}
	if (!beforeInstructionsChecked) {
		// this may happen when I is after instructions in vec
		if (AnyOperandDependsOnInstructions(*I, dependentOnPredParInstr))
			return false;
	}
	return true;
}

const llvm::Instruction* ParallelInstVec::getInstructionClosesToBlockEnd() const {
	if (empty())
		return nullptr;
	else
		return (*this)[thisOrderedAsInParentBlock.back()].I;
}

ParallelInstVecInBlockOrderIterator ParallelInstVec::iterInBlockOrder_begin() {
	return ParallelInstVecInBlockOrderIterator(*this);
}
ParallelInstVecInBlockOrderIterator ParallelInstVec::iterInBlockOrder_end() {
	return ParallelInstVecInBlockOrderIterator(*this,
			thisOrderedAsInParentBlock.end());
}
llvm::iterator_range<ParallelInstVecInBlockOrderIterator> ParallelInstVec::iterInBlockOrder() {
	return llvm::make_range(iterInBlockOrder_begin(), iterInBlockOrder_end());
}
ParallelInstVecUniqueIterator ParallelInstVec::iterUnique_begin() {
	ParallelInstVecUniqueIterator it(*this, begin());
	if (!empty()) {
		if (it->isDuplicate) {
			++it;
		}
	}
	return it;
}
ParallelInstVecUniqueIterator ParallelInstVec::iterUnique_end() {
	return ParallelInstVecUniqueIterator(*this, end());
}
llvm::iterator_range<ParallelInstVecUniqueIterator> ParallelInstVec::iterUnique() {
	return llvm::make_range(iterUnique_begin(), iterUnique_end());
}

std::size_t ParallelInstVec::uniqueSize() const {
	std::size_t count = 0;
	for ([[maybe_unused]] auto &_ : const_cast<ParallelInstVec*>(this)->iterUnique()) {
		++count;
	}
	return count;
}

}
