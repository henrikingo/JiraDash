"""
Dynamically load a python module based string argument. (Such as cli option)
"""
from importlib import import_module

def run_command(my_config):
    module_path = "jiradash." + my_config['command'][0]
    module = import_module(module_path, package="jiradash")
    func = getattr(module, 'entry_point')
    func(my_config)
