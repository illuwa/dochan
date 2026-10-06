"""Build the dependency-free PDF C accelerators only when explicitly requested."""
import os

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class AcceleratorBuildExt(build_ext):
    def build_extensions(self):
        # The interpreter and line assembly must reproduce Python's float results bit for bit,
        # so the compiler may not fuse a multiply and an add. Select by the actual compiler:
        # MinGW on Windows still takes GCC flags.
        flags = ["/fp:precise"] if self.compiler.compiler_type == "msvc" else ["-ffp-contract=off"]
        for extension in self.extensions:
            extension.extra_compile_args = list(extension.extra_compile_args or []) + flags
        super().build_extensions()


def _extension(name, sources, depends=()):
    return Extension(
        name, sources, depends=list(depends),
        optional=True, py_limited_api=True,
        define_macros=[("Py_LIMITED_API", "0x03090000")],
    )


extensions = []
if os.environ.get("DOCHAN_BUILD_ACCEL") == "1":
    extensions = [
        _extension("dochan.pdf._cscan", ["dochan/pdf/_cscan.c"]),
        _extension("dochan.pdf._cinterp", ["dochan/pdf/_cinterp.c"],
                   depends=["dochan/pdf/_cinterp_objects.h", "dochan/pdf/_cinterp_paths.h"]),
        _extension("dochan.pdf._clines", ["dochan/pdf/_clines.c"]),
    ]

setup(
    ext_modules=extensions,
    cmdclass={"build_ext": AcceleratorBuildExt} if extensions else {},
    # The sdist carries the build source; wheels carry executable packages.
    exclude_package_data={"dochan.pdf": ["_cscan.c", "_cinterp.c", "_cinterp_objects.h",
                                         "_cinterp_paths.h", "_clines.c"]},
    options={"bdist_wheel": {"py_limited_api": "cp39"}} if extensions else {},
)
