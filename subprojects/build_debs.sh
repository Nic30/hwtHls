#!/bin/bash

SUBPROJECTS_DIR=$PWD
ABC_ROOT="$SUBPROJECTS_DIR/berkeley-abc"

ABC_REPO_URL="https://github.com/berkeley-abc/abc.git"
#ABC_LATEST_VER=$(git ls-remote $ABC_REPO_URL HEAD | awk '{ print $1}')
#ABC_LATEST_VER=$(git rev-parse --short $ABC_LATEST_VER)
if [ ! -d "$ABC_ROOT" ] ; then
    git clone "$ABC_REPO_URL" "$ABC_ROOT"
fi

cd "$ABC_ROOT"
if [ ! -d "build" ] ; then
    mkdir "build"
fi

# append CPack related if not already appended
last_line=$(tail -n 1 "CMakeLists.txt")
if [ "$last_line" != "include(\${CMAKE_CURRENT_SOURCE_DIR}/abc_cpack.cmake)" ]; then
   echo "include(\${CMAKE_CURRENT_SOURCE_DIR}/abc_cpack.cmake)" >> CMakeLists.txt
fi
cp ../abc_cpack.cmake .
cp ../abc_pkgconfig.pc.in .

# https://cmake.org/cmake/help/book/mastering-cmake/chapter/Packaging%20With%20CPack.html
cd "build"
VERSION=$(git rev-parse --short HEAD)
cmake -G Ninja \
 -DABC_SKIP_TESTS=1 \
 -DCPACK_PACKAGE_VERSION="$VERSION" \
 .. 

ninja libabc-pic
cpack -G DEB

if [ ! -d "$SUBPROJECTS_DIR/DEB" ] ; then
    mkdir "$SUBPROJECTS_DIR/DEB"
fi
cp $ABC_ROOT/build/libabc-dev-$VERSION-Linux.deb $SUBPROJECTS_DIR/DEB
