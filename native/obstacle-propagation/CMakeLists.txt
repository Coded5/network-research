build_lib(
  LIBNAME obstacle-propagation
  SOURCE_FILES
    model/obstacle-propagation-loss-model.cc
  HEADER_FILES
    model/obstacle-propagation-loss-model.h
  LIBRARIES_TO_LINK ${libpropagation} ${libmobility}
)
