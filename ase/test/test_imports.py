from pathlib import Path
from importlib import import_module
import pytest
import ase

# This test imports modules.
#
# This test exists because we don't want those modules at the bottom
# of the coverage ranking distracting us from real issues, and because
# importing them is at least slightly better than just ignoring them
# in the coverage stats.
#
# Some modules get 100% coverage because of this, while others
# will still have low coverage.  That's okay.


def filenames2modules(filenames):
    modules = []
    for filename in filenames:
        module = str(filename).rsplit('.', 1)[0]
        module = module.replace('/', '.')
        if module == 'ase.data.tmxr200x':
            continue
        modules.append(module)
        print(module)
    return modules


def glob_modules():
    topdir = Path(ase.__file__).parent
    for path in topdir.rglob('*.py'):
        path = 'ase' / path.relative_to(topdir)
        if path.name.startswith('__'):
            continue
        if path.parts[1] == 'test':
            continue
        yield path

all_modules = filenames2modules(glob_modules())


ignore_imports = {
    'flask', 'psycopg2', 'kimpy', 'pymysql', 'IPython',
    'gpaw.lrtddft'  # ase.vibrations.placzek
}


@pytest.mark.filterwarnings('ignore:Moved to')
def test_imports():
    for module in all_modules:
        try:
            import_module(module)
        except ImportError as err:
            modname = err.name
            if err.name not in ignore_imports:
                raise
