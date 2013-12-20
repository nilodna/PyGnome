# GNOME2 #

## [Project Documentation](http://noaa-orr-erd.github.io/GNOME2/) ##
## [FAQ -- Troubleshoot](https://github.com/NOAA-ORR-ERD/GNOME2/wiki/FAQ---Troubleshoot) ##

<img src="http://gnome.orr.noaa.gov/py_gnome_testdata/GnomeIcon128.png" alt="Gnome Logo" title="Gnome" align="right">

The General NOAA Operational Modeling Environment.

GNOME ( General NOAA Operational Modeling Environment ) is a modeling tool
developed by the National Oceanic and Atmospheric Administration (NOAA),
Office of Response and Restoration (ORR), Emergency Response Division.


It is designed to support oil and other hazardous material spills in the coastal environment.

This repository contains the source code to the currently under-development version of the model.

**This is code that is under active development -- it should not be considered endorsed or supported by NOAA for any use.**

For a supported version, please see our main web site:  
http://response.restoration.noaa.gov/gnome

## Installation in Development Mode ##

Since this is development work, it might be good to create and run this in a virtual environment.
[Virtual env](http://www.virtualenv.org/en/latest/) and 
[Virtual env wrapper](http://virtualenvwrapper.readthedocs.org/en/latest/) eases management of virtual environments.

A virtualenv is *not required* to run PyGnome or WebGnome.
Depending on your access level/permissions, you may require a virtualenv if you cannot 
install python packages in the global site-packages. 

### Linux (Tested in 32-bit, raring 13.04) ###

- PyGnome uses NetCDF and also currently uses PIL. 
- WebGnome requires libxml and npm.

For Linux use appropriate package manager (apt-get on ubuntu) to download/install binary dependencies.

#### Binary Dependencies ####

1. Python Imaging Library (PIL) requires:  
    `$ sudo apt-get install libjpeg-dev libfreetype6-dev zlib1g-dev`
   
   Use apt-get to build dependencies for PIL  
    `$ sudo apt-get install build-dep python-imaging`

   This did not build symlinks to libraries for me in /usr/lib, so had to
   manually create them:  
```
    $ sudo ln -s /usr/lib/`uname -i`-linux-gnu/libfreetype.so /usr/lib/  
    $ sudo ln -s /usr/lib/`uname -i`-linux-gnu/libjpeg.so /usr/lib/  
    $ sudo ln -s /usr/lib/`uname -i`-linux-gnu/libz.so /usr/lib/  
```
    
2. netCDF4 python module requires NetCDF libraries: libhdf5-serial-dev, libnetcdf-dev

3. libxml used by webgnome requires: libxml2-dev, libxslt1-dev

4. npm is a javascript package manager used by webgnome

```
    $ sudo apt-get install libhdf5-serial-dev libnetcdf-dev libxml2-dev libxslt1-dev npm
```

5. The following python packages, documented in PyGnome's requirements.txt,
   may need to be manually installed. Binaries for 
   [Numpy](http://packages.ubuntu.com/raring/python/python-numpy) and 
   [Cython](http://packages.ubuntu.com/raring/python/cython) can be installed using apt-get. 
   Current binaries for these are sufficiently new: (Numpy >=1.7.0) and (Cython >= 0.17.1).  

   If you use virtualenv and apt-get to install these system site packages.
   Remember to use the [--system-site-packages](https://pypi.python.org/pypi/virtualenv)
   option when creating a new virtualenv so the system packages are available in the virtualenv.

   Alternatively, pip install should also work. 
   The following builds the latest packages in your virtualenv once the above dependencies are met.
   ```
        $ pip install numpy
        $ pip install cython
        $ pip install netCDF4
        $ pip install PIL
   ```

6. python-cjson is a webgnome dependency that can be pip installed. Currently commented in requirements.txt

The remaining dependencies are python packages and can be installed using pip install -r requirements.txt  
See [Build PyGnome/WebGnome](https://github.com/NOAA-ORR-ERD/GNOME2#build-pygnomewebgnome) section below.

### Windows 7 (32-bit, using VS-2008 express edition) ###

- PyGnome requires PIL. 
  It statically links against netcdf-3, included with PyGnome source code

Binary dependencies for PyGnome are obtained from
[Chris Gohlke's website](http://www.lfd.uci.edu/~gohlke/pythonlibs/).

#### Binary Dependencies ####

Download and install the newest Windows executable distribution of [Python 2.7](http://www.python.org/download/)
(*note: we are not quite ready for Python 3.0*)
Make sure the distribution is named consistently with the Python environment you desire.
For example, binaries ending in *win32-py2.7.exe are for Python 2.7.* (32-bit)

There exist some packages that GNOME depends on that have very complex and brittle build processes,
or that have unreasonable build dependencies.
Fortunately, [Chris Gohlke's website](http://www.lfd.uci.edu/~gohlke/pythonlibs/) contains pre-compiled binary distributions
for many of these packages.  
*(The full list of dependent packages and their minimum versions can be found in the file
 GNOME2/py_gnome/requirements.txt)*

Here are the binary packages we need:

1. [setuptools](http://www.lfd.uci.edu/~gohlke/pythonlibs/#setuptools)
2. [pip](http://www.lfd.uci.edu/~gohlke/pythonlibs/#pip)  
   At this point, we should test that pip is installed correctly - on command line invoke the following pip commands.  
   These should show usage information for 'pip', and then a list of installed packages.
   ```
       $ pip
       Usage:
         pip <command> [options]

       Commands:
         install                     Install packages.
         ...
   ```
   ```
       $ pip list
       pip (1.4.1)
       setuptools (1.1.4)
   ```
3. [numpy-MKL](http://www.lfd.uci.edu/~gohlke/pythonlibs/#numpy)
4. [Cython](http://www.lfd.uci.edu/~gohlke/pythonlibs/#cython)
5. Install [PIL](http://www.pythonware.com/products/pil/) instead of Pillow
6. 32-bit 1.0.6 version of [netCDF4](http://www.lfd.uci.edu/~gohlke/pythonlibs/#netcdf4)
7. [lxml] (http://www.lfd.uci.edu/~gohlke/pythonlibs/#lxml) - required for webgnome
8. [python-cjson] (http://www.lfd.uci.edu/~gohlke/pythonlibs/#python-cjson) - required for webgnome

The remaining dependencies are python packages and can be installed using the command:
`pip install -r requirements.txt`

See [Build PyGnome/WebGnome](https://github.com/NOAA-ORR-ERD/GNOME2#build-pygnomewebgnome) section below.

### Windows 7 (64-bit, using VS-2008 express edition) ###

Building GNOME for 64 bit Windows is similar to the 32 bit Windows build, and has similar
binary dependencies.
There are however some extra steps you need to perform in order to build py_gnome.

If you are not on a 64 bit Windows system, you may skip forward to the section
[Build PyGnome/WebGnome](https://github.com/NOAA-ORR-ERD/GNOME2#build-pygnomewebgnome)

1. Download and install the windows SDK.  Here is the link that we are using:  
   [Microsoft Windows SDK for Windows 7 and .NET Framework 3.5 SP1](http://www.microsoft.com/en-us/download/details.aspx?id=3138)

2. Start the Windows SDK command window.  
   From your Windows Desktop, select:  
   **`Start`->`All Programs`->`Microsoft Windows SDK v7.0`->`CMD Shell`**

   The title of your command window should read:  
   **'Microsoft Windows 7 x64 DEBUG Build Environment'**

3. Inside your x64 Build Console:
   run the command `"\Program Files (x86)\Microsoft Visual Studio 9.0\VC\bin\vcvars64.bat"`  
   This sets up the environment variables needed for 64 bit compilation.

4. Stay inside this Build console for all further build actions.

### Build PyGnome/WebGnome ###

1. Clone the GNOME2 repository.  
```
    $ git clone https://github.com/NOAA-ORR-ERD/GNOME2.git  
```


2. pip install all of GNOME's python package dependencies.
```
    $ cd GNOME2/py_gnome
    $ pip install -r requirements.txt
```

3. build the py_gnome module in develop mode first as install mode may still need some testing/work.
```
    $ python setup.py develop  
```

4. If this successfully completes, then run unit_tests
```
    $ py.test --runslow tests/unit_tests/  
```

5. Once all of the py_gnome unit tests pass, install webgnome requirements and build webgnome.
```
    $ cd ../web/gnome/webgnome
    $ pip install -r requirements
    $ python setup.py develop
```

6. Once the webgnome build succeeds, you can test it with the following command.
```
    $ nosetests webgnome/tests/*  
```

7. Run development server  
    `$ pserve development.ini --reload`

The WebGnome server will start up at the location [http://localhost:6543/](http://localhost:6543/)
by default, but you can change this configuration in development.ini.