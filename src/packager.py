#!/usr/bin/env python3.2

import os, sys, zipfile

## Usage: run from directory containing file.

# Determine required parameter values
app_path = os.getcwd()
app_name = os.path.basename(app_path) # or params._PROGRAM_NAME_SHORT
python_exec_name = os.path.basename(sys.executable)

# Create zipfile (for provisioning source code)

zipfile_ = '{}.{}.zip'.format(app_name, python_exec_name)
filenames = [f for f in os.listdir(app_path) if
             ((os.path.splitext(f)[1] in ('.py',)) and ('backup' not in f))]
filenames.append(app_name)
filenames.sort()

zipfile_ = zipfile.ZipFile(zipfile_, mode='w')
for f in filenames: zipfile_.write(f)
zipfile_.close()

# Create pyzipfile (for provisioning application)

zipfile_ =  '{}.compiled.{}.zip'.format(app_name, python_exec_name)

zipfile_ = zipfile.PyZipFile(zipfile_, mode='w')
zipfile_.writepy(app_path)
zipfile_.close()
