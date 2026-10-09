# Third-party software notices

ContactDock uses the following third-party software. ContactDock is an independent application, not an official product of the organizations listed below. Original copyright and license notices are retained under `licenses/` and in the bundled runtime files. ContactDock itself is licensed under the MIT License in the top-level LICENSE file. Third-party components retain their respective licenses below.

| Component | Distribution notice |
|---|---|
| Python runtime / standard library | `licenses/Python-runtime.txt`, copied from the Python installation used to package the release. This file includes Python's license history and bundled third-party notices. |
| Tcl / Tk | `licenses/Tcl.txt`, `licenses/Tk.txt`; upstream 8.6.12 license terms, replaced by actual bundled `license.terms` when present. Preserve other notices in `_internal` as well. |
| sqlcipher3 0.6.3 | `licenses/sqlcipher3.txt`, taken from the CPython 3.12 Windows x64 wheel. Copyright (c) 2004-2007 Gerhard Häring. |
| SQLCipher Community 4.12.0 | `licenses/SQLCipher.txt`, upstream version 4.12.0 BSD-style license; `licenses/SQLCipher-Bundled-Notice.txt`, original notice from sqlcipher3's vendored amalgamation. Copyright belongs to ZETETIC LLC. |
| SQLite, included in SQLCipher | SQLite's original core is in the public domain. The SQLCipher modifications retain their own license. SQLite's notice is retained in `licenses/SQLite.txt`. |
| OpenSSL 3.6.0, statically included in the inspected sqlcipher3 Windows wheel | `licenses/OpenSSL.txt`, Apache License 2.0. OpenSSL is developed by The OpenSSL Project Authors. This is separate from any OpenSSL runtime bundled with Python, whose notice is included in Python's LICENSE.txt. |
| PyInstaller 6.22.3 bootloader and runtime support | `licenses/PyInstaller.txt`, GPL v2 or later with the bootloader exception and other notices. The exception is part of the original text. |

Source references:

- Python: https://docs.python.org/3/license.html
- Tcl: https://github.com/tcltk/tcl/blob/core-8-6-12/license.terms
- Tk: https://github.com/tcltk/tk/blob/core-8-6-12/license.terms
- sqlcipher3: https://pypi.org/project/sqlcipher3/0.6.3/
- SQLCipher: https://github.com/sqlcipher/sqlcipher/blob/v4.12.0/LICENSE.md
- SQLite: https://www.sqlite.org/copyright.html
- OpenSSL: https://github.com/openssl/openssl/blob/openssl-3.6.0/LICENSE.txt
- PyInstaller: https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt

Build-only tools such as pytest, setuptools, and packaging are not intentionally shipped as application features. When the build's dependency set changes, inspect the actual bundled files and update this notice before distribution.
