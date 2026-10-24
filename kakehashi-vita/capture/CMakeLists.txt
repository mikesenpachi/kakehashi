cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "toolchain file")
endif()

project(kakehashi C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)

# gnu17: taiHEN's TAI_CONTINUE casts to type(*)(), which means "no arguments" in C23 (the GCC 15 default).
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -std=gnu17 -Wl,-q -Wall -O2 -nostdlib")

add_executable(kakehashi main.c buttons.c frame.c bmp.c notice.c config.c)
target_link_libraries(kakehashi
  SceCtrlForDriver_stub
  SceDisplayForDriver_stub
  SceIofilemgrForDriver_stub
  SceRtcForDriver_stub
  SceSysclibForDriver_stub
  SceSysmemForDriver_stub
  SceSysrootForKernel_stub
  SceThreadmgrForDriver_stub
  taihenForKernel_stub
)

vita_create_self(kakehashi.skprx kakehashi CONFIG exports.yml UNSAFE)
