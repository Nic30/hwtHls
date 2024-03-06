#pragma once

#include <vector>
#include <assert.h>

#include <llvm/ADT/iterator_range.h>

namespace llvm {
class Instruction;
}

namespace hwtHls {

struct ParallelInstVecItem {
	llvm::Instruction *I;
	bool hasOperandsSwapped; // used to mark that operands are swapped for commutative operands
	bool isDuplicate; // true if some previous item already has same I
};

class ParallelInstVecInBlockOrderIterator;
class ParallelInstVecUniqueIterator;

/*
 * lowest first vector of instructions on same slice which have slices of the same bit vector as operands
 */
class ParallelInstVec: private std::vector<ParallelInstVecItem> {
protected:
	std::vector<std::size_t> thisOrderedAsInParentBlock; // vector of indexes to "this" to allow iteration in block order
	// without sorting
	using BASE_T = std::vector<ParallelInstVecItem>;
public:
	friend ParallelInstVecInBlockOrderIterator;
	using BASE_T::begin;
	using BASE_T::end;
	using BASE_T::size;
	using BASE_T::empty;
	using iterator = typename BASE_T::iterator;
	using reference = typename BASE_T::reference;
	using difference_type = typename BASE_T::difference_type;
	using const_iterator = typename BASE_T::const_iterator;

	using BASE_T::operator[];

	const llvm::Instruction* getInstructionClosesToBlockEnd() const;
	std::pair<std::vector<std::size_t>::iterator, iterator> getInstrAfter(
			llvm::Instruction *I);
	iterator insertSorted(llvm::Instruction *I, bool hasSwappedOperands);
	// check if instruction does not depend (transitively) on any already contained instruction
	// and that any contained instruction does not depend (transitively) on this instruction
	bool canInsert(llvm::Instruction *I);

	// iterate instructions in order in which they are placed in parent basic block
	ParallelInstVecInBlockOrderIterator iterInBlockOrder_begin();
	ParallelInstVecInBlockOrderIterator iterInBlockOrder_end();
	llvm::iterator_range<ParallelInstVecInBlockOrderIterator> iterInBlockOrder();

	// iterate this vector skipping duplicated items
	ParallelInstVecUniqueIterator iterUnique_begin();
	ParallelInstVecUniqueIterator iterUnique_end();
	llvm::iterator_range<ParallelInstVecUniqueIterator> iterUnique();
	std::size_t uniqueSize() const;
};

/*
 * ParallelInstVec::iterator which skips items with isDuplicate=true
 * */
class ParallelInstVecUniqueIterator {
	ParallelInstVec &parent;
	ParallelInstVec::iterator instrIt;

public:
	using iterator_category = std::random_access_iterator_tag;
	using value_type = ParallelInstVecItem;
	using difference_type = long;
	using pointer = ParallelInstVecItem*;
	using reference = ParallelInstVecItem&;
	using iterator = ParallelInstVecUniqueIterator;

	explicit ParallelInstVecUniqueIterator(ParallelInstVec &_parent) :
			parent(_parent), instrIt(_parent.begin()) {
	}
	explicit ParallelInstVecUniqueIterator(ParallelInstVec &_parent,
			ParallelInstVec::iterator _instrIt) :
			parent(_parent), instrIt(_instrIt) {
	}
	iterator& operator=(const iterator &rhs) {
		assert(&parent == &rhs.parent);
		instrIt = rhs.instrIt;
		return *this;
	}

	reference operator*() const {
		return *instrIt;
	}

	reference operator[](const difference_type &n) const {
		return *(*this + n);
	}

	pointer operator ->() {
		return &*instrIt;
	}

	bool isOnEnd() {
		return instrIt == parent.end();
	}

	// incr/decr
	iterator& operator++() {
		assert(instrIt != parent.end());
		do {
			instrIt++;
		} while (instrIt != parent.end() && instrIt->isDuplicate);
		return *this;
	}
	iterator& operator--() {
		assert(instrIt != parent.begin());
		do {
			instrIt--;
		} while (instrIt != parent.begin() && instrIt->isDuplicate);
		return *this;
	}

	// postfix variants
	iterator operator++(int) {
		iterator retval = *this;
		++(*this);
		return retval;
	}
	iterator operator--(int) {
		iterator retval = *this;
		--(*this);
		return retval;
	}

	// add/sub
	iterator& operator+=(const difference_type &n) {
		long _n = n;
		if (_n < 0) {
			for (;_n;++_n) {
				--(*this);
			}
		} else {
			for (;_n;--_n) {
				++(*this);
			}
		}
		return *this;
	}
	iterator operator+(const difference_type &n) const {
		iterator tmp(*this);
		tmp += n;
		return tmp;
	}
	iterator& operator-=(const difference_type &n) {
		(*this) += -n;
		return *this;
	}
	iterator operator-(const difference_type &n) const {
		iterator tmp(*this);
		tmp -= n;
		return tmp;
	}

	// compares
	bool operator==(iterator other) const {
		return instrIt == other.instrIt;
	}
	bool operator!=(iterator other) const {
		return !(*this == other);
	}
	bool operator<(const iterator &rhs) const {
		return instrIt < rhs.instrIt;
	}
	bool operator<=(const iterator &rhs) const {
		return instrIt <= rhs.instrIt;
	}
	bool operator>(const iterator &rhs) const {
		return instrIt > rhs.instrIt;
	}
	bool operator>=(const iterator &rhs) const {
		return instrIt >= rhs.instrIt;
	}
};

class ParallelInstVecInBlockOrderIterator {
	ParallelInstVec &parent;
	std::vector<std::size_t>::iterator blockIndexIt;
	ParallelInstVec::iterator instrIt;

public:
	using iterator_category = std::random_access_iterator_tag;
	using value_type = std::pair<std::size_t, ParallelInstVecItem>;
	using difference_type = long;
	using pointer = std::pair<std::size_t*, ParallelInstVecItem*>;
	using reference = std::pair<std::size_t&, ParallelInstVecItem&>;
	using iterator = ParallelInstVecInBlockOrderIterator;

	explicit ParallelInstVecInBlockOrderIterator(ParallelInstVec &_parent) :
			parent(_parent), blockIndexIt(
					_parent.thisOrderedAsInParentBlock.begin()) {
		_updateInstrIt();
	}
	explicit ParallelInstVecInBlockOrderIterator(ParallelInstVec &_parent,
			std::vector<std::size_t>::iterator _blockIndexIt) :
			parent(_parent), blockIndexIt(_blockIndexIt) {
		_updateInstrIt();
	}

	iterator& operator=(const iterator &rhs) {
		assert(&parent == &rhs.parent);
		blockIndexIt = rhs.blockIndexIt;
		instrIt = rhs.instrIt;
		return *this;
	}

	reference operator*() const {
		return reference(*blockIndexIt, *instrIt);
	}

	reference operator[](const difference_type &n) const {
		return *(*this + n);
	}
	ParallelInstVec::iterator getInstrIt() {
		return instrIt;
	}
	std::vector<std::size_t>::iterator getIndexIt() {
		return blockIndexIt;
	}
	pointer operator ->() {
		return {&*blockIndexIt, &*instrIt};
	}

	bool isOnEnd() {
		return blockIndexIt == parent.thisOrderedAsInParentBlock.end();
	}
	void _updateInstrIt() {
		if (isOnEnd()) {
			instrIt = parent.end();
		} else {
			instrIt = parent.begin() + *blockIndexIt;
		}
	}

	// incr/decr
	iterator& operator++() {
		blockIndexIt++;
		_updateInstrIt();
		return *this;
	}
	iterator& operator--() {
		blockIndexIt--;
		_updateInstrIt();
		return *this;
	}

	// postfix variants
	iterator operator++(int) {
		iterator retval = *this;
		++(*this);
		return retval;
	}
	iterator operator--(int) {
		iterator retval = *this;
		--(*this);
		return retval;
	}

	// add/sub
	iterator& operator+=(const difference_type &n) {
		blockIndexIt += n;
		_updateInstrIt();
		return *this;
	}
	iterator operator+(const difference_type &n) const {
		iterator tmp(*this);
		tmp += n;
		return tmp;
	}
	iterator& operator-=(const difference_type &n) {
		blockIndexIt -= n;
		_updateInstrIt();
		return *this;
	}
	iterator operator-(const difference_type &n) const {
		iterator tmp(*this);
		tmp -= n;
		return tmp;
	}

	// compares
	bool operator==(iterator other) const {
		return blockIndexIt == other.blockIndexIt;
	}
	bool operator!=(iterator other) const {
		return !(*this == other);
	}
	bool operator<(const iterator &rhs) const {
		return blockIndexIt < rhs.blockIndexIt;
	}
	bool operator<=(const iterator &rhs) const {
		return blockIndexIt <= rhs.blockIndexIt;
	}
	bool operator>(const iterator &rhs) const {
		return blockIndexIt > rhs.blockIndexIt;
	}
	bool operator>=(const iterator &rhs) const {
		return blockIndexIt >= rhs.blockIndexIt;
	}
};

}
