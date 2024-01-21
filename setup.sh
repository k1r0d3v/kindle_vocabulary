#!/bin/bash 

rm -rf env

echo "Creating python environment..."
python -m venv env
source env/bin/activate

echo "Intalling requirements..."
pip -q install -r requirements.txt

echo "Patching modules..."
patch -i wrpy.core.patch $(python -c "import wrpy as _; print(_.__path__[0])")/core.py