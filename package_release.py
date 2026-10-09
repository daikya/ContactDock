"""Package the verified Windows onedir build with notices; never overwrite ZIPs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

PRIVATE_SUFFIXES={'.db','.sqlite','.sqlite3','.csv','.pst','.vcf'}
REQUIRED_LICENSES={'sqlcipher3.txt','SQLCipher.txt','SQLCipher-Bundled-Notice.txt','OpenSSL.txt','Tcl.txt','Tk.txt','PyInstaller.txt'}


def validate_bundle(bundle):
    bundle=Path(bundle).resolve()
    if not (bundle/'ContactDock.exe').is_file() or not (bundle/'_internal').is_dir():
        raise ValueError('通常版のContactDock.exeと_internalが見つかりません。')
    for path in bundle.rglob('*'):
        if path.is_symlink() or not path.resolve().is_relative_to(bundle):
            raise ValueError('配布フォルダに外部参照が含まれています。')
        lower=path.name.lower()
        if (path.suffix.lower() in PRIVATE_SUFFIXES or '.db-' in lower or '.sqlite' in lower
                or lower in {'settings.json','.venv','.git','tests','__pycache__'}):
            raise ValueError('配布フォルダにDB・CSV・設定・開発用ファイルが含まれています。')
    allowed={'ContactDock.exe','_internal'}
    if any(path.name not in allowed for path in bundle.iterdir()):
        raise ValueError('通常版の出力直下に追加ファイルがあります。元のビルド出力を使用してください。')
    return bundle


def create_release(project,bundle,output,python_license,metadata):
    project=Path(project);bundle=validate_bundle(bundle);output=Path(output)
    if output.exists() or output.with_suffix(output.suffix+'.sha256').exists():
        raise FileExistsError('同名の配布ファイルは上書きしません。')
    license_dir=project/'licenses'
    if not REQUIRED_LICENSES<={p.name for p in license_dir.glob('*.txt')}:
        raise ValueError('必要なライセンス原文が不足しています。')
    if not Path(python_license).is_file():raise ValueError('Python本体のLICENSE.txtが見つかりません。')
    if output.resolve().is_relative_to(bundle):raise ValueError('ZIPはビルド済みフォルダの外へ保存してください。')
    # Stage only verified build output and explicitly selected documentation.
    with tempfile.TemporaryDirectory(prefix='contactdock-release-') as temporary:
        stage=Path(temporary)/'ContactDock';stage.mkdir()
        shutil.copy2(bundle/'ContactDock.exe',stage/'ContactDock.exe')
        shutil.copytree(bundle/'_internal',stage/'_internal')
        shutil.copytree(license_dir,stage/'licenses')
        shutil.copy2(python_license,stage/'licenses'/'Python-runtime.txt')
        # Prefer the license terms from the actual bundled Tcl/Tk runtime.
        for name,folder in (('Tcl.txt','_tcl_data'),('Tk.txt','_tk_data')):
            actual=bundle/'_internal'/folder/'license.terms'
            if actual.is_file():shutil.copy2(actual,stage/'licenses'/name)
        shutil.copy2(project/'DISTRIBUTION_README.md',stage/'README.md')
        shutil.copy2(project/'THIRD_PARTY_NOTICES.md',stage/'THIRD_PARTY_NOTICES.md')
        (stage/'BUILD_INFO.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        created=False
        try:
            with ZipFile(output,'x',ZIP_DEFLATED) as z:
                created=True
                for path in sorted(stage.rglob('*')):
                    if path.is_file():z.write(path,path.relative_to(stage.parent))
            with ZipFile(output) as z:
                if z.testzip() is not None:raise ValueError('ZIP整合性検査に失敗しました。')
        except BaseException:
            if created:output.unlink(missing_ok=True)
            raise
    with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    checksum=output.with_suffix(output.suffix+'.sha256')
    with checksum.open('x',encoding='utf-8') as stream:stream.write(digest+'  '+output.name+'\n')
    return output,checksum


def main():
    if os.name!='nt':raise SystemExit('Windowsのビルド環境で実行してください。')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    from importlib.metadata import version
    from sqlcipher3 import dbapi2 as sqlcipher
    import tkinter
    project=Path(__file__).resolve().parent
    if version('sqlcipher3')!='0.6.3' or version('pyinstaller')!='6.22.3':
        raise SystemExit('検証対象のsqlcipher3またはPyInstallerの版が異なります。')
    c=sqlcipher.connect(':memory:')
    try:cipher=c.execute('PRAGMA cipher_version').fetchone()[0]
    finally:c.close()
    tcl=tkinter.Tcl().eval('info patchlevel')
    architecture='x64' if platform.machine().lower() in {'amd64','x86_64'} else platform.machine().lower()
    output=args.output or project/'dist'/f'ContactDock-0.1.0-windows-{architecture}.zip'
    if output.exists() or output.with_suffix(output.suffix+'.sha256').exists():
        raise SystemExit('同名のZIPまたはSHA-256ファイルが存在します。別の--output名を指定してください。')
    metadata={'contactdock':'0.1.0','python':platform.python_version(),'architecture':architecture,
              'sqlcipher3':version('sqlcipher3'),'sqlcipher':cipher,'pyinstaller':version('pyinstaller'),
              'tcl':tcl,'tk':str(tkinter.TkVersion)}
    if not cipher.startswith('4.12.0'):raise SystemExit('SQLCipherの版が検証対象と異なります。')
    result=create_release(project,project/'dist'/'ContactDock',output,Path(sys.base_prefix)/'LICENSE.txt',metadata)
    for path in result:print(path)


if __name__=='__main__':main()
