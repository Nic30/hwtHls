#pragma once

#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/APInt.h>
#include <llvm/IR/Metadata.h>

namespace hwtHls {

class MetadataPyObjectPath {
public:
	std::vector<std::string> value;
	static MetadataPyObjectPath parse(llvm::MDTuple *md);
	llvm::MDTuple* toMetadata(llvm::LLVMContext &ctx) const;
};

class IntStringTupleOrObjectPath {
public:
	static constexpr std::string METADATA_NAME_PYOBJPATH = "pyobj";
	static constexpr std::string METADATA_NAME_TUPLE = "tuple";
	enum ValueT {
		V_NULL, V_INT, V_STR, V_TUPLE, V_OBJECT,
	};
	ValueT valT;
	llvm::APInt vInt; // formated as ConstantInt, MetadataAsValue
	std::string vStr; // formated as MDString
	std::vector<IntStringTupleOrObjectPath> vTuple; // formated as !0 = !{!"tuple", !1}; !1 = !{tuple items}
	MetadataPyObjectPath vObj; // formated as !0 = !{!"pyobj", !1}; !1 = !{path items}

	IntStringTupleOrObjectPath();
	IntStringTupleOrObjectPath(const llvm::APInt &i);
	IntStringTupleOrObjectPath(uint64_t i);
	IntStringTupleOrObjectPath(const std::string &str);
	IntStringTupleOrObjectPath(
			const std::vector<IntStringTupleOrObjectPath> &tuple);
	IntStringTupleOrObjectPath(const MetadataPyObjectPath &obj);

	static IntStringTupleOrObjectPath fromMetadata(llvm::Metadata *md);
	llvm::Metadata* toMetadata(llvm::LLVMContext &ctx) const;

};

void IntStringTupleOrObjectPath_fromMetadataMany(llvm::Metadata *md,
		std::vector<IntStringTupleOrObjectPath> &items);
llvm::MDTuple* IntStringTupleOrObjectPath_toMetadataMany(llvm::LLVMContext &ctx,
		const std::vector<IntStringTupleOrObjectPath> &items);
void IntStringTupleOrObjectPath_fromMetadataNamed(llvm::Metadata *md,
		std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> &items);
llvm::MDTuple* IntStringTupleOrObjectPath_toMetadataNamed(
		llvm::LLVMContext &ctx,
		const std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> &items);
void IntStringTupleOrObjectPath_fromMetadataIndexed(llvm::Metadata *md,
		std::vector<std::pair<uint64_t, IntStringTupleOrObjectPath>> &items);
llvm::MDTuple* IntStringTupleOrObjectPath_toMetadataIndexed(
		llvm::LLVMContext &ctx,
		const std::vector<std::pair<uint64_t, IntStringTupleOrObjectPath>> &items);

/*
 * Function metadata to mark placeholder LLVM function which shall be replaced with HWT instance in later compilation phase.
 * */
class MetadataThreadHwtComponent {
public:
	MetadataPyObjectPath constructor; // python path to constructor (typically HwModule subclass but can be any callable object)
	std::vector<IntStringTupleOrObjectPath> constructorArgs; // tuple of args
	std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> constructorKwargs; // tuple with {name, value}* for keyword args followed by sequence of values for args
	std::vector<std::pair<std::string, IntStringTupleOrObjectPath>> hwParams; // assigned to return value of constructor based on name (format same as constructorKwargs)
	std::vector<std::pair<uint64_t, IntStringTupleOrObjectPath>> ioMappingOverride;
	// the connection is done based on Function arg names by default but can be overridden in last arg
	// format is {function arg index, IntStringTupleOrObjectPath}*
	// :note: ports unreferenced by Function arguments and by ioMappingOverride are left unconnected without error
	//   this is to allow connection of things like clock/reset in later phases
	// :note: purpose of ioMappingOverride is to override connection to special types of IO on component instance from function arguments
	//        while HwtHlsIoMetadata specifies connection of this function arguments to outside word

	static const std::string METADATA_NAME;

	static std::optional<MetadataThreadHwtComponent> fromMetadata(
			llvm::MDNode *md);
	static std::optional<MetadataThreadHwtComponent> get(llvm::Function &F);
	llvm::MDTuple* toMetadata(llvm::LLVMContext &ctx) const;
	void set(llvm::Function &F) const;

};

}

