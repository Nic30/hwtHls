
# begin onf abc_cpack.cmake

file(GLOB_RECURSE LIBABC_INCLUDE_FILES "src/*.h*")
# https://stackoverflow.com/a/59257505
#set_target_properties(libabc-pic  # this method does not preserve include folder hierarchy
#    PROPERTIES
#    PUBLIC_HEADER "${LIBABC_INCLUDE_FILES}"
#)
install(TARGETS libabc-pic
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    # PUBLIC_HEADER DESTINATION include/abc
)
# Install the headers, preserving the directory structure
foreach(header ${LIBABC_INCLUDE_FILES})
    # Get the directory structure relative to the 'src' folder
    get_filename_component(header_dir "${header}" DIRECTORY)
    string(REPLACE "${CMAKE_SOURCE_DIR}/src" "" relative_dir "${header_dir}")

    # Install the header to the appropriate directory under 'include/abc'
    install(FILES ${header} DESTINATION include/abc${relative_dir})
endforeach()


# pkg-config related
# based on https://www.kaizou.org/2014/11/typical-cmake-project.html#exporting-dependencies-towards-external-packages
#          https://github.com/p-ranav/argparse/blob/master/CMakeLists.txt
set(CPACK_PACKAGING_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}") # to make sure it is the same in abc.pc and deb

set(CPACK_PACKAGE_NAME "libabc-dev")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "ABC System for Sequential Logic Synthesis and Formal Verification (build for hwtHls)")
set(CPACK_PACKAGE_VENDOR "nic30")
set(CPACK_PACKAGE_CONTACT "Nic30original@gmail.com")
set(CPACK_DEBIAN_PACKAGE_DEPENDS "libreadline-dev")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_SOURCE_DIR}/copyright.txt")
set(CPACK_RESOURCE_FILE_README "${CMAKE_SOURCE_DIR}/README.md")

SET(PKG_CONFIG_REQUIRES readline)
SET(PKG_CONFIG_LIBDIR     "\${prefix}/lib")
SET(PKG_CONFIG_INCLUDEDIR "\${prefix}/include/abc")
SET(PKG_CONFIG_LIBS       "-L\${libdir} -labc-pic")

# https://stackoverflow.com/questions/56104607/how-to-print-current-compilation-flags-that-are-set-with-target-compile-options
# Convert the list of CXX flags into a space-separated string
string(REPLACE ";" " " LIBABC_PIC_FLAGS_STR "${ABC_CFLAGS} ${ABC_CXXFLAGS}")
string(REPLACE "-std=c++17 -fno-exceptions" "" LIBABC_PIC_FLAGS_STR "${LIBABC_PIC_FLAGS_STR}")
string(REPLACE "-Wall -Wno-unused-function -Wno-write-strings -Wno-sign-compare" "" LIBABC_PIC_FLAGS_STR "${LIBABC_PIC_FLAGS_STR}")

SET(PKG_CONFIG_CFLAGS     "-I\${includedir} ${LIBABC_PIC_FLAGS_STR}")
set(PKG_CONFIG_FILE_NAME "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.pc")

configure_file("${CMAKE_SOURCE_DIR}/abc_pkgconfig.pc.in" "${PKG_CONFIG_FILE_NAME}" @ONLY)
INSTALL(FILES "${PKG_CONFIG_FILE_NAME}"
        DESTINATION lib/pkgconfig)

include(CPack)
