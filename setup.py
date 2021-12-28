# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

install_requires = []
with open("requirements.txt") as f:
    for line in f:
        install_requires.append(line.strip())

setup(
    name="cpqdtrd",
    version="0.1.0",
    description="CPqD Dialog Transcription Client",
    install_requires=install_requires,
    author="Akira Miasato",
    author_email="valterf@cpqd.com.br",
    packages=find_packages(),
)
