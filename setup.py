#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='annexremote-openneuro',
      version='0',
      description='Git Annex plugin for https://openneuro.org',
      author='Nick Guenther',
      author_email='nguenthe@uwaterloo.ca',
      url='https://github.com/kousu/annexremote-openneuro', # TODO: import to /neuropoly ?
      license='MIT',
      python_requires='>=3.6.0',
      install_requires=[
        'requests>=2.0.0',
        'annexremote>=1.4.0', # TODO: maybe this can be an older version?
      ],
      packages=find_packages(),
      # https://setuptools.readthedocs.io/en/latest/setuptools.html#automatic-script-creation
      #entry_points={
      #  'console_scripts': [
      #    'git-annex-remote-openneuro=git_annex_remote_openneuro.remote:main',
      #  ]}
      # I don't need this the setuptools gunk. What happened to "there should only be one way to do it?"
      scripts=['git-annex-remote-openneuro',
               'openneuro-cli']
     )
