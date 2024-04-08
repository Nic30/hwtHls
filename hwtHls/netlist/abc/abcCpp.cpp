#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <memory>
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>

// abc realated
#include <base/abc/abc.h>
#include <base/io/ioAbc.h>
#include <base/main/abcapis.h>
#include <base/main/main.h>
#include <map/mio/mio.h>
#include <aig/aig/aig.h>


namespace py = pybind11;

namespace hwtHls {

// https://github.com/kollartamas/CircuitMinimization/blob/master/src/Circuit.cpp
// https://people.eecs.berkeley.edu/~alanmi/abc/
// https://www.dropbox.com/s/qrl9svlf0ylxy8p/ABC_GettingStarted.pdf
// https://github.com/Yu-Utah/FlowTune

void * __attribute__ ((unused)) ___v = (void*) &Vec_MemHashProfile; // to suppress warning that Vec_MemHashProfile is unused

// these types are incomplete and pybind11 needs a typeinfo so we have to provide some existing type
struct Abc_Frame_t_pybind11_wrap {
};
struct Abc_Aig_t_pybind11_wrap {
};

template<typename Return, typename ... Args>
auto wrap_Abc_Aig_t(Return (*f)(Abc_Aig_t *, Args...)) {
	return [f](Abc_Aig_t_pybind11_wrap *self, Args &&... args) {
		return f((Abc_Aig_t*) self, args...);
	};
}

class Abc_ObjFaninIterator {
protected:
	Abc_Obj_t *pObj;
	int i = 0;
public:
	typedef std::forward_iterator_tag iterator_category;
	typedef Abc_Obj_t value_type;
	typedef int difference_type;
	typedef Abc_Obj_t *pointer;
	typedef Abc_Obj_t &reference;

	Abc_ObjFaninIterator(Abc_Obj_t &_pObj) :
			pObj(&_pObj) {
	}
	Abc_ObjFaninIterator(Abc_Obj_t &_pObj, int _i) :
			pObj(&_pObj), i(_i) {
	}

	Abc_ObjFaninIterator& operator++() {
		// based on Abc_ObjForEachFanin( pObj, pFanin, i )
		if ((i < Abc_ObjFaninNum(pObj))) {
			if (Abc_ObjFanin(pObj, i)) {
				++i;
			}
		}
		return *this;
	}

	reference operator*() const {
		return *Abc_ObjFanin(pObj, i);
	}

	bool operator==(Abc_ObjFaninIterator const &rhs) const {
		return pObj == rhs.pObj && i == rhs.i;
	}
	bool operator!=(Abc_ObjFaninIterator const &rhs) const {
		return *this != rhs;
	}
	void operator+=(int b) {
		i += b;
	}
	int operator-(const Abc_ObjFaninIterator &rhs) const {
		assert(pObj == rhs.pObj);
		return i - rhs.i;
	}
};

class Abc_Ntk_PoIterator {
protected:
	Abc_Ntk_t *pNtk;
	int i = 0;
public:
	typedef std::forward_iterator_tag iterator_category;
	typedef Abc_Obj_t value_type;
	typedef int difference_type;
	typedef Abc_Obj_t *pointer;
	typedef Abc_Obj_t &reference;

	Abc_Ntk_PoIterator(Abc_Ntk_t &_pNtk) :
		pNtk(&_pNtk) {
	}
	Abc_Ntk_PoIterator(Abc_Ntk_t &_pNtk, int _i) :
		pNtk(&_pNtk), i(_i) {
	}

	Abc_Ntk_PoIterator& operator++() {
		// based on Abc_ObjForEachFanin( pObj, pFanin, i )
		if ((i < Abc_NtkPoNum(pNtk))) {
			if (Abc_NtkPo(pNtk, i)) {
				++i;
			}
		}
		return *this;
	}

	reference operator*() const {
		return *Abc_NtkPo(pNtk, i);
	}

	bool operator==(Abc_Ntk_PoIterator const &rhs) const {
		return pNtk == rhs.pNtk && i == rhs.i;
	}
	bool operator!=(Abc_Ntk_PoIterator const &rhs) const {
		return *this != rhs;
	}
	void operator+=(int b) {
		i += b;
	}
	int operator-(const Abc_Ntk_PoIterator &rhs) const {
		assert(pNtk == rhs.pNtk);
		return i - rhs.i;
	}
};

class Abc_Ntk_PiIterator: public Abc_Ntk_PoIterator {
public:
	using Abc_Ntk_PoIterator::Abc_Ntk_PoIterator;
	Abc_Ntk_PiIterator& operator++() {
		// based on Abc_ObjForEachFanin( pObj, pFanin, i )
		if ((i < Abc_NtkPiNum(pNtk))) {
			if (Abc_NtkPi(pNtk, i)) {
				++i;
			}
		}
		return *this;
	}
	reference operator*() const {
		return *Abc_NtkPi(pNtk, i);
	}
};

// :note: duplicated Abc_ObjPrint converted for std::stringstream
std::string __repr__Abc_ObjPrint(Abc_Obj_t * pObj )
{
	std::stringstream ss;
    ss << "Object ";
    if (Abc_ObjIsComplement(pObj)) {
    	ss << "~";
    } else {
     	ss << " ";
    }
	// :attention: complement pointer is a abc hack which stores values in lower bits of pointer
	// which makes pointer itself invalid C++ pointer
	pObj = Abc_ObjRegular(pObj);
    ss << std::setw(5) << pObj->Id << " : ";
    switch ( pObj->Type )
    {
        case ABC_OBJ_NONE:
        	ss << "NONE   ";
            break;
        case ABC_OBJ_CONST1:
            ss << "Const1 ";
            break;
        case ABC_OBJ_PI:
            ss << "PI     ";
            break;
        case ABC_OBJ_PO:
            ss << "PO     ";
            break;
        case ABC_OBJ_BI:
            ss << "BI     ";
            break;
        case ABC_OBJ_BO:
            ss << "BO     ";
            break;
        case ABC_OBJ_NET:
            ss << "Net    ";
            break;
        case ABC_OBJ_NODE:
            ss << "Node   ";
            break;
        case ABC_OBJ_LATCH:
            ss << "Latch  ";
            break;
        case ABC_OBJ_WHITEBOX:
            ss << "Whitebox";
            break;
        case ABC_OBJ_BLACKBOX:
            ss << "Blackbox";
            break;
        default:
            throw std::runtime_error("__repr__Abc_ObjPrint unknown object type " + std::to_string(pObj->Type));
            break;
    }
    // print the fanins
    Abc_Obj_t * pFanin;
    int i;
    ss << " Fanins ( ";
    Abc_ObjForEachFanin( pObj, pFanin, i )
        ss << pFanin->Id << " ";
    ss << ") ";
    // print the logic function
    if ( Abc_ObjIsNode(pObj) && Abc_NtkIsSopLogic(pObj->pNtk) )
        ss << " " << (char*)pObj->pData;
    else if ( Abc_ObjIsNode(pObj) && Abc_NtkIsMappedLogic(pObj->pNtk) )
        ss << " <<" << Mio_GateReadName((Mio_Gate_t *)pObj->pData) ;
    return ss.str();
}

class AbcError : public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

template<typename Return, typename ... Args>
auto returnCodeToException(std::string errMsg, Return (*f)(Args...)) {
	return [f, &errMsg](Args &&... args) {
		int ret = f(args...);
		if (!ret)
			throw AbcError(errMsg);
		return ret;
	};
}

Abc_Obj_t * Abc_AigEq( Abc_Aig_t * pMan, Abc_Obj_t * p0, Abc_Obj_t * p1 )
{
    return Abc_AigOr( pMan, Abc_AigAnd(pMan, p0, p1),
                            Abc_AigAnd(pMan, Abc_ObjNot(p0), Abc_ObjNot(p1)) );
}
Abc_Obj_t * Abc_AigNe( Abc_Aig_t * pMan, Abc_Obj_t * p0, Abc_Obj_t * p1 )
{
    return Abc_AigOr( pMan, Abc_AigAnd(pMan, p0, Abc_ObjNot(p1)),
                            Abc_AigAnd(pMan, Abc_ObjNot(p0), p1) );
}

void register_Abc_Ntk_t(py::module_ &m) {
	py::class_<Abc_Ntk_t, std::unique_ptr<Abc_Ntk_t, py::nodelete>>(m, "Abc_Ntk_t")
	.def(py::init(&Abc_NtkAlloc))
	.def_property("pManFunc",
			[](Abc_Ntk_t * self) {
				return (Abc_Aig_t_pybind11_wrap*)self->pManFunc;
			},
			[](Abc_Ntk_t * self, Abc_Aig_t_pybind11_wrap * val) {
				self->pManFunc = (Abc_Aig_t*)val;
			}
	)
	.def("Name", &Abc_NtkName, py::return_value_policy::reference_internal)
	.def("setName", [](Abc_Ntk_t * self, char * name) {
		self->pName = Extra_UtilStrsav(name);
	})
	.def("CreatePi", &Abc_NtkCreatePi, py::return_value_policy::reference_internal)
	.def("CreatePo", &Abc_NtkCreatePo, py::return_value_policy::reference_internal)
	.def("Pi", &Abc_NtkPi, py::return_value_policy::reference_internal)
	.def("Po", &Abc_NtkPo, py::return_value_policy::reference_internal)
	.def("IterPo", [](Abc_Ntk_t &self) {
		return py::make_iterator(Abc_Ntk_PoIterator(self), Abc_Ntk_PoIterator(self, Abc_NtkPoNum(&self)));
	 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
	 .def("IterPi", [](Abc_Ntk_t &self) {
	 	 return py::make_iterator(Abc_Ntk_PiIterator(self), Abc_Ntk_PiIterator(self, Abc_NtkPiNum(&self)));
	 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */

	.def("PiNum", &Abc_NtkPiNum)
	.def("PoNum", &Abc_NtkPoNum)
	.def("CreateBi", &Abc_NtkCreateBi, py::return_value_policy::reference_internal)
	.def("CreateBo", &Abc_NtkCreateBo, py::return_value_policy::reference_internal)
	.def("Const1", &Abc_AigConst1, py::return_value_policy::reference_internal)
	.def_static("Miter", &Abc_NtkMiter, py::return_value_policy::reference_internal,
			py::arg("pNtk1"),
			py::arg("pNtk2"),
			py::arg("fComb") = false,
			py::arg("nPartSize") = 0ull,
			py::arg("fImplic") = false,
			py::arg("fMulti") = false,
			 R"""(
:param fComb: deriving combinational miter (latches as POs)
:param fImplic: deriving implication miter (file1 => file2)
:param nPartSize: output partition size
:param fMulti: creating multi-output miter
	)""")
	.def("MiterReport", &Abc_NtkMiterReport)
	.def("MiterIsConstant", &Abc_NtkMiterIsConstant, R"""(
        Description [Return 0 if the miter is sat for at least one output.
        Return 1 if the miter is unsat for all its outputs. Returns -1 if the
        miter is undecided for some outputs.]
	)""")
	.def("Balance", &Abc_NtkBalance,
			py::arg("fDuplicate")=false,
			py::arg("fSelective")=false,
			py::arg("fUpdateLevel")=true, py::return_value_policy::reference)
	.def("Rewrite", returnCodeToException("Abc_NtkRewrite has failed", &Abc_NtkRewrite),
			/* defaults are from Abc_CommandRewrite */
			py::arg("fUpdateLevel")=true,
			py::arg("fUseZeros")=false,
			py::arg("fVerbose")=false,
			py::arg("fVeryVerbose")=false,
			py::arg("fPlaceEnable")=false)
	.def("Refactor", returnCodeToException("Abc_NtkRefactor has failed", &Abc_NtkRefactor),
			/* defaults are from Abc_CommandRefactor */
			py::arg("nNodeSizeMax")=10,
			py::arg("nMinSaved")=1,
			py::arg("nConeSizeMax")=16,
			py::arg("fUpdateLevel")=true,
			py::arg("fUseZeros")=false,
			py::arg("fUseDcs")=false,
			py::arg("fVerbose")=false)
	.def("Check", &Abc_NtkCheck)
	.def("Io_Write", [](Abc_Ntk_t * pNtk, char *pFileName, Io_FileType_t FileType) {
		if (FileType == Io_FileType_t::IO_FILE_VERILOG && Abc_NtkName(pNtk) == nullptr) {
			throw std::runtime_error("Abc_Ntk_t is missing name");
		}
		Io_Write(pNtk, pFileName, FileType);
	}, R""""(
			Dump this network to a file in format specified by second argument.
			:attention: some formats like IO_FILE_VERILOG requires network name to be set
		)""""
	)
	.def("Io_WriteHie", [](Abc_Ntk_t * pNtk,  char * pBaseName, char * pFileName) {
		Io_WriteHie(pNtk, pFileName, pFileName);
	}, R""""(
			Outputs the hierarchy containing black boxes into a file if the original design contained black boxes. The original file should be given as one of the arguments in this command.
		)""""
	).doc() = "ABC network object.";


	py::enum_<Io_FileType_t>(m, "Io_FileType_t")
	 .value("IO_FILE_NONE",    Io_FileType_t::IO_FILE_NONE   )//
	 .value("IO_FILE_AIGER",   Io_FileType_t::IO_FILE_AIGER  , "Writes the combinational AIG in binary AIGER format developed by Armin Biere. This format is very compact and leads to a substantial reduction in the reading/writing times. (When writing AIGER for sequential circuits with non-0 initial states, use command zero to normalize the registers initial states.)")//
	 .value("IO_FILE_BAF",     Io_FileType_t::IO_FILE_BAF    , "Writes the combinational AIG in Binary Aig Format (BAF). For a description of BAF, refer to the source code file src/base/io/ioWriteBaf.c. This format is superseded by the AIGER format and kept for backward compatibility with earlier versions of ABC.")//
	 .value("IO_FILE_BBLIF",   Io_FileType_t::IO_FILE_BBLIF  )//
	 .value("IO_FILE_BLIF",    Io_FileType_t::IO_FILE_BLIF   , "Outputs the current network into a BLIF file. If the current network is mapped using a standard cell library, outputs the current network into a BLIF file, compatible with SIS and other tools. (The same genlib library has to be selected in SIS before reading the generated file.) The current mapper does not map the registers. As a result, the mapped BLIF files generated for sequential circuits contain unmapped latches. Additionally, command write_blif with command-line switch –l writes out a part of the current network containing a combinational logic without latches.")//
	 .value("IO_FILE_BLIFMV",  Io_FileType_t::IO_FILE_BLIFMV , "Outputs the current network into a BLIF-MV file. Two write a hierarchical BLIF-MV output, use command write_hie.")//
	 .value("IO_FILE_BENCH",   Io_FileType_t::IO_FILE_BENCH  , "Outputs the current network into a BENCH file.")//
	 .value("IO_FILE_BOOK",    Io_FileType_t::IO_FILE_BOOK   )//
	 .value("IO_FILE_CNF",     Io_FileType_t::IO_FILE_CNF    , "Outputs the current network into a CNF file, which can be used with a variety of SAT solvers. This command is only applicable to combinational miter circuits (the miter circuit has only one output, which is expected to be zero under all input combinations).")//
	 .value("IO_FILE_DOT",     Io_FileType_t::IO_FILE_DOT    , "Outputs the structure of the current network into a DOT file that can be processed by graph visualization package GraphViz. Currently work only if the current network is an AIG.")//
	 .value("IO_FILE_EDIF",    Io_FileType_t::IO_FILE_EDIF   )//
	 .value("IO_FILE_EQN",     Io_FileType_t::IO_FILE_EQN    , "Outputs the combinational part of the current network in the Synopsys equation format.")//
	 .value("IO_FILE_GML",     Io_FileType_t::IO_FILE_GML    , "Outputs the structure of the current network into a GML file used by some graph editors, such as yEd, a free product of yWorks.")//
	 .value("IO_FILE_JSON",    Io_FileType_t::IO_FILE_JSON   )//
	 .value("IO_FILE_LIST",    Io_FileType_t::IO_FILE_LIST   )//
	 .value("IO_FILE_PLA",     Io_FileType_t::IO_FILE_PLA    , "Outputs the current network into a PLA file. The current network should be collapsed (each PO is represented by a node whose fanins are PIs). Works only for combinational networks.")//
	 .value("IO_FILE_MOPLA",   Io_FileType_t::IO_FILE_MOPLA  )//
	 .value("IO_FILE_SMV",     Io_FileType_t::IO_FILE_SMV    )//
	 .value("IO_FILE_VERILOG", Io_FileType_t::IO_FILE_VERILOG, "Outputs the network using technology-independent Verilog.")//
	 .value("IO_FILE_UNKNOWN", Io_FileType_t::IO_FILE_UNKNOWN)//
     .export_values();


	py::class_<Abc_Aig_t_pybind11_wrap, std::unique_ptr<Abc_Aig_t_pybind11_wrap, py::nodelete>>(m, "Abc_Aig_t")
		.def("And", wrap_Abc_Aig_t(&Abc_AigAnd), py::return_value_policy::reference_internal)
		.def("Or", wrap_Abc_Aig_t(&Abc_AigOr), py::return_value_policy::reference_internal)
		.def("Xor", wrap_Abc_Aig_t(&Abc_AigXor), py::return_value_policy::reference_internal)
		.def("Mux", wrap_Abc_Aig_t(&Abc_AigMux), py::return_value_policy::reference_internal)
		.def("Eq", wrap_Abc_Aig_t(&Abc_AigEq), py::return_value_policy::reference_internal)
		.def("Ne", wrap_Abc_Aig_t(&Abc_AigNe), py::return_value_policy::reference_internal)
		.def("Not", [](Abc_Aig_t_pybind11_wrap *self, Abc_Obj_t* v) {
			return Abc_ObjNot(v);
		}, py::return_value_policy::reference_internal)
		.def("Miter", [](Abc_Aig_t_pybind11_wrap *self, const std::vector<Abc_Obj_t*> & memberPairs, bool fImplic) {
			// based on Abc_NtkMiterFinalize
			if (memberPairs.empty()) {
				throw std::runtime_error("memberPairs should not be empty");
			}
		    if (memberPairs.size() % 2 != 0) {
				throw std::runtime_error("memberPairs should contain pairs but size % 2 != 0");
			}
			struct Vec_Ptr_deleter {
				void operator()(Vec_Ptr_t *p) {
					Vec_PtrFree(p);
				}
			};
		    std::unique_ptr<Vec_Ptr_t, Vec_Ptr_deleter> vPairs;
		    vPairs.reset(Vec_PtrAlloc(memberPairs.size()));
			for (auto * pNode: memberPairs) {
				Vec_PtrPush( vPairs.get(), Abc_ObjChild0Copy(pNode) );
			}
			// pMiter = Abc_AigMiter( (Abc_Aig_t *)pNtkMiter->pManFunc, vPairs, fImplic );
            // Abc_ObjAddFanin( Abc_NtkPo(pNtkMiter,0), pMiter );
			return Abc_AigMiter( ((Abc_Aig_t *)self), vPairs.get(), fImplic);

		}, py::return_value_policy::reference_internal)
		.def("Cleanup", wrap_Abc_Aig_t(&Abc_AigCleanup));

	py::enum_<Abc_NtkType_t>(m, "Abc_NtkType_t")
	    .value("ABC_NTK_NONE", Abc_NtkType_t::ABC_NTK_NONE  )
	    .value("ABC_NTK_NETLIST", Abc_NtkType_t::ABC_NTK_NETLIST)
	    .value("ABC_NTK_LOGIC", Abc_NtkType_t::ABC_NTK_LOGIC )
	    .value("ABC_NTK_STRASH", Abc_NtkType_t::ABC_NTK_STRASH)
	    .value("ABC_NTK_OTHER", Abc_NtkType_t::ABC_NTK_OTHER  )
		.export_values();

	py::enum_<Abc_NtkFunc_t>(m, "Abc_NtkFunc_t")
	    .value("ABC_FUNC_NONE", Abc_NtkFunc_t::ABC_FUNC_NONE, "unknown")
	    .value("ABC_FUNC_SOP", Abc_NtkFunc_t::ABC_FUNC_SOP, "sum-of-products")
	    .value("ABC_FUNC_BDD", Abc_NtkFunc_t::ABC_FUNC_BDD, "binary decision diagrams")
	    .value("ABC_FUNC_AIG", Abc_NtkFunc_t::ABC_FUNC_AIG, "and-inverter graphs")
	    .value("ABC_FUNC_MAP", Abc_NtkFunc_t::ABC_FUNC_MAP, "standard cell library")
	    .value("ABC_FUNC_BLIFMV", Abc_NtkFunc_t::ABC_FUNC_BLIFMV, "BLIF-MV node functions")
	    .value("ABC_FUNC_BLACKBOX", Abc_NtkFunc_t::ABC_FUNC_BLACKBOX, "black box about which nothing is known")
	    .value("ABC_FUNC_OTHER", Abc_NtkFunc_t::ABC_FUNC_OTHER, "unused")
		.export_values();
}

template<typename ReturnT, typename ... Args>
auto Abc_Obj_t_rmComplementBeforeCall(ReturnT (*f)(Abc_Obj_t * self, Args...)) {
	return [f](Abc_Obj_t * self, Args &&... args) {
		return f(Abc_ObjRegular(self), args...);
	};
}

void register_Abc_Obj_t(py::module_ &m) {
	py::enum_<Abc_ObjType_t>(m, "Abc_ObjType_t")
	    .value("ABC_OBJ_NONE",     Abc_ObjType_t::ABC_OBJ_NONE,      "unknown"                   )//
	    .value("ABC_OBJ_CONST1",   Abc_ObjType_t::ABC_OBJ_CONST1,    "constant 1 node (AIG only)")//
	    .value("ABC_OBJ_PI",       Abc_ObjType_t::ABC_OBJ_PI,        "primary input terminal"    )//
	    .value("ABC_OBJ_PO",       Abc_ObjType_t::ABC_OBJ_PO,        "primary output terminal"   )//
	    .value("ABC_OBJ_BI",       Abc_ObjType_t::ABC_OBJ_BI,        "box input terminal"        )//
	    .value("ABC_OBJ_BO",       Abc_ObjType_t::ABC_OBJ_BO,        "box output terminal"       )//
	    .value("ABC_OBJ_NET",      Abc_ObjType_t::ABC_OBJ_NET,       "net"                       )//
	    .value("ABC_OBJ_NODE",     Abc_ObjType_t::ABC_OBJ_NODE,      "node"                      )//
	    .value("ABC_OBJ_LATCH",    Abc_ObjType_t::ABC_OBJ_LATCH,     "latch"                     )//
	    .value("ABC_OBJ_WHITEBOX", Abc_ObjType_t::ABC_OBJ_WHITEBOX,  "box with known contents"   )//
	    .value("ABC_OBJ_BLACKBOX", Abc_ObjType_t::ABC_OBJ_BLACKBOX,  "box with unknown contents" )//
	    .value("ABC_OBJ_NUMBER",   Abc_ObjType_t::ABC_OBJ_NUMBER,    "unused"                    )//
		.export_values();

	// this must be without delete, because life is mantained by parent Abc_Ntk_t
	// and some bits of pointer are used to mark private information so this is not even proper C++ pointer
	py::class_<Abc_Obj_t, std::unique_ptr<Abc_Obj_t, py::nodelete>>(m, "Abc_Obj_t")
		.def_property_readonly("Type", [](Abc_Obj_t * self) {
			return (Abc_ObjType_t)Abc_ObjType(Abc_ObjRegular(self));
		})
		.def_property_readonly("Id", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjId))
		.def("IsComplement", &Abc_ObjIsComplement)
		.def("Not", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjNot), "Get negated value of this")
		.def("NotCond", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjNotCond), "Conditionally get negated value of this")
		.def("Regular", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjRegular), "Get a non negated value of this")
		.def("FaninC0", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjFaninC0))
		.def("FaninC1", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjFaninC1))
		.def("AddFanin", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjAddFanin))
		.def("IterFanin", [](Abc_Obj_t &self) {
				Abc_Obj_t & _self = *Abc_ObjRegular(&self);
	 			return py::make_iterator(Abc_ObjFaninIterator(_self), Abc_ObjFaninIterator(_self, Abc_ObjFaninNum(&_self)));
	 	 	 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("IsPi", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjIsPi), "Is primary input")
		.def("IsPo", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjIsPo), "is primary output")
		.def("Name", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjName), py::return_value_policy::reference_internal)
		.def("AssignName", Abc_Obj_t_rmComplementBeforeCall(&Abc_ObjAssignName))
		// [todo] temporally disable using Abc_Obj_t private data because it is not clear if it
		//        is used by ABC internally, the data is also cleared after every abc transformation which
		//	.def("SetData", [](Abc_Obj_t * self, py::object & d) {
		//			d.inc_ref();
		//			Abc_ObjSetData(self, d.ptr());
		//		}, py::keep_alive<1, 0>()) // keep data alive while Abc_Obj_t is alive
		//	.def("Data", [](Abc_Obj_t * self) {
		//			PyObject* d = (PyObject*) Abc_ObjData(self);
		//			if (d == nullptr)
		//				return py::reinterpret_borrow<py::object>(py::none());
		//			return py::reinterpret_borrow<py::object>(d);
		//		}, py::return_value_policy::reference)
		.def("__repr__", &__repr__Abc_ObjPrint)
		.def("__eq__", [](Abc_Obj_t * self, Abc_Obj_t * other) {
			return self == other;
		})
		.def("__hash__", [](Abc_Obj_t* self) {
			return (std::intptr_t) self;
		});
}

PYBIND11_MODULE(abcCpp, m) {
	// https://people.eecs.berkeley.edu/~alanmi/abc/aig.pdf
	Abc_Start();

	py::class_<Abc_Frame_t_pybind11_wrap, std::unique_ptr<Abc_Frame_t_pybind11_wrap, py::nodelete>>(m, "Abc_Frame_t")
		.def_static("GetGlobalFrame", []() {
				return (Abc_Frame_t_pybind11_wrap*)Abc_FrameGetGlobalFrame();
			}, py::return_value_policy::reference)
		.def("CommandExecute", [](Abc_Frame_t_pybind11_wrap * pAbc, const char * sCommand) {
			return Cmd_CommandExecute((Abc_Frame_t*)pAbc, sCommand);
		})
		.def("SetCurrentNetwork", [](Abc_Frame_t_pybind11_wrap * pAbc, Abc_Ntk_t * pNtkNew) {
			Abc_FrameSetCurrentNetwork((Abc_Frame_t*)pAbc, pNtkNew);
		}, py::keep_alive<1, 0>()) // keep network alive while frame exists
		.def("DeleteAllNetworks", [](Abc_Frame_t_pybind11_wrap * pAbc) {
			Abc_FrameDeleteAllNetworks((Abc_Frame_t*)pAbc); // [todo] decr_ref for all Abc_Obj_t data
		});

	register_Abc_Ntk_t(m);
	register_Abc_Obj_t(m);
	//py::capsule cleanup(m, [](PyObject *) { Abc_Stop(); });
	//m.add_object("_cleanup", cleanup);
}
}
