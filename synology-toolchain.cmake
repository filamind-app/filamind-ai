# CMake toolchain file for cross-compiling to Synology DVA 3221 (denverton)
# Usage: cmake -DCMAKE_TOOLCHAIN_FILE=/path/to/synology-toolchain.cmake ...

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

set(TC_ROOT $ENV{HOME}/saynologyai/toolchain/extracted/x86_64-pc-linux-gnu)
set(NAS_SYSROOT $ENV{HOME}/saynologyai/nas-sysroot)

set(CMAKE_C_COMPILER   ${TC_ROOT}/bin/x86_64-pc-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER ${TC_ROOT}/bin/x86_64-pc-linux-gnu-g++)
set(CMAKE_AR           ${TC_ROOT}/bin/x86_64-pc-linux-gnu-ar)
set(CMAKE_RANLIB       ${TC_ROOT}/bin/x86_64-pc-linux-gnu-ranlib)
set(CMAKE_STRIP        ${TC_ROOT}/bin/x86_64-pc-linux-gnu-strip)

# Use Synology toolchain sysroot for system headers/libs
set(CMAKE_SYSROOT ${TC_ROOT}/x86_64-pc-linux-gnu/sys-root)

# Search NAS sysroot for NVIDIA libs but use toolchain sysroot for everything else
set(CMAKE_FIND_ROOT_PATH ${TC_ROOT}/x86_64-pc-linux-gnu/sys-root ${NAS_SYSROOT})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)

# Tell linker to use NAS CUDA libs
set(CMAKE_EXE_LINKER_FLAGS_INIT "-L${NAS_SYSROOT}/cuda/lib64 -L${NAS_SYSROOT}/usr/lib -Wl,-rpath-link,${NAS_SYSROOT}/cuda/lib64:${NAS_SYSROOT}/usr/lib")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-L${NAS_SYSROOT}/cuda/lib64 -L${NAS_SYSROOT}/usr/lib -Wl,-rpath-link,${NAS_SYSROOT}/cuda/lib64:${NAS_SYSROOT}/usr/lib")
