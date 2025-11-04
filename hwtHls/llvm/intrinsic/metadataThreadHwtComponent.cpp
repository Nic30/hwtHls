#include <hwtHls/llvm/intrinsic/metadataThreadHwtComponent.h>

#include <llvm/IR/Function.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Metadata.h>

using namespace llvm;

namespace hwtHls {

const std::string MetadataThreadHwtComponent::METADATA_NAME =
		"hwthls.thread.hwtcomponent";

MetadataPyObjectPath MetadataPyObjectPath::parse(MDTuple *md) {
	MetadataPyObjectPath path;
	assert(md);
	for (auto &o : md->operands()) {
		MDString *mdStr = dyn_cast<MDString>(o.get());
		assert(mdStr);
		path.value.push_back(mdStr->getString().str());
	}
	assert(path.value.size());
	return path;
}
MDTuple* MetadataPyObjectPath::toMetadata(LLVMContext &ctx) const {
	// Create an MDString for each element in the `value` vector
	SmallVector<Metadata*, 4> operands;
	for (const std::string &str : value) {
		operands.push_back(MDString::get(ctx, str));
	}

	// Create and return an MDTuple with all the MDStrings
	return MDTuple::get(ctx, operands);
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath() :
		valT(V_NULL) {
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath(const APInt &i) :
		valT(V_INT), vInt(i) {
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath(uint64_t i) :
		valT(V_INT), vInt(APInt(64, i)) {
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath(const std::string &str) :
		valT(V_STR), vStr(str) {
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath(
		const std::vector<IntStringTupleOrObjectPath> &tuple) :
		valT(V_TUPLE), vTuple(std::move(tuple)) {
}

IntStringTupleOrObjectPath::IntStringTupleOrObjectPath(
		const MetadataPyObjectPath &obj) :
		valT(V_OBJECT), vObj(obj) {
}

IntStringTupleOrObjectPath IntStringTupleOrObjectPath::fromMetadata(
		Metadata *md) {
	assert(md);

	if (MDString *str = dyn_cast<MDString>(md))
		return IntStringTupleOrObjectPath(str->getString().str());

	if (MDTuple *tuple = dyn_cast<MDTuple>(md)) {
		assert(tuple->getNumOperands() == 2);
		auto tupleTy = dyn_cast<MDString>(tuple->getOperand(0).get());
		assert(
				tupleTy
						&& "MDTuple in IntStringTupleOrObjectPath may be only 2 item tuple with \"pyobj\" or \"tuple\" as first operand and tuple as second");
		auto tupleVals = dyn_cast<MDTuple>(tuple->getOperand(1).get());
		assert(tupleVals);
		if (tupleTy->getString() == METADATA_NAME_PYOBJPATH) {
			return IntStringTupleOrObjectPath(
					MetadataPyObjectPath::parse(tupleVals));
		} else if (tupleTy->getString() == METADATA_NAME_TUPLE) {
			auto parsedTuple = std::vector<IntStringTupleOrObjectPath>();
			// Recursively parse the elements of the tuple
			for (auto &operand : tuple->operands()) {
				parsedTuple.push_back(fromMetadata(operand.get()));
			}

			return IntStringTupleOrObjectPath(std::move(parsedTuple));
		} else {
			llvm_unreachable(
					"expecting \"pyobj\" or \"tuple\" as first operand");
		}
	}

	if (auto v = dyn_cast<ValueAsMetadata>(md)) {
		if (dyn_cast<ConstantPointerNull>(v->getValue())) {
			return IntStringTupleOrObjectPath();
		} else if (ConstantInt *intVal = dyn_cast<ConstantInt>(v->getValue())) {
			return IntStringTupleOrObjectPath(intVal->getValue());
		}
	}
	llvm_unreachable("Unsupported metadata type");
}

Metadata* IntStringTupleOrObjectPath::toMetadata(LLVMContext &ctx) const {
	switch (valT) {
	case V_NULL: {
		return ValueAsMetadata::get(
				ConstantPointerNull::get(PointerType::get(ctx, 0)));
	}
	case V_INT: {
		return ValueAsMetadata::get(ConstantInt::get(ctx, vInt));
	}
	case V_STR: {
		return MDString::get(ctx, vStr);
	}
	case V_TUPLE: {
		// For tuples, create an MDTuple with each element in the tuple
		SmallVector<Metadata*, 4> tupleItems;
		for (const auto &item : vTuple) {
			tupleItems.push_back(item.toMetadata(ctx));
		}
		return MDTuple::get(ctx, { MDString::get(ctx, METADATA_NAME_TUPLE),
				MDTuple::get(ctx, tupleItems), });
	}
	case V_OBJECT: {
		return MDTuple::get(ctx, { MDString::get(ctx, METADATA_NAME_TUPLE),
				MDTuple::get(ctx, vObj.toMetadata(ctx)), });
	}
	default:
		llvm_unreachable(
				"Unsupported value type in IntStringTupleOrObjectPath");
	}
}

void IntStringTupleOrObjectPath_fromMetadataMany(Metadata *md,
		std::vector<IntStringTupleOrObjectPath> &items) {

	assert(md && "Metadata should not be null");
	MDTuple *tuple = dyn_cast<MDTuple>(md);
	assert(tuple);
	for (auto &operand : tuple->operands()) {
		items.push_back(
				IntStringTupleOrObjectPath::fromMetadata(operand.get()));
	}
}

MDTuple* IntStringTupleOrObjectPath_toMetadataMany(LLVMContext &ctx,
		const std::vector<IntStringTupleOrObjectPath> &items) {
	std::vector<Metadata*> operands;
	for (const auto &item : items) {
		operands.push_back(item.toMetadata(ctx));
	}
	return MDTuple::get(ctx, operands);
}

void IntStringTupleOrObjectPath_fromMetadataNamed(Metadata *md,
		std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> &items) {
	MDTuple *tuple = dyn_cast<MDTuple>(md);
	assert(tuple);
	assert(tuple->getNumOperands() % 2 == 0);

	// Parse each named pair {name, value}
	for (unsigned oI = 0; oI < tuple->getNumOperands(); oI += 2) {
		auto name = dyn_cast<MDString>(tuple->getOperand(oI).get());
		assert(name);
		auto value = IntStringTupleOrObjectPath::fromMetadata(
				tuple->getOperand(oI + 1).get());
		items.push_back( { name->getString().str(), value });
	}
}

MDTuple* IntStringTupleOrObjectPath_toMetadataNamed(LLVMContext &ctx,
		const std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> &items) {
	std::vector<Metadata*> operands;
	for (const auto &item : items) {
		operands.push_back(MDString::get(ctx, item.first));
		operands.push_back(item.second.toMetadata(ctx));
	}
	return MDTuple::get(ctx, operands);
}

void IntStringTupleOrObjectPath_fromMetadataIndexed(Metadata *md,
		std::vector<std::pair<uint64_t, IntStringTupleOrObjectPath>> &items) {
	MDTuple *tuple = dyn_cast<MDTuple>(md);
	assert(tuple);
	assert(tuple->getNumOperands() % 2 == 0);

	// Parse each named pair {name, value}
	for (unsigned oI = 0; oI < tuple->getNumOperands(); oI += 2) {
		auto indexV = dyn_cast<ValueAsMetadata>(tuple->getOperand(oI).get());
		assert(indexV);
		auto indexC = dyn_cast<ConstantInt>(indexV->getValue());
		assert(indexC);
		auto value = IntStringTupleOrObjectPath::fromMetadata(
				tuple->getOperand(oI + 1).get());
		items.push_back( { indexC->getValue().getZExtValue(), value });
	}
}

MDTuple* IntStringTupleOrObjectPath_toMetadataIndexed(LLVMContext &ctx,
		const std::vector<std::pair<uint64_t, IntStringTupleOrObjectPath>> &items) {
	std::vector<Metadata*> operands;
	for (const auto &item : items) {
		Metadata *indexMD = ValueAsMetadata::get(
				ConstantInt::get(ctx, APInt(64, item.first)));
		operands.push_back(indexMD);
		operands.push_back(item.second.toMetadata(ctx));
	}
	return MDTuple::get(ctx, operands);
}

std::optional<MetadataThreadHwtComponent> MetadataThreadHwtComponent::fromMetadata(
		MDNode *md) {
	if (!md) {
		return std::nullopt;
	}
	assert(md->getNumOperands() == 5);
	assert(md->isDistinct());

	MetadataThreadHwtComponent component;
	component.constructor = MetadataPyObjectPath::parse(
			dyn_cast<MDTuple>(md->getOperand(0).get()));
	IntStringTupleOrObjectPath_fromMetadataMany(md->getOperand(1).get(),
			component.constructorArgs);
	IntStringTupleOrObjectPath_fromMetadataNamed(md->getOperand(2).get(),
			component.constructorKwargs);
	IntStringTupleOrObjectPath_fromMetadataNamed(md->getOperand(3).get(),
			component.hwParams);
	IntStringTupleOrObjectPath_fromMetadataIndexed(md->getOperand(4).get(),
			component.ioMappingOverride);

	return component;
}

std::optional<MetadataThreadHwtComponent> MetadataThreadHwtComponent::get(
		Function &F) {
	MDNode *md = F.getMetadata(METADATA_NAME);
	return fromMetadata(md);
}

MDTuple* MetadataThreadHwtComponent::toMetadata(LLVMContext &ctx) const {
	std::vector<Metadata*> operands;
	operands.push_back(constructor.toMetadata(ctx));
	operands.push_back(
			IntStringTupleOrObjectPath_toMetadataMany(ctx, constructorArgs));
	operands.push_back(
			IntStringTupleOrObjectPath_toMetadataNamed(ctx, constructorKwargs));
	operands.push_back(
			IntStringTupleOrObjectPath_toMetadataNamed(ctx, hwParams));
	operands.push_back(
			IntStringTupleOrObjectPath_toMetadataIndexed(ctx,
					ioMappingOverride));
	return MDTuple::getDistinct(ctx, operands);
}

void MetadataThreadHwtComponent::set(llvm::Function &F) const {
	auto md = toMetadata(F.getContext());
	F.setMetadata(METADATA_NAME, md);
}

}
