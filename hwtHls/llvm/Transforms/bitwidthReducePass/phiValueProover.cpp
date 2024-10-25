#include <hwtHls/llvm/Transforms/bitwidthReducePass/phiValueProover.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;
namespace hwtHls {

PHIValueProover::PHIValueProover(const llvm::PHINode *phi) :
		phi(phi) {
	auto w = phi->getType()->getIntegerBitWidth();
	knownBits.resize(w);
	knownBits[0] = ValueInfo(w);
}

PHIValueProover::ValueInfo::ValueInfo() :
		hasMultipleValues(false), width(0) {
}

PHIValueProover::ValueInfo::ValueInfo(size_t width) :
		hasMultipleValues(false), width(width) {
}

PHIValueProover::ValueInfo::ValueInfo(const llvm::PHINode *phi,
		const KnownBitRangeInfo &kbri) :
		hasMultipleValues(false), width(phi->getType()->getIntegerBitWidth()) {
	if (kbri.src != phi) {
		currentValue = kbri;
	}
}

void PHIValueProover::addOperandConstraint(const VarBitConstraint &opConstr) {
	for (const auto &r : opConstr.replacements) {
		knownBits_insert(r);
		assert(consistencyCheck());
	}
}

void PHIValueProover::knownBits_insertSameSizeNonPhi(KnownBitsIteraor valInfoIt,
		const KnownBitRangeInfo *kbri, bool hasMultipleValues) {

	if (hasMultipleValues || valInfoIt->hasMultipleValues) {
		if (valInfoIt->hasMultipleValues) {
			return; // no change, no need to propagate further
		} else {
			valInfoIt->currentValue = { };
			valInfoIt->hasMultipleValues = true;
		}
	} else if (valInfoIt->currentValue.has_value()) {
		assert(kbri && "kbri must be specified if hasMultipleValues=false");
		assert(
				kbri->src != phi
						&& "Case for phis should be handled in knownBits_insertSameSize()");
		auto &curV = valInfoIt->currentValue.value();
		if (*kbri == curV)
			return; // value is same (constant or non-constant)
		if (auto *kbriC = dyn_cast<ConstantInt>(kbri->src)) {
			if (auto *curC = dyn_cast<ConstantInt>(curV.src)) {
				// :attention: if we split item this may also split any other bits in value
				//             as bits can be arbitrary interwired
				auto sameBitMask = ~(kbriC->getValue() ^ curC->getValue());
				size_t off = valInfoIt - knownBits.begin();
				size_t offEnd = off + sameBitMask.getBitWidth();
				for (auto seq : iter1and0sequences(sameBitMask, 0,
						sameBitMask.getBitWidth())) {
					unsigned w = seq.second;
					// cut if found segment does not end at end of kbri
					if (off + w != offEnd) {
						knownBits_splitItem(knownBits.begin() + off, w);
					}
					auto itemToSet = knownBits.begin() + off;
					if (seq.first) {
						// 1 - same bit sequence found sequence found, can keep as it is
						assert(itemToSet->width == w);
					} else {
						// 0 - different sequence found - replace with hasMultipleValues
						knownBits_insertSameSizeNonPhi(itemToSet, { }, true);
					}
					off += w;
				}
				return;
			}
		}
		valInfoIt->hasMultipleValues = true;
		valInfoIt->currentValue = { };
	} else {
		assert(!valInfoIt->hasMultipleValues);
		assert(kbri->dstBeginBitI == valInfoIt - knownBits.begin());
		valInfoIt->currentValue = *kbri;
	}
	// propagate value change in both directions
	for (auto uOff : valInfoIt->users) {
		auto u = knownBits.begin() + uOff;
		auto _valInfoIt = valInfoIt;
		if (hasMultipleValues) {
			knownBits_insertSameSizeNonPhi(u, nullptr, true);
		} else {
			// :note: the kbri may have dstBitI <,= or > than uOff
			// we have to shift it to be the same
			KnownBitRangeInfo _kbri(*kbri);
			_kbri.dstBeginBitI = uOff;

			size_t w = _valInfoIt->width; // width of current item in knownBits to be updated
			for (size_t off = 0; off != kbri->width; off += w) {
				// for each chunk of bits in newly propagated kbri
				w = _valInfoIt->width;
				if (off == 0 && kbri->width == w) {
					knownBits_insertSameSizeNonPhi(u, &_kbri,
							valInfoIt->hasMultipleValues);
				} else {
					auto _v = _kbri.slice(off, w);
					knownBits_insertSameSizeNonPhi(u, &_v,
							valInfoIt->hasMultipleValues);
				}
				_valInfoIt += w;
			}
		}
	}
}

void PHIValueProover::knownBits_insertSameSizePhi(KnownBitsIteraor valInfoIt,
		const KnownBitRangeInfo &kbri, bool hasMultipleValues) {
	if (kbri.dstBeginBitI == kbri.srcBeginBitI)
		return; // no need to add reference on itself

	// src may be cut into multiple pieces, if this is the case
	// we have to cut this chunk as well
	auto foundSrcPredec = knownBits.begin() + kbri.srcBeginBitI;
	// skip placeholder records
	while (foundSrcPredec->width == 0) {
		--foundSrcPredec;
	}
	size_t srcBeginBitI = foundSrcPredec - knownBits.begin();
	// same if structure as in knownBits_insert which asserts that src and dst segments are of same size
	if (srcBeginBitI == kbri.srcBeginBitI) { // if knownBits record begins on same bits as requested by caller
		if (foundSrcPredec->width == kbri.width) { // if record in knownBits is also of the same width
			// add users/phiDeps link to notify about slice
			if (foundSrcPredec->users.insert(kbri.dstBeginBitI).second) {
				assert(valInfoIt->phiDeps.insert(kbri.srcBeginBitI).second);
				bool propagateValFromSrc = (foundSrcPredec->hasMultipleValues
						&& !valInfoIt->hasMultipleValues)
						|| foundSrcPredec->currentValue.has_value();
				bool propagateValToSrc = (valInfoIt->hasMultipleValues
						&& !foundSrcPredec->hasMultipleValues)
						|| valInfoIt->currentValue.has_value();
				if (propagateValFromSrc) {
					// if it is newly inserted, propagate value of foundSrcPredec record to this one
					// potentially splitting some records
					KnownBitRangeInfo _kbri(0u);
					KnownBitRangeInfo *_kbriPtr = nullptr;
					if (foundSrcPredec->currentValue.has_value()) {
						_kbri = foundSrcPredec->currentValue.value();
						_kbri.dstBeginBitI = valInfoIt - knownBits.begin();
						_kbriPtr = &_kbri;
					}
					knownBits_insertSameSizeNonPhi(valInfoIt, _kbriPtr,
							foundSrcPredec->hasMultipleValues);
				}
				// :note: there the foundSrcPredec and valInfoIt records may be already split to multiple
				//        because of splitting during value propagation
				if (propagateValToSrc) {
					// if it is newly inserted, propagate value of this record to foundSrcPredec
					// potentially splitting some records

					auto srcIt = foundSrcPredec;
					auto dstIt = valInfoIt;
					auto w = srcIt->width;
					for (size_t off = 0; off != kbri.width; off += w) {
						assert(off < kbri.width);
						assert(srcIt->width);
						assert(dstIt->width);
						assert(
								srcIt->width == dstIt->width
										&& "Because users and phiDeps are updated all splits must propagate");
						w = srcIt->width;
						if (dstIt->hasMultipleValues) {
							knownBits_insertSameSizeNonPhi(valInfoIt, nullptr,
									true);
						} else {
							auto _v = dstIt->currentValue.value();
							assert(_v.width == w);
							_v.dstBeginBitI = srcIt - knownBits.begin();
							knownBits_insertSameSizeNonPhi(srcIt, &_v,
									dstIt->hasMultipleValues);
						}
						srcIt += w;
						dstIt += w;
					}
				}

			} else {
				assert(
						valInfoIt->phiDeps.find(kbri.srcBeginBitI)
								== valInfoIt->phiDeps.end());
				// it was already known that valInfoIt may use foundSrcPredec
			}

		} else if (foundSrcPredec->width < kbri.width) {
			// must split kbri
			knownBits_splitItem(valInfoIt, foundSrcPredec->width);
					//kbri.slice(0, foundSrcPredec->width));
			knownBits_insert(kbri.slice(0, foundSrcPredec->width));
			knownBits_insert(
					kbri.slice(foundSrcPredec->width,
							kbri.width - foundSrcPredec->width));

		} else {
			assert(kbri.width < foundSrcPredec->width);
			// must split record in knownBits
			knownBits_splitItem(foundSrcPredec, kbri.width);
			knownBits_insertSameSize(valInfoIt, kbri);
		}
	} else {
		// split prefix of foundPredec and try again
		assert(
				srcBeginBitI < kbri.srcBeginBitI
						&& "foundPredec must be first overlapping");
		knownBits_splitItem(foundSrcPredec, kbri.srcBeginBitI - srcBeginBitI);
		knownBits_insert(kbri);
	}

	//valInfoIt->phiDeps.insert(kbri.srcBeginBitI);
}

void PHIValueProover::knownBits_insertSameSize(KnownBitsIteraor valInfoIt,
		const KnownBitRangeInfo &kbri, bool hasMultipleValues) {
	assert(valInfoIt->width == kbri.width);
	assert(valInfoIt - knownBits.begin() == kbri.dstBeginBitI);

	if (valInfoIt->hasMultipleValues)
		return; // :see: PHIValueProover::ValueInfo
	if (kbri.src == phi && !hasMultipleValues) {
		knownBits_insertSameSizePhi(valInfoIt, kbri, hasMultipleValues);
	} else {
		knownBits_insertSameSizeNonPhi(valInfoIt,
				hasMultipleValues ? nullptr : &kbri, hasMultipleValues);
	}
}

void PHIValueProover::knownBits_insert(const KnownBitRangeInfo &kbri) {
	auto firstOverlappingKbri = knownBits.begin() + kbri.dstBeginBitI;
	// skip placeholder records, at least begin should have width != 0
	while (firstOverlappingKbri->width == 0) {
		--firstOverlappingKbri;
	}

	// if there is an item which spans over the same bits we can just add it
	// if there is not we have to split this or current into multiple

	// index must be used because adding to vector causes iterator invalidation
	size_t dstBeginBitI = firstOverlappingKbri - knownBits.begin();
	size_t curWidth = firstOverlappingKbri->width;

	if (dstBeginBitI == kbri.dstBeginBitI) {
		if (curWidth == kbri.width) {
			// 1:1 width and offset match
			knownBits_insertSameSize(firstOverlappingKbri, kbri);
		} else if (curWidth < kbri.width) {
			// must split kbri
			knownBits_insertSameSize(firstOverlappingKbri,
					kbri.slice(0, curWidth));
			knownBits_insert(kbri.slice(curWidth, kbri.width - curWidth));
		} else {
			assert(kbri.width < curWidth);
			// must split record in knownBits first
			knownBits_splitItem(firstOverlappingKbri, kbri.width);
			knownBits_insert(kbri);
		}
	} else {
		// split prefix of curKbri and try again
		assert(
				dstBeginBitI < kbri.dstBeginBitI
						&& "curKbri must be first overlapping, this is how std::lower_bound works");
		knownBits_splitItem(firstOverlappingKbri,
				kbri.dstBeginBitI - dstBeginBitI);
		knownBits_insert(kbri);
	}
}

void PHIValueProover::knownBits_splitItem(KnownBitsIteraor knownBitsItem,
		size_t newWidthOfLeft) {
	assert(knownBitsItem != knownBits.end());
	assert(newWidthOfLeft > 0);
	size_t originalWidth = knownBitsItem->width;
	if (originalWidth == newWidthOfLeft)
		return;
	assert(originalWidth > newWidthOfLeft);

	// split this item,
	knownBitsItem->width = newWidthOfLeft;
	KnownBitsIteraor secondPart = knownBitsItem + newWidthOfLeft;
	assert(secondPart->width == 0);
	secondPart->width = originalWidth - newWidthOfLeft;
	secondPart->hasMultipleValues = knownBitsItem->hasMultipleValues;
	if (knownBitsItem->currentValue.has_value()) {
		secondPart->currentValue = knownBitsItem->currentValue.value().slice(
				newWidthOfLeft, secondPart->width);
		knownBitsItem->currentValue = knownBitsItem->currentValue.value().slice(
				0, newWidthOfLeft);
	}
	for (auto uOff : knownBitsItem->users) {
		knownBits_splitItem(knownBits.begin() + uOff, newWidthOfLeft);
	}
	for (auto uDep : knownBitsItem->phiDeps) {
		knownBits_splitItem(knownBits.begin() + uDep, newWidthOfLeft);
	}

}

VarBitConstraint PHIValueProover::resolve() {
	assert(!knownBits.empty());
	VarBitConstraint res(phi->getType()->getIntegerBitWidth());

	consistencyCheck();
	size_t offset = 0;
	for (auto vi = knownBits.begin();
			vi != knownBits.begin() + phi->getType()->getIntegerBitWidth();
			vi += vi->width) {
		size_t width = vi->width;
		if (vi->currentValue.has_value()) {
			assert(!vi->hasMultipleValues);
			// can reduce phi value to some specific other value
			res.srcUnionPushBackWithMerge(res.replacements, vi->currentValue.value(), 0, width);
			//res.replacements.push_back(vi->currentValue.value());
		} else {
			// case where this can be only a single bit range of this phi (not necessary the same)
			res.srcUnionPushBackWithMerge(res.replacements, KnownBitRangeInfo(phi), offset, width);
			// res.replacements.push_back(
			// 		KnownBitRangeInfo(phi).slice(offset, width));
		}
		offset += vi->width;
	}
	// errs() << "Phi resolved to: " << *phi << "\n";
	// errs() << *this << "\n" << res << "\n";

	return res;
}

bool PHIValueProover::consistencyCheck() const {
	assert(phi != nullptr);
	size_t offset = 0;
	size_t offsetNext = 0;
	assert(knownBits.size());
	for (const auto &kb : knownBits) {
		assert(kb.hasMultipleValues == 1 || kb.hasMultipleValues == 0);
		if (offset == offsetNext) {
			assert(kb.width != 0);
		} else {
			assert(kb.width == 0);
			assert(!kb.hasMultipleValues);
			assert(!kb.currentValue.has_value());
			assert(kb.phiDeps.empty());
			assert(kb.users.empty());
		}
		if (kb.currentValue.has_value()) {
			assert(kb.currentValue.value().dstBeginBitI == offset);
			assert(kb.currentValue.value().width == kb.width);
		}
		for (size_t depOff : kb.phiDeps) {
			assert(depOff < phi->getType()->getIntegerBitWidth());
			const auto &dep = knownBits[depOff];
			assert(dep.width == kb.width);
			assert(dep.users.find(offset) != dep.users.end());
		}
		for (size_t uOff : kb.users) {
			assert(uOff < phi->getType()->getIntegerBitWidth());
			const auto &u = knownBits[uOff];
			assert(u.width == kb.width);
			assert(u.phiDeps.find(offset) != u.phiDeps.end());
		}
		if (kb.width)
			offsetNext = offset + kb.width;
		offset += 1;
		assert(offset <= phi->getType()->getIntegerBitWidth());
	}
	return true;
}

void PHIValueProover::print(llvm::raw_ostream &O, bool IsForDebug) const {
	O << "PHIValueProover(" << phi << " " << *phi << "\n";
	for (auto _kb = knownBits.begin(); _kb != knownBits.end(); ++_kb) {
		if (_kb->width == 0)
			continue;
		size_t dstBeginBitI = _kb - knownBits.begin();
		const auto &kb = *_kb;
		O << "  [" << dstBeginBitI + kb.width << ":" << dstBeginBitI << "]";
		if (kb.hasMultipleValues) {
			O << " hasMultipleValues";
		}
		if (kb.currentValue.has_value()) {
			O << " " << kb.currentValue.value();
		}
		O << "\n";
		for (const auto &k : kb.phiDeps) {
			O << "    [" << k + kb.width << ":" << k << "]\n";
		}
	}
	O << ")";
}

}
