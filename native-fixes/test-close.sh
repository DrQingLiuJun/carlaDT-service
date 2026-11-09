#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
rpc_library="${1:-/src/carla/Unreal/CarlaUE4/Plugins/Carla/CarlaDependencies/lib/librpc.a}"
output_name="${2:-/fixes/test_close_old}"
clang++-8 -std=c++14 -stdlib=libc++ -DBOOST_NO_EXCEPTIONS -DASIO_NO_EXCEPTIONS -DASIO_STANDALONE -DRPCLIB_ASIO=clmdep_asio -DRPCLIB_FMT=clmdep_fmt -I/fixes/rpclib/include -I/fixes/rpclib/dependencies/include -isystem /src/carla/Build/llvm-8.0-install/include/c++/v1 /fixes/test_close.cpp "$rpc_library" -L/src/carla/Build/llvm-8.0-install/lib -Wl,-rpath,/src/carla/Build/llvm-8.0-install/lib -lc++ -lc++abi -pthread -o "$output_name"
"$output_name"
