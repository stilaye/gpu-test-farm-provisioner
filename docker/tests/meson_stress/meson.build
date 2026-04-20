project('cuda_stress_runner', 'c',
  version : '1.0',
  default_options : ['c_std=c11'])

m_dep = meson.get_compiler('c').find_library('m')

executable('cuda_stress_runner',
  'cuda_stress_runner.c',
  dependencies : m_dep,
  install : true)
