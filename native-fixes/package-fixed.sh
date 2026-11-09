#!/usr/bin/env bash
set -euo pipefail
engine_root=/home/liumeng/UnrealEngine_4.26
objcopy="$engine_root/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v17_clang-10.0.1-centos7/x86_64-unknown-linux-gnu/bin/llvm-objcopy"
mkdir -p /fixes/packaged
"$objcopy" --only-keep-debug /fixes/CarlaUE4-Linux-Shipping.full /fixes/packaged/CarlaUE4-Linux-Shipping.debug
"$objcopy" --strip-all /fixes/CarlaUE4-Linux-Shipping.full /fixes/packaged/CarlaUE4-Linux-Shipping.stripped
"$objcopy" --add-gnu-debuglink=/fixes/packaged/CarlaUE4-Linux-Shipping.debug /fixes/packaged/CarlaUE4-Linux-Shipping.stripped /fixes/packaged/CarlaUE4-Linux-Shipping
"$engine_root/Engine/Binaries/Linux/dump_syms" -c -o /fixes/Shipping-fixed.psym /fixes/staging/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping
"$engine_root/Engine/Binaries/Linux/BreakpadSymbolEncoder" /fixes/Shipping-fixed.psym /fixes/packaged/CarlaUE4-Linux-Shipping.sym
chmod 755 /fixes/packaged/CarlaUE4-Linux-Shipping
chmod 644 /fixes/packaged/CarlaUE4-Linux-Shipping.debug /fixes/packaged/CarlaUE4-Linux-Shipping.sym
