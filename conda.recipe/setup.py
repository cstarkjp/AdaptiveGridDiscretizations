import setuptools

with open("README.md", "r") as fh:
	long_description = fh.read()

setuptools.setup(
	name='agd',  
	version='0.1.5',
	author="Jean-Marie Mirebeau",
	author_email="jm.mirebeau@gmail.com",
	description="Adaptive Grid Discretizations",
	long_description=long_description,
	long_description_content_type="text/markdown",
	url="https://github.com/Mirebeau/AdaptiveGridDiscretizations/",
	packages=setuptools.find_packages(),
	platforms=["any"],
	classifiers=[
		"Programming Language :: Python :: 3",
		"License :: OSI Approved :: Apache Software License",
		"Operating System :: OS Independent",
	],
)
	