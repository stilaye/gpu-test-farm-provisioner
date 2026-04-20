cmake_minimum_required(VERSION 3.16)
project(cuda_validator C)

set(CMAKE_C_STANDARD 11)

add_executable(cuda_math_validator cuda_math_validator.c)
target_link_libraries(cuda_math_validator m)

# If real CUDA were available:
# find_package(CUDAToolkit REQUIRED)
# target_link_libraries(cuda_math_validator CUDA::cudart CUDA::cublas)

install(TARGETS cuda_math_validator DESTINATION /usr/local/bin)
