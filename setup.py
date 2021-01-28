import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='cats-python',
    author='Adam Bright',
    author_email='adam.brian.bright@gmail.com',
    description='Python 3.8 Cifrazia Action Transport System',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/AdamBrianBright/cats-python',
    packages=setuptools.find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    install_requires=[
        "tornado >= 3.8",
        "ujson >= 4.0.1",
    ],
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    classifiers=[
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
)
