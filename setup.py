"""uWeb3 cms installer."""

import os
import re
from setuptools import setup, find_packages

REQUIREMENTS = [
    'uwebthree',
    'marko',
    'passlib'
]

def Description():
  """Returns the contents of the README.md file as description information."""
  with open(os.path.join(os.path.dirname(__file__), 'README.md')) as r_file:
    return r_file.read()


def Version():
  """Returns the version of the library as read from the __init__.py file"""
  main_lib = os.path.join(os.path.dirname(__file__), 'uweb3cms', 'base', '__init__.py')
  with open(main_lib) as v_file:
    return re.match(".*__version__ = '(.*?)'", v_file.read(), re.S).group(1)


setup(
    name='uWeb3 cms',
    version=Version(),
    description='uWeb, python3, uswgi compatible headless cms',
    long_description=Description(),
    long_description_content_type='text/markdown',
    license='ISC',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Environment :: Web Environment',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Operating System :: POSIX :: Linux',
    ],
    author='Jan Klopper',
    author_email='jan@underdark.nl',
    url='https://github.com/underdarknl/uweb3cms',
    keywords='headless cms based on uWeb3',
    packages=find_packages(),
    include_package_data=True,
    install_requires=REQUIREMENTS,
    python_requires='>=3.5')
