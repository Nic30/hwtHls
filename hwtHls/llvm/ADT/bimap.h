#pragma once
#include <map>
#include <optional>
#include <llvm/ADT/SmallVector.h>

namespace hwtHls {

template<typename T0, typename T1>
class bimap {
	std::map<T0, T1> map0To1;
	std::map<T1, T0> map1To0;
	llvm::SmallVector<std::pair<T0, T1>> _items; // vector for deterministic iteration order
public:

	void insert(T0 k0, T1 k1) {
		map0To1[k0] = k1;
		map1To0[k1] = k0;
		_items.push_back( { k0, k1 });
	}

	std::optional<T0> find0(T1 k1) const {
		auto it = map1To0.find(k1);
		if (it == map1To0.end())
			return {};
		else
			return it->second;
	}

	std::optional<T1> find1(T0 k0) const {
		auto it = map0To1.find(k0);
		if (it == map0To1.end())
			return {};
		else
			return it->second;
	}
	bool contains0(T1 k1) const {
		return find1(k1).has_value();
	}
	bool contains1(T0 k0) const {
		return find0(k0).has_value();
	}
	bool empty() const {
		return _items.empty();
	}

	const llvm::SmallVector<std::pair<T0, T1>>& items() const {
		return _items;
	}
};

}
