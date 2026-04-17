cmake_minimum_required(VERSION 3.14)
project(ble_scanner VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -DDEBUG")
set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")

# Find required packages
find_package(PkgConfig REQUIRED)
pkg_check_modules(DBUS REQUIRED dbus-1)
pkg_check_modules(GLIB REQUIRED glib-2.0)

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${DBUS_INCLUDE_DIRS}
    ${GLIB_INCLUDE_DIRS}
)

# Source files
set(SOURCES
    src/main.cpp
    src/ble_scanner.cpp
    src/device_parser.cpp
    src/deduplicator.cpp
    src/logger.cpp
)

# Executable
add_executable(ble_scanner ${SOURCES})

# Link libraries
target_link_libraries(ble_scanner
    ${DBUS_LIBRARIES}
    ${GLIB_LIBRARIES}
    pthread
)

# Compiler warnings
target_compile_options(ble_scanner PRIVATE -Wall -Wextra -Wpedantic)

# Install
install(TARGETS ble_scanner DESTINATION bin)

# Output directory
set_target_properties(ble_scanner PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)
