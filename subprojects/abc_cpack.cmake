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

include(CPack)
