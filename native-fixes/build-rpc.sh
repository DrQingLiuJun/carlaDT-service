#!/usr/bin/env bash
set -euo pipefail
mkdir -p /fixes/rpc-build
cd /fixes/rpc-build
cmake /fixes/rpclib -G Ninja -DCMAKE_C_COMPILER=/usr/bin/clang-8 -DCMAKE_CXX_COMPILER=/usr/bin/clang++-8 -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS='-fPIC -std=c++14 -stdlib=libc++ -I/src/carla/Build/llvm-8.0-install/include/c++/v1 -DBOOST_NO_EXCEPTIONS -DASIO_NO_EXCEPTIONS' -DCMAKE_EXE_LINKER_FLAGS='-L/src/carla/Build/llvm-8.0-install/lib' -DRPCLIB_BUILD_TESTS=OFF -DRPCLIB_BUILD_EXAMPLES=OFF
cmake --build /fixes/rpc-build -- -j4
bash /fixes/test-close.sh /fixes/rpc-build/librpc.a /fixes/test_close_fixed
