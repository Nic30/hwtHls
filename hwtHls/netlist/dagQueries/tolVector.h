#pragma once

#include <vector>
#include <algorithm>

namespace TOL {

/*
 * A vector of an ordered sequence used to implement sets
 * */
template<typename _T>
class TolVector: public std::vector<_T> {
public:
	using std::vector<_T>::push_back;
	using std::vector<_T>::size;
	using std::vector<_T>::resize;
	using std::vector<_T>::reserve;
	using std::vector<_T>::capacity;
	using std::vector<_T>::begin;
	using std::vector<_T>::end;

	void sort() {
		if (size() == 0)
			return;

		if (size() < 20) {
			_T tmp;
			for (size_t i = 0; i < size() - 1; ++i) {
				unsigned k = i;
				for (size_t j = i + 1; j < size(); ++j)
					if ((*this)[j] < (*this)[k])
						k = j;
				if (k != i) {
					tmp = (*this)[i];
					(*this)[i] = (*this)[k];
					(*this)[k] = tmp;
				}
			}
		} else
			std::sort(begin(), end());
	}

	bool remove(_T &x) {
		auto _size = size();
		for (size_t left = 0, right = _size; left < right;) {
			// binary search for x
			size_t mid = (left + right) / 2;

			if ((*this)[mid] == x) {
				if (size() - 1 > mid)
					std::memmove(&(*this)[mid], &(*this)[mid + 1],
							sizeof(_T) * (size() - 1 - mid));
				resize(_size - 1);
				return true;
			} else if ((*this)[mid] < x)
				left = mid + 1;
			else
				right = mid;
		}
		return false;
	}

	bool sorted_insert(_T &x) {
		if (size() == 0) {
			std::vector<_T>::push_back(x);
			return true;
		}
		if (size() == capacity())
			reserve(capacity() * 2);

		unsigned l, r;

		for (l = 0, r = size(); l < r;) {
			// binary search for x
			int m = (l + r) / 2;
			if ((*this)[m] < x)
				l = m + 1;
			else
				r = m;
		}

		if (l < size() && (*this)[l] == x) {
			// Insert Duplicate
			return false;
		} else {
			// insert new item on found index in sorted sequence
			resize(size() + 1);
			if (size() - 1 > l) {
				// move all items after insert index to make place for this
				memmove(&(*this)[l + 1], &(*this)[l],
						sizeof(_T) * (size() - 1 - l));
			}
			(*this)[l] = x;
			return true;
		}
	}
	/*
	 * @return true if the x was in this vector else false
	 * */
	bool remove_unsorted(_T &x) {
		for (size_t m = 0; m < size(); ++m) {
			// linear search for for x
			if ((*this)[m] == x) {
				if (size() - 1 > m)
					memcpy(&(*this)[m], &(*this)[m + 1],
							sizeof(_T) * (size() - 1 - m));
				resize(size() - 1);
				return true;
			}
		}
		return false;
	}
};

}
