import hashlib
from pathlib import Path
from zipfile import ZipFile
import pytest
import package_release

PROJECT=Path(__file__).resolve().parents[1]

@pytest.fixture
def bundle(tmp_path):
    root=tmp_path/'bundle';root.mkdir()
    (root/'ContactDock.exe').write_bytes(b'fictional executable')
    internal=root/'_internal';internal.mkdir()
    (internal/'fictional.dll').write_bytes(b'fictional runtime')
    return root


def test_release_contains_notices_and_runtime(bundle,tmp_path):
    license=tmp_path/'python-license.txt';license.write_text('fictional python license')
    output=tmp_path/'release.zip'
    result,checksum=package_release.create_release(PROJECT,bundle,output,license,{'test':'fictional'})
    with ZipFile(result) as z:
        assert z.testzip() is None
        names=set(z.namelist())
        assert {'ContactDock/ContactDock.exe','ContactDock/README.md','ContactDock/THIRD_PARTY_NOTICES.md','ContactDock/BUILD_INFO.json','ContactDock/licenses/Python-runtime.txt'}<=names
        assert z.read('ContactDock/licenses/Python-runtime.txt')==b'fictional python license'
    assert checksum.read_text().split()[0]==hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize('name',['personal.db','personal.db-wal','contacts.csv','settings.json','private.pst','.git'])
def test_private_data_stops_packaging(bundle,tmp_path,name):
    (bundle/'_internal'/name).touch()
    with pytest.raises(ValueError):package_release.validate_bundle(bundle)
    assert not (tmp_path/'release.zip').exists()


def test_existing_output_is_preserved(bundle,tmp_path):
    output=tmp_path/'release.zip';output.write_bytes(b'keep')
    with pytest.raises(FileExistsError):package_release.create_release(PROJECT,bundle,output,tmp_path/'unused',{})
    assert output.read_bytes()==b'keep'


def test_missing_license_does_not_create_zip(bundle,tmp_path):
    output=tmp_path/'release.zip'
    with pytest.raises(ValueError):package_release.create_release(PROJECT,bundle,output,tmp_path/'missing-license',{})
    assert not output.exists()


def test_extra_root_file_is_not_silently_discarded(bundle):
    (bundle/'personal.txt').touch()
    with pytest.raises(ValueError):package_release.validate_bundle(bundle)
