"""Build the dependency-free C scanner only when explicitly requested."""
import os

from setuptools import Extension, setup


extensions = []
if os.environ.get("DOCHAN_BUILD_ACCEL") == "1":
    extensions.append(Extension(
        "dochan.pdf._cscan", ["dochan/pdf/_cscan.c"],
        optional=True, py_limited_api=True,
        define_macros=[("Py_LIMITED_API", "0x03090000")],
    ))

setup(
    ext_modules=extensions,
    # The sdist carries the build source; wheels carry executable packages.
    exclude_package_data={"dochan.pdf": ["_cscan.c"]},
    options={"bdist_wheel": {"py_limited_api": "cp39"}} if extensions else {},
)
