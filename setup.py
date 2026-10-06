"""Build dependency-free PDF accelerators only when explicitly requested."""
import os

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class PDFBuildExt(build_ext):
    def build_extensions(self):
        # Select by the actual compiler: MinGW on Windows still uses GCC flags.
        for extension in self.extensions:
            if extension.name == "dochan.pdf._cinterp":
                extension.extra_compile_args = (["/fp:precise"]
                                                if self.compiler.compiler_type == "msvc"
                                                else ["-ffp-contract=off"])
        super().build_extensions()


extensions = []
if os.environ.get("DOCHAN_BUILD_ACCEL") == "1":
    extensions.append(Extension(
        "dochan.pdf._cscan", ["dochan/pdf/_cscan.c"],
        optional=True, py_limited_api=True,
        define_macros=[("Py_LIMITED_API", "0x03090000")],
    ))

    extensions.append(Extension(
        "dochan.pdf._cinterp", ["dochan/pdf/_cinterp.c"],
        depends=["dochan/pdf/_cinterp_objects.h", "dochan/pdf/_cinterp_paths.h"],
        optional=True, py_limited_api=True,
        define_macros=[("Py_LIMITED_API", "0x03090000")],
    ))

setup(
    ext_modules=extensions,
    cmdclass={"build_ext": PDFBuildExt} if extensions else {},
    # The sdist carries the build source; wheels carry executable packages.
    exclude_package_data={"dochan.pdf": ["_cscan.c", "_cinterp.c", "_cinterp_objects.h", "_cinterp_paths.h"]},
    options={"bdist_wheel": {"py_limited_api": "cp39"}} if extensions else {},
)
