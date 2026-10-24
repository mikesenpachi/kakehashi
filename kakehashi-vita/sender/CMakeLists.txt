cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "toolchain file")
endif()

project(kakehashi_sender C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -std=gnu17 -Wl,-q -Wall -O2 -nostdlib")

add_executable(kakehashi_sender main.c)
target_link_libraries(kakehashi_sender
  SceIofilemgr_stub
  SceKernelThreadMgr_stub
  SceLibKernel_stub
  SceNet_stub_weak
  SceNetCtl_stub_weak
)

# UNSAFE: the safe build did not run in SceShell. shellbat, pngshot and henkaku are all unsafe.
vita_create_self(kakehashi_sender.suprx kakehashi_sender CONFIG exports.yml UNSAFE)
