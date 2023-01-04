import setuptools
from fabrictestbed import __VERSION__


with open("README.md", "r") as fh:
    long_description = fh.read()

with open("requirements.txt", "r") as fh:
    requirements = fh.read()

setuptools.setup(
    name='fabrictestbed',
    version=__VERSION__,
    author="Erica Fu, Komal Thareja",
    author_email="ericafu@renci.org, kthare10@unc.edu",
    description="FABRIC Python Client Library with CLI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fabric-testbed/fabric-cli",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        "test": ["pytest"],
    },
    entry_points='''
        [console_scripts]
        fabric-cli=fabrictestbed.cli.cli:cli
    ''',
    classifiers=[
                  "Programming Language :: Python :: 3",
                  "License :: OSI Approved :: MIT License",
                  "Operating System :: OS Independent",
              ],
    python_requires='>=3.9',
)



