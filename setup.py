from setuptools import setup

setup(name="memorize",
      license="MIT",
      packages=["memorize"],
      install_requires=[
          'contractions',
          'vosk',
          'nltk',
          'cattrs',
          'pendulum',
          'click',
          'fuzzy',
          'metaphone',
          'fuzzywuzzy',
      ])
