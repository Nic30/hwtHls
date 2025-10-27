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
if [ "$last_line" != "include(CPack)" ]; then
   cat "$SUBPROJECTS_DIR/abc_cpack.cmake" >> CMakeLists.txt
fi

# https://cmake.org/cmake/help/book/mastering-cmake/chapter/Packaging%20With%20CPack.html
cd "build"
VERSION=$(git rev-parse --short HEAD)
cmake -G Ninja \
 -DABC_SKIP_TESTS=1 \
 -DCPACK_PACKAGE_NAME="libabc-dev" \
 -DCPACK_PACKAGE_DESCRIPTION_SUMMARY="ABC: System for Sequential Logic Synthesis and Formal Verification (build for hwtHls)" \
 -DCPACK_PACKAGE_VENDOR="nic30" \
 -DCPACK_PACKAGE_CONTACT="Nic30original@gmail.com" \
 -DCPACK_PACKAGE_VERSION="$VERSION" \
 -DCPACK_DEBIAN_PACKAGE_DEPENDS=libreadline-dev \
 -DCPACK_RESOURCE_FILE_LICENSE="$ABC_ROOT/copyright.txt" \
 -DCPACK_RESOURCE_FILE_README="$ABC_ROOT/README.md" \
 .. 
#               -DCPACK_DEBIAN_PACKAGE_NAME=berkeley-abc\

ninja libabc-pic
cpack -G DEB

if [ ! -d "$SUBPROJECTS_DIR/DEB" ] ; then
    mkdir "$SUBPROJECTS_DIR/DEB"
fi
$PROJECTS_DIR=$SUBPROJECTS_DIR/../DEB
cp $ABC_ROOT/build/libabc-dev-$VERSION-Linux.deb $SUBPROJECTS_DIR/DEB
