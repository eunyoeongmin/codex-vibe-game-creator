# Third-party licenses

This inventory accompanies the [README](../README.md#third-party-software). It covers the 60 pinned entries in [requirements-runtime.txt](../requirements-runtime.txt). Package versions and license declarations were checked against the installed distributions and their license files on 2026-10-05. Package links point to the corresponding releases.

Python, Codex CLI, SQLite and the embedding model are listed with upstream license links in the README. The release ZIP and setup executable do not embed their binaries or the Python package/model cache; setup obtains or reuses these components separately. The harness [MIT License](../LICENSE) applies to our code, not to third-party code or model weights.

## Python packages

The license column summarizes package declarations. `AND` and `OR` are retained where the package declares them. A package's own LICENSE, NOTICE, COPYING and other bundled notices remain authoritative, including notices for libraries inside binary wheels. This index does not replace those texts or relicense the dependencies.

Notice paths below are as declared by the package, or relative to its installed `.dist-info` directory. Declared files may be under `.dist-info/licenses/`. For example, `py_rust_stemmers` does not declare a license name in its metadata; its installed `licenses/LICENSE` explicitly identifies MIT.

| Package / release | Version | Declared license / license-file summary | Notice files |
|---|---|---|---|
| [annotated-types](https://pypi.org/project/annotated-types/0.8.0/) | 0.8.0 | MIT | `LICENSE` |
| [anyio](https://pypi.org/project/anyio/4.15.1/) | 4.15.1 | MIT | `LICENSE` |
| [certifi](https://pypi.org/project/certifi/2026.7.22/) | 2026.7.22 | MPL-2.0 | `LICENSE` |
| [chardet](https://pypi.org/project/chardet/7.6.0/) | 7.6.0 | 0BSD | `LICENSE` |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/) | 3.5.2 | MIT | `LICENSE` |
| [click](https://pypi.org/project/click/8.5.0/) | 8.5.0 | BSD-3-Clause | `LICENSE.txt` |
| [cloudpickle](https://pypi.org/project/cloudpickle/3.1.2/) | 3.1.2 | BSD-3-Clause | `LICENSE` |
| [colorama](https://pypi.org/project/colorama/0.4.6/) | 0.4.6 | BSD-3-Clause | `LICENSE.txt` |
| [fastembed](https://pypi.org/project/fastembed/0.8.1/) | 0.8.1 | Apache-2.0 | `LICENSE`, `NOTICE` |
| [filelock](https://pypi.org/project/filelock/4.0.7/) | 4.0.7 | MIT | `LICENSE` |
| [flatbuffers](https://pypi.org/project/flatbuffers/25.12.19/) | 25.12.19 | Apache-2.0 | Package metadata / upstream notices |
| [fsspec](https://pypi.org/project/fsspec/2026.9.0/) | 2026.9.0 | BSD-3-Clause | `LICENSE` |
| [grpcio](https://pypi.org/project/grpcio/1.84.0/) | 1.84.0 | Apache-2.0 | `LICENSE` |
| [h11](https://pypi.org/project/h11/0.16.0/) | 0.16.0 | MIT | `LICENSE.txt` |
| [hf-xet](https://pypi.org/project/hf-xet/1.6.0/) | 1.6.0 | Apache-2.0 | `LICENSE` |
| [httpcore](https://pypi.org/project/httpcore/1.0.9/) | 1.0.9 | BSD-3-Clause | `LICENSE.md` |
| [httpx](https://pypi.org/project/httpx/0.28.1/) | 0.28.1 | BSD-3-Clause | `licenses/LICENSE.md` |
| [huggingface_hub](https://pypi.org/project/huggingface_hub/1.33.0/) | 1.33.0 | Apache-2.0 | `LICENSE` |
| [idna](https://pypi.org/project/idna/3.20/) | 3.20 | BSD-3-Clause | `LICENSE.md` |
| [joblib](https://pypi.org/project/joblib/1.6.0/) | 1.6.0 | BSD-3-Clause | `LICENSE.txt` |
| [loguru](https://pypi.org/project/loguru/0.7.3/) | 0.7.3 | MIT | Package metadata / upstream notices |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/4.2.0/) | 4.2.0 | MIT | `LICENSE`, `LICENSE.markdown-it` |
| [mdurl](https://pypi.org/project/mdurl/0.1.2/) | 0.1.2 | MIT | `LICENSE` |
| [mmh3](https://pypi.org/project/mmh3/5.3.1/) | 5.3.1 | MIT | `LICENSE` |
| [narwhals](https://pypi.org/project/narwhals/2.26.0/) | 2.26.0 | MIT | `LICENSE.md` |
| [networkx](https://pypi.org/project/networkx/3.7/) | 3.7 | BSD-3-Clause | `LICENSE.txt` |
| [numpy](https://pypi.org/project/numpy/2.5.3/) | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | `LICENSE.txt`, `numpy/_core/include/numpy/libdivide/LICENSE.txt`, `numpy/_core/src/common/pythoncapi-compat/COPYING`, `numpy/_core/src/highway/LICENSE`, `numpy/_core/src/multiarray/dragon4_LICENSE.txt`, `numpy/_core/src/npysort/x86-simd-sort/LICENSE.md`, `numpy/_core/src/umath/svml/LICENSE`, `numpy/fft/pocketfft/LICENSE.md`, `numpy/linalg/lapack_lite/LICENSE.txt`, `numpy/ma/LICENSE`, `numpy/random/LICENSE.md`, `numpy/random/src/distributions/LICENSE.md`, `numpy/random/src/mt19937/LICENSE.md`, `numpy/random/src/pcg64/LICENSE.md`, `numpy/random/src/philox/LICENSE.md`, `numpy/random/src/sfc64/LICENSE.md`, `numpy/random/src/splitmix64/LICENSE.md` |
| [onnxruntime](https://pypi.org/project/onnxruntime/1.30.0/) | 1.30.0 | MIT | Package metadata / upstream notices |
| [packaging](https://pypi.org/project/packaging/26.3/) | 26.3 | Apache-2.0 OR BSD-2-Clause | `LICENSE`, `LICENSE.APACHE`, `LICENSE.BSD` |
| [pandas](https://pypi.org/project/pandas/3.0.6/) | 3.0.6 | BSD-3-Clause | `LICENSE` |
| [pillow](https://pypi.org/project/pillow/12.3.0/) | 12.3.0 | MIT-CMU | `LICENSE` |
| [protobuf](https://pypi.org/project/protobuf/7.36.2/) | 7.36.2 | BSD-3-Clause | `LICENSE` |
| [py_rust_stemmers](https://pypi.org/project/py_rust_stemmers/0.1.8/) | 0.1.8 | MIT | `LICENSE` |
| [pyarrow](https://pypi.org/project/pyarrow/25.0.1/) | 25.0.1 | Apache-2.0 | `LICENSE.txt`, `NOTICE.txt` |
| [pydantic](https://pypi.org/project/pydantic/2.13.5/) | 2.13.5 | MIT | `LICENSE` |
| [pydantic_core](https://pypi.org/project/pydantic_core/2.46.5/) | 2.46.5 | MIT | `LICENSE` |
| [Pygments](https://pypi.org/project/Pygments/2.21.0/) | 2.21.0 | BSD-2-Clause | `AUTHORS`, `LICENSE` |
| [pyoxigraph](https://pypi.org/project/pyoxigraph/0.5.11/) | 0.5.11 | MIT OR Apache-2.0 | Package metadata / upstream notices |
| [pyparsing](https://pypi.org/project/pyparsing/3.3.3/) | 3.3.3 | MIT | `LICENSE` |
| [python-dateutil](https://pypi.org/project/python-dateutil/2.9.0.post0/) | 2.9.0.post0 | BSD-3-Clause; Apache-2.0 also applies to specified contributions | `LICENSE` |
| [python-dotenv](https://pypi.org/project/python-dotenv/1.2.3/) | 1.2.3 | BSD-3-Clause | `LICENSE` |
| [PyYAML](https://pypi.org/project/PyYAML/6.0.3/) | 6.0.3 | MIT | `LICENSE` |
| [rdflib](https://pypi.org/project/rdflib/7.6.0/) | 7.6.0 | BSD-3-Clause | `LICENSE` |
| [requests](https://pypi.org/project/requests/2.34.2/) | 2.34.2 | Apache-2.0 | `LICENSE`, `NOTICE` |
| [rich](https://pypi.org/project/rich/15.0.0/) | 15.0.0 | MIT | `LICENSE` |
| [scikit-learn](https://pypi.org/project/scikit-learn/1.9.1/) | 1.9.1 | BSD-3-Clause | `COPYING` |
| [scipy](https://pypi.org/project/scipy/1.18.1/) | 1.18.1 | BSD-3-Clause; additional bundled-library notices in LICENSE.txt | `LICENSE.txt` |
| [semantica](https://pypi.org/project/semantica/0.7.0/) | 0.7.0 | MIT | `LICENSE` |
| [six](https://pypi.org/project/six/1.17.0/) | 1.17.0 | MIT | `LICENSE` |
| [sqlite-vec](https://pypi.org/project/sqlite-vec/0.1.9/) | 0.1.9 | MIT / Apache-2.0 | Package metadata / upstream notices |
| [structlog](https://pypi.org/project/structlog/26.1.0/) | 26.1.0 | MIT OR Apache-2.0 | `LICENSE-APACHE`, `LICENSE-MIT`, `NOTICE` |
| [threadpoolctl](https://pypi.org/project/threadpoolctl/3.7.0/) | 3.7.0 | BSD-3-Clause | `LICENSE` |
| [tokenizers](https://pypi.org/project/tokenizers/0.23.2/) | 0.23.2 | Apache-2.0 | Package metadata / upstream notices |
| [toml](https://pypi.org/project/toml/0.10.2/) | 0.10.2 | MIT | `LICENSE` |
| [tqdm](https://pypi.org/project/tqdm/4.70.1/) | 4.70.1 | MPL-2.0 AND MIT | `LICENCE` |
| [typing-inspection](https://pypi.org/project/typing-inspection/0.4.4/) | 0.4.4 | MIT | `LICENSE` |
| [typing_extensions](https://pypi.org/project/typing_extensions/4.16.0/) | 4.16.0 | PSF-2.0 | `LICENSE` |
| [tzdata](https://pypi.org/project/tzdata/2026.4/) | 2026.4 | Apache-2.0 | `LICENSE`, `licenses/LICENSE_APACHE` |
| [urllib3](https://pypi.org/project/urllib3/2.8.0/) | 2.8.0 | MIT | `LICENSE.txt` |
| [win32_setctime](https://pypi.org/project/win32_setctime/1.2.0/) | 1.2.0 | MIT | `LICENSE` |

## Runtime and service scope

Python has its own PSF license agreement and bundled-component notices. Its SQLite engine is public domain. NumPy, SciPy, PyArrow, ONNX Runtime and other binary packages can include further third-party components: retain their supplied notices when redistributing those binaries. The SciPy license file, for example, includes notices for OpenBLAS, LAPACK and other build-dependent components.

Codex CLI's Apache-2.0 license covers the client software. Access to the hosted OpenAI service is separate from this source-code license. Windows PowerShell and .NET Framework are operating-system prerequisites, not bundled in this project's release payload.

When changing requirements or bootstrap/model versions, update this inventory and the README component tables alongside them.
