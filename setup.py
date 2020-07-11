import os

from setuptools import setup


def readme():
    readme_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md")

    with open(readme_path, encoding="utf-8") as f:
        return f.read()


setup(
    name="smalld-click",
    description="Add Click support to your SmallD bot.",
    long_description=readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/aymanizz/smalld-click",
    author="Ayman Izzeldin",
    author_email="ayman.izzeldin@gmail.com",
    license="MIT",
    packages=["smalld_click"],
    use_scm_version=True,
    install_requires=["smalld>=0.1.4", "click>=7.1.2"],
    setup_requires=["setuptools-scm==4.1.2"],
    classifiers=[
        "Development Status :: 1 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
