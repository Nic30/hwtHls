
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
SET(PKG_CONFIG_REQUIRES libreadline-dev)
SET(PKG_CONFIG_LIBDIR
    "\${prefix}/lib"
)
SET(PKG_CONFIG_INCLUDEDIR
    "\${prefix}/include/abc"
)
SET(PKG_CONFIG_LIBS
    "-L\${libdir} -labc"
)
SET(PKG_CONFIG_CFLAGS
    "-I\${includedir}"
)
set(PKG_CONFIG_FILE_NAME "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.pc")
configure_file("${CMAKE_SOURCE_DIR}/abc_pkgconfig.pc.in" "${PKG_CONFIG_FILE_NAME}" @ONLY)
INSTALL(FILES "${PKG_CONFIG_FILE_NAME}"
        DESTINATION lib/pkgconfig)

include(CPack)
