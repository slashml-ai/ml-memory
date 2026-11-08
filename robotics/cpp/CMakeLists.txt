cmake_minimum_required(VERSION 3.14)
project(slashml_robotics_cpp VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(slashml_robotics INTERFACE)
target_include_directories(slashml_robotics INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

enable_testing()
add_executable(test_robotics_client tests/test_client.cpp)
target_link_libraries(test_robotics_client PRIVATE slashml_robotics)
add_test(NAME test_robotics_client COMMAND test_robotics_client)
