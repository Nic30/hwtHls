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
#include <base/main/abcapis.h>
#include <base/main/main.h>
#include <map/mio/mio.h>


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
    Abc_Obj_t * pFanin;
    int i;
    ss << "Object " << std::setw(5) << pObj->Id << " : ";
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
			Abc_FrameDeleteAllNetworks((Abc_Frame_t*)pAbc);
		});

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
		.def("setName", [](Abc_Ntk_t * self, char * name) {
			self->pName = Extra_UtilStrsav(name);
		})
		.def("CreatePi", &Abc_NtkCreatePi, py::return_value_policy::reference)
		.def("CreatePo", &Abc_NtkCreatePo, py::return_value_policy::reference)
		.def("Pi", &Abc_NtkPi)
		.def("Po", &Abc_NtkPo)
		.def("IterPo", [](Abc_Ntk_t &self) {
			return py::make_iterator(Abc_Ntk_PoIterator(self), Abc_Ntk_PoIterator(self, Abc_NtkPoNum(&self)));
	 	 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		 .def("IterPi", [](Abc_Ntk_t &self) {
		 	 return py::make_iterator(Abc_Ntk_PiIterator(self), Abc_Ntk_PiIterator(self, Abc_NtkPiNum(&self)));
		 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */

		.def("PiNum", &Abc_NtkPiNum)
		.def("PoNum", &Abc_NtkPoNum)
		.def("CreateBi", &Abc_NtkCreateBi, py::return_value_policy::reference)
		.def("CreateBo", &Abc_NtkCreateBo, py::return_value_policy::reference)
		.def("Const1", &Abc_AigConst1, py::return_value_policy::reference)
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
		.def("Check", &Abc_NtkCheck);


	py::class_<Abc_Aig_t_pybind11_wrap, std::unique_ptr<Abc_Aig_t_pybind11_wrap, py::nodelete>>(m, "Abc_Aig_t")
			.def("And", wrap_Abc_Aig_t(&Abc_AigAnd), py::return_value_policy::reference)
			.def("Or", wrap_Abc_Aig_t(&Abc_AigOr), py::return_value_policy::reference)
		    .def("Xor", wrap_Abc_Aig_t(&Abc_AigXor), py::return_value_policy::reference)
		    .def("Mux", wrap_Abc_Aig_t(&Abc_AigMux), py::return_value_policy::reference)
			.def("Eq", wrap_Abc_Aig_t(&Abc_AigEq), py::return_value_policy::reference)
			.def("Ne", wrap_Abc_Aig_t(&Abc_AigNe), py::return_value_policy::reference)
			.def_static("Not", &Abc_ObjNot, py::return_value_policy::reference)
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

	py::enum_<Abc_ObjType_t>(m, "Abc_ObjType_t")
	    .value("ABC_OBJ_NONE",     Abc_ObjType_t::ABC_OBJ_NONE,      "unknown"                   )
	    .value("ABC_OBJ_CONST1",   Abc_ObjType_t::ABC_OBJ_CONST1,    "constant 1 node (AIG only)")
	    .value("ABC_OBJ_PI",       Abc_ObjType_t::ABC_OBJ_PI,        "primary input terminal"    )
	    .value("ABC_OBJ_PO",       Abc_ObjType_t::ABC_OBJ_PO,        "primary output terminal"   )
	    .value("ABC_OBJ_BI",       Abc_ObjType_t::ABC_OBJ_BI,        "box input terminal"        )
	    .value("ABC_OBJ_BO",       Abc_ObjType_t::ABC_OBJ_BO,        "box output terminal"       )
	    .value("ABC_OBJ_NET",      Abc_ObjType_t::ABC_OBJ_NET,       "net"                       )
	    .value("ABC_OBJ_NODE",     Abc_ObjType_t::ABC_OBJ_NODE,      "node"                      )
	    .value("ABC_OBJ_LATCH",    Abc_ObjType_t::ABC_OBJ_LATCH,     "latch"                     )
	    .value("ABC_OBJ_WHITEBOX", Abc_ObjType_t::ABC_OBJ_WHITEBOX,  "box with known contents"   )
	    .value("ABC_OBJ_BLACKBOX", Abc_ObjType_t::ABC_OBJ_BLACKBOX,  "box with unknown contents" )
	    .value("ABC_OBJ_NUMBER",   Abc_ObjType_t::ABC_OBJ_NUMBER,    "unused"                    )
		.export_values();


	py::class_<Abc_Obj_t>(m, "Abc_Obj_t")
		.def_property_readonly("Type", [](Abc_Obj_t * self) {
			return (Abc_ObjType_t)Abc_ObjType(self);
		})
		.def("Not", &Abc_ObjNot, py::return_value_policy::reference)
		.def("FaninC0", &Abc_ObjFaninC0)
		.def("FaninC1", &Abc_ObjFaninC1)
		.def("IsPi", &Abc_ObjIsPi)
		.def("IsPo", &Abc_ObjIsPo)
		.def("AddFanin", &Abc_ObjAddFanin)
		.def("AssignName", &Abc_ObjAssignName)
		.def("SetData", [](Abc_Obj_t * self, py::object & d) {
				d.inc_ref();
				Abc_ObjSetData(self, d.ptr());
			}, py::keep_alive<1, 0>()) // keep data alive while Abc_Obj_t is alive
		.def("Data", [](Abc_Obj_t * self) {
				PyObject* d = (PyObject*) Abc_ObjData(self);
				if (d == nullptr)
					return py::reinterpret_borrow<py::object>(py::none());
				return py::reinterpret_borrow<py::object>(d);
			}, py::return_value_policy::reference)
		.def("IterFanin", [](Abc_Obj_t &self) {
	 			return py::make_iterator(Abc_ObjFaninIterator(self), Abc_ObjFaninIterator(self, Abc_ObjFaninNum(&self)));
	 	 	 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("__repr__", &__repr__Abc_ObjPrint)
		.def("__eq__", [](Abc_Obj_t * self, Abc_Obj_t * other) {
			return self == other;
		})
		.def("__hash__", [](Abc_Obj_t* self) {
			return (std::intptr_t) self;
		});

	//py::capsule cleanup(m, [](PyObject *) { Abc_Stop(); });
	//m.add_object("_cleanup", cleanup);
}
}
