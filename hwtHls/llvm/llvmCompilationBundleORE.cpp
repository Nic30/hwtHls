#include <hwtHls/llvm/llvmCompilationBundleORE.h>

#include <llvm/Support/Error.h>
#include <llvm/IR/LLVMRemarkStreamer.h>
#include <llvm/Remarks/HotnessThresholdParser.h>

namespace hwtHls {

static llvm::cl::opt<bool> RemarksWithHotness(
    "pass-remarks-with-hotness",
	llvm::cl::desc("With PGO, include profile count in optimization remarks"),
	llvm::cl::Hidden);

static llvm::cl::opt<std::optional<uint64_t>, false, llvm::remarks::HotnessThresholdParser>
    RemarksHotnessThreshold(
        "pass-remarks-hotness-threshold",
		llvm::cl::desc("Minimum profile count required for "
                 "an optimization remark to be output. "
                 "Use 'auto' to apply the threshold from profile summary"),
				 llvm::cl::value_desc("N or 'auto'"), llvm::cl::init(0), llvm::cl::Hidden);

static llvm::cl::opt<std::string>
    RemarksFilename("pass-remarks-output",
                    llvm::cl::desc("Output filename for pass remarks"),
                    llvm::cl::value_desc("filename"));

static llvm::cl::opt<std::string>
    RemarksPasses("pass-remarks-filter",
    		llvm::cl::desc("Only record optimization remarks from passes whose "
                           "names match the given regular expression"),
						   llvm::cl::value_desc("regex"));

static llvm::cl::opt<std::string> RemarksFormat(
    "pass-remarks-format",
    llvm::cl::desc("The format used for serializing remarks (default: YAML)"),
    llvm::cl::value_desc("format"), llvm::cl::init("yaml"));


std::unique_ptr<llvm::ToolOutputFile> LlvmCompilationBundle_registerORE(llvm::LLVMContext & Context) {
	llvm::Expected<std::unique_ptr<llvm::ToolOutputFile>> RemarksFileOrErr =
		llvm::setupLLVMOptimizationRemarks(Context, RemarksFilename, RemarksPasses,
									 RemarksFormat, RemarksWithHotness,
									 RemarksHotnessThreshold);
	if (llvm::Error E = RemarksFileOrErr.takeError()) {
		throw std::runtime_error(toString(std::move(E)));
	}
	std::unique_ptr<llvm::ToolOutputFile> RemarksFile = std::move(*RemarksFileOrErr);
	return RemarksFile;
}

}
