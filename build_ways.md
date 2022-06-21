#### OpenImageIO
```
cmake .. -DCMAKE_INSTALL_PREFIX=C:\oiio -DUSE_PYTHON=1 -DBUILD_SHARED_LIBS=1 -Dpybind11_ROOT=C:\pybind11 -DOpenEXR_ROOT=C:\openexr -DImath_ROOT=C:\openexr -DIlmBase_ROOT=C:\openexr -DOpenVDB_ROOT=C:\openvdb
```
---

#### OpenVDB
```
cmake .. -DCMAKE_INSTALL_PREFIX=C:\openvdb -DTBB_ROOT=C:\tbb -DOPENVDB_BUILD_PYTHON_MODULE=ON
```
---

#### Boost
```
b2 install --prefix=C:\boost --threading=multi --address-model=64 --variant=debug,release --toolset=msvc runtime-link=static,shared link=static,shared
```