cmake_minimum_required(VERSION 3.28)

project(
  newromancer
  VERSION 0.0.1
  LANGUAGES C CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_COLOR_DIAGNOSTICS ON)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Repo-root compile_commands.json symlink, refreshed to this build's database on every
# configure. clangd finds a database by walking up from the source file, so the root link
# makes the last-configured build the one code intelligence follows. A regular file at the
# link path is left in place; only a symlink or nothing gets replaced.
set(NEWROMANCER_CCDB_LINK ${CMAKE_SOURCE_DIR}/compile_commands.json)
if(IS_SYMLINK ${NEWROMANCER_CCDB_LINK} OR NOT EXISTS ${NEWROMANCER_CCDB_LINK})
  file(REMOVE ${NEWROMANCER_CCDB_LINK})
  file(CREATE_LINK ${CMAKE_BINARY_DIR}/compile_commands.json ${NEWROMANCER_CCDB_LINK} SYMBOLIC)
else()
  message(WARNING "compile_commands.json at the repo root is a regular file; leaving it in place "
                  "instead of relinking it to ${CMAKE_BINARY_DIR}.")
endif()

option(NEWROMANCER_BUILD_TESTS "Build the GoogleTest suite" ON)
set(NEWROMANCER_ADF
    "${CMAKE_CURRENT_LIST_DIR}/assets/Neuromancer.adf"
    CACHE FILEPATH "Original disk image used by the tests that need the game's files")

set(COMMON_SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/src)

include(FetchContent)

# A commit, not a branch: a pinned commit cannot be fetched shallow.
set(ADFLIB_ENABLE_TESTS
    OFF
    CACHE BOOL "Enable tests" FORCE)
set(ADFLIB_ENABLE_NATIVE_DEV
    OFF
    CACHE BOOL "Enable native devices" FORCE)
FetchContent_Declare(
  ADFlib
  GIT_REPOSITORY https://github.com/zakgi/ADFlib
  GIT_TAG 284eb9f3178120cafe4b7a7e7fb69d09791d2f82
  EXCLUDE_FROM_ALL SYSTEM)
FetchContent_MakeAvailable(ADFlib)

FetchContent_Declare(
  SFML
  GIT_REPOSITORY https://github.com/SFML/SFML.git
  GIT_TAG 3.1.0
  GIT_SHALLOW ON
  EXCLUDE_FROM_ALL SYSTEM)
FetchContent_MakeAvailable(SFML)

set(ARGS_BUILD_EXAMPLE
    OFF
    CACHE BOOL "Build example" FORCE)
set(ARGS_BUILD_UNITTESTS
    OFF
    CACHE BOOL "Build unittests" FORCE)
FetchContent_Declare(
  args
  GIT_REPOSITORY https://github.com/Taywee/args
  GIT_TAG 6.4.7
  GIT_SHALLOW ON
  EXCLUDE_FROM_ALL)
FetchContent_MakeAvailable(args)

FetchContent_Declare(
  spdlog
  GIT_REPOSITORY https://github.com/gabime/spdlog
  GIT_TAG v1.15.3
  GIT_SHALLOW ON
  EXCLUDE_FROM_ALL)
FetchContent_MakeAvailable(spdlog)

# Host-side reading of the disk image and decoding of the original files (std allowed).
add_library(newromancer_host STATIC src/host/adf.cpp src/host/format/huffman.cpp src/host/format/offset_table.cpp
                                    src/host/format/picture.cpp)
target_include_directories(newromancer_host PUBLIC ${COMMON_SOURCE_DIR})
target_link_libraries(newromancer_host PUBLIC spdlog::spdlog adf)

add_executable(newromancer src/main.cpp)
target_link_libraries(newromancer PRIVATE newromancer_host SFML::Graphics args spdlog::spdlog)

# No RTTI anywhere (docs/coding-style.md). Exceptions stay enabled only where third-party
# libraries need them: the executable (args, SFML) and the tests (GoogleTest).
foreach(target newromancer newromancer_host)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive- /GR-)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -fno-rtti)
  endif()
endforeach()

if(NEWROMANCER_BUILD_TESTS)
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest
    GIT_TAG v1.17.0
    GIT_SHALLOW ON
    EXCLUDE_FROM_ALL)
  set(INSTALL_GTEST
      OFF
      CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  enable_testing()
  include(GoogleTest)

  add_executable(newromancer_tests test/format/huffman_test.cpp test/format/offset_table_test.cpp
                                   test/format/picture_test.cpp test/host/adf_test.cpp)
  target_include_directories(newromancer_tests PRIVATE ${CMAKE_CURRENT_LIST_DIR}/test)
  target_compile_definitions(newromancer_tests PRIVATE NEWROMANCER_ADF="${NEWROMANCER_ADF}")
  target_link_libraries(newromancer_tests PRIVATE newromancer_host GTest::gtest_main)
  if(NOT MSVC)
    target_compile_options(newromancer_tests PRIVATE -Wall -Wextra -Wpedantic -fno-rtti)
  endif()
  gtest_discover_tests(newromancer_tests)
endif()
