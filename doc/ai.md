# Hailo AI dataflow compiler

This is to create your custom models. This version is for Ubuntu x86

In folder ~/ai/

```bash
sudo apt update
sudo apt install -y unzip python3-dev python3-pip python3-tk graphviz graphviz-dev build-essential virtualenv
sudo apt install -y build-essential python3.10-dev python3-distutils cython3
````

Create a virtual envirtonment
```bash
python3.10 -m venv ~/ai/hailo-ai
source ~/ai/hailo-ai/bin/activate # to exit: deactivate
python -V  # should say 3.10
````

Install the tool and check
```bash
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade "pip>=25" "setuptools>=70" "numpy==1.26.4"
pip install hailo_dataflow_compiler-3.33.0-py3-none-linux_x86_64.whl


Optional install the model zoo
```bash
git clone https://github.com/hailo-ai/hailo_model_zoo.git
cd hailo_model_zoo
pip uninstall -y lap || true
pip install "lapx>=0.5.5"
git fetch --all --tags
git checkout v2.16.0   # use latest
git clean -xfd         # wipe build leftovers
rm -rf *.egg-info build dist
pip install setuptools-scm "packaging>=23" "tomli; python_version<'3.11'"
pip install . --no-deps --no-build-isolation

# Verify DFC is actually present in THIS venv
pip show hailo-dataflow-compiler
which hailo
hailo --version
```
