#include <list>
#include <unordered_set>

namespace hwtHls {
template <typename T> class ListSet : std::list<T> {
	using list_t = std::list<T>;
	std::unordered_set<T> set;

public:
	ListSet() :
		list_t() {}
	bool contains(const T &__x) { return set.contains(__x); }
	bool empty() const { return list_t::empty(); }

	void push_back(T __x) {
		if (set.contains(__x))
			return;
		list_t::push_back(__x);
		set.insert(__x);
	}

	T &front() { return list_t::front(); }

	void pop_front() {
		auto front = list_t::front();
		set.erase(front);
		list_t::pop_front();
	}
	T pop_front_val() {
		T v = front(); // :note: copy
		pop_front();
		return v;
	}
};
}