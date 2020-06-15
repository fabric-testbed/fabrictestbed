import setuptools

VERSION = "0.0.1"

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='fabric-cli',
    version=VERSION,
    author="Erica Fu",
    author_email="ericafu@renci.org",
    description="FABRIC Testbed Python Client Library with CLI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fabric-testbed/fabric-cli",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'fabric_credmgr'
    ],
    entry_points='''
        [console_scripts]
        fabric-cli=fabric.cli:cli
    ''',
    classifiers=[
                  "Programming Language :: Python :: 3",
                  "License :: OSI Approved :: MIT License",
                  "Operating System :: OS Independent",
              ],
    python_requires='>=3.6',
)



