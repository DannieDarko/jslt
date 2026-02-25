from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")
setup(
  name="JSLT",
  version="1.1.0",
  description="JSON transformation tool",
  long_description=long_description,
  long_description_content_type="text/markdown",
  package_dir={"": "src"},
  packages=find_packages(where="src"),
)