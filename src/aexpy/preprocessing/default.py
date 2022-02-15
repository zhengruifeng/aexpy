from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
from logging import Logger
from pathlib import Path
import re
import shutil
import zipfile
import requests
from urllib import parse
from email.message import Message
import wheel.metadata
import platform

from aexpy import utils

from ..models import Distribution, Release
from . import Preprocessor as Base
from ..utils import elapsedTimer, ensureDirectory, logWithFile

FILE_ORIGIN = "https://files.pythonhosted.org/"
FILE_TSINGHUA = "https://pypi.tuna.tsinghua.edu.cn/"
INDEX_ORIGIN = "https://pypi.org/simple/"
INDEX_TSINGHUA = "https://pypi.tuna.tsinghua.edu.cn/simple/"


@dataclass
class DownloadInfo:
    url: "str"
    sha256: "str" = ""
    md5: "str" = ""
    name: "str" = field(init=False)

    def __post_init__(self):
        self.name = parse.urlparse(self.url).path.split("/")[-1]


@dataclass
class CompatibilityTag:
    python: str = "py3"
    abi: str = "none"
    platform: list[str] = field(default_factory=lambda: ["any"])

    @classmethod
    def fromfile(cls, filename: str) -> "CompatibilityTag | None":
        filename = Path(filename).stem
        try:
            segs = filename.split("-")
            return CompatibilityTag(segs[-3], segs[-2], segs[-1].split("."))
        except:
            return None


@dataclass
class DistInfo:
    metadata: Message
    topLevel: list[str]
    wheel: Message

    def pyversion(self) -> str | None:
        tags = self.wheel.get_all("tag")
        for rawTag in tags:
            tag = CompatibilityTag.fromfile(rawTag) or CompatibilityTag()
            if "any" in tag.platform:
                requires = str(self.metadata.get("requires-python"))
                requires = list(map(lambda x: x.strip(), requires.split(",")))
                if len(requires) == 0:
                    return None
                for item in requires:
                    if item.startswith(">="):
                        version = item.removeprefix(">=").strip()
                        if version.startswith("3."):
                            if int(version.split(".")[1]) < 7:
                                return "3.7"
                            else:
                                return version
                        else:
                            return version
                    elif item.startswith("<="):
                        return item.removeprefix("<=").strip()
                return "3.7"
            else:
                for i in range(7, 11):
                    if f"py3{i}" in tag.python or f"cp3{i}" in tag.python:
                        return f"3.{i}"
        return None

    @classmethod
    def fromdir(cls, path: "Path") -> "DistInfo | None":
        distinfoDir = list(path.glob("*.dist-info"))
        if len(distinfoDir) == 0:
            return None
        distinfoDir = distinfoDir[0]
        try:
            return DistInfo(
                metadata=wheel.metadata.read_pkg_info(
                    distinfoDir / "METADATA"),
                topLevel=[s.strip() for s in distinfoDir.joinpath(
                    "top_level.txt").read_text().splitlines() if s.strip()],
                wheel=wheel.metadata.read_pkg_info(
                    distinfoDir / "WHEEL")
            )
        except:
            return None


class Preprocessor(Base):
    def __init__(self, logger: "Logger | None" = None, cache: "Path | None" = None, redo: "bool" = False, mirror: "bool" = False) -> None:
        super().__init__(logger, cache, redo)
        self.mirror = mirror

    def preprocess(self, release: "Release") -> "Distribution":
        cacheDir = self.cache / "results" / \
            release.project
        cacheFile = cacheDir / f"{release.version}.json"
        ensureDirectory(cacheDir)

        if not cacheFile.exists() or self.redo:
            logFile = cacheDir / f"{release.version}.log"
            success = True
            wheelFile = None
            wheelDir = None
            distInfo = None
            with logWithFile(self.logger, logFile):
                with elapsedTimer() as elapsed:
                    try:
                        rels = self.getReleases(release.project)
                        if rels is None or release.version not in rels:
                            raise Exception(f"Not found the release {release}")
                        download = self.getDownloadInfo(rels[release.version])
                        if download is None:
                            raise Exception(
                                f"Not found the valid distribution {release}")
                        wheelFile = self.downloadWheel(release.project, download)
                        wheelDir = self.unpackWheel(release.project, wheelFile)
                        distInfo = DistInfo.fromdir(wheelDir)
                    except Exception as ex:
                        self.logger.error(f"Failed to preprocess {release}.", exc_info=ex)
                        success = False
            ret = Distribution(creation=datetime.now(),
                               duration=timedelta(seconds=elapsed()),
                               release=release, wheelFile=wheelFile, wheelDir=wheelDir,
                               logFile=logFile, success=success)
            if distInfo:
                ret.pyversion = distInfo.pyversion()
                ret.topModules = distInfo.topLevel
            cacheFile.write_text(ret.dumps())
        else:
            ret = Distribution()
            ret.load(json.loads(cacheFile.read_text()))

        return ret

    def getIndex(self):
        url = INDEX_TSINGHUA if self.mirror else INDEX_ORIGIN
        cache = self.cache
        resultCache = cache / "index.json"
        if resultCache.exists() and not self.redo:
            return json.loads(resultCache.read_text())

        htmlCache = cache.joinpath("simple.html")
        if not htmlCache.exists() or self.redo:
            self.logger.info(f"Request PYPI Index @ {url}")
            try:
                htmlCache.write_text(requests.get(url, timeout=60).text)
            except Exception as ex:
                self.logger.error("Failed to request index", exc_info=ex)
                return []

        regex = r'<a href="[\w:/\.]*">([\S\s]*?)</a>'
        result = re.findall(regex, htmlCache.read_text())
        resultCache.write_text(json.dumps(result))
        return result

    def getReleases(self, project: "str") -> "dict | None":
        cache = self.cache / "releases" / project
        utils.ensureDirectory(cache)
        cacheFile = cache / "index.json"

        if not cacheFile.exists() or self.redo:
            url = f"https://pypi.org/pypi/{project}/json"
            self.logger.info(f"Request releases @ {url}")
            try:
                cacheFile.write_text(json.dumps(
                    requests.get(url, timeout=60).json()["releases"]))
            except:
                cacheFile.write_text(json.dumps(None))

        return json.loads(cacheFile.read_text())

    def getReleaseInfo(self, project: str, version: str) -> dict | None:
        cache = self.cache / "releases" / project
        utils.ensureDirectory(cache)
        cacheFile = cache / f"{version}.json"
        if not cacheFile.exists() or self.redo:
            url = f"https://pypi.org/pypi/{project}/{version}/json"
            self.logger.info(f"Request release info @ {url}")
            try:
                cacheFile.write_text(json.dumps(
                    requests.get(url, timeout=60).json()["info"]))
            except:
                cacheFile.write_text(json.dumps(None))
        return json.loads(cacheFile.read_text())

    def getDownloadInfo(self, release: "list[dict]", packagetype="bdist_wheel") -> "DownloadInfo | None":
        py3 = []

        for item in release:
            if item["packagetype"] != packagetype:
                continue

            # https://www.python.org/dev/peps/pep-0425/#compressed-tag-sets

            tag = CompatibilityTag.fromfile(
                item["filename"]) or CompatibilityTag()
            if "py3" not in tag.python:
                if "cp3" not in tag.python:
                    continue
            if "any" not in tag.platform:
                if "windows" in platform.platform().lower():
                    if not any((platform for platform in tag.platform if "win" in platform and "amd64" in platform)):
                        continue
                else:
                    if not any((platform for platform in tag.platform if "linux" in platform and "x86_64" in platform)):
                        continue

            py3.append((item, tag))

        py37 = []
        for item, tag in py3:
            for i in range(7, 11):
                if f"py3{i}" in tag.python or f"cp3{i}" in tag.python:
                    py37.append(item)
                    break

        result = None

        if len(py37) > 0:
            result = py37[0]

        if len(py3) > 0:
            result = py3[0][0]

        if result:
            ret = DownloadInfo(item["url"], item["digests"].get(
                "sha256", ""), item["digests"].get("md5", ""))
            self.logger.debug(f"Select download-info {ret}.")
            return ret

        self.logger.warning(f"Failed to select download-info.")
        return None

    def downloadWheel(self, project: str, info: "DownloadInfo") -> "Path":
        cache = self.cache / "wheels" / project
        utils.ensureDirectory(cache)
        cacheFile = cache / info.name

        if self.mirror:
            url = info.url.replace(FILE_ORIGIN, FILE_TSINGHUA)
        else:
            url = info.url

        if not cacheFile.exists() or self.redo:
            self.logger.info(f"Download wheel @ {url}.")
            try:
                content = requests.get(url, timeout=60).content
                if info.sha256:
                    if hashlib.sha256(content).hexdigest() != info.sha256:
                        raise Exception(
                            f"Release download sha256 mismatch: {info}.")

                if info.md5:
                    if hashlib.md5(content).hexdigest() != info.md5:
                        raise Exception(
                            f"Release download md5 mismatch: {info}.")

                with open(cacheFile, "wb") as file:
                    file.write(content)
            except Exception as ex:
                self.logger.error(f"Not found wheel {url}.", exc_info=ex)
                raise Exception(f"Not found download: {url}.")

        return cacheFile.resolve()

    def unpackWheel(self, project: str, path: "Path") -> "Path":
        cache = self.cache / "wheels" / project / "unpacked"

        cacheDir = cache / path.stem

        if self.redo and cacheDir.exists():
            self.logger.info(
                f"Remove old unpacked files @ {cacheDir.relative_to(self.cache)}")
            shutil.rmtree(cacheDir)

        if not cacheDir.exists() or self.redo:
            utils.ensureDirectory(cacheDir)

            self.logger.info(
                f"Unpack {path.relative_to(self.cache)} to {cacheDir.relative_to(self.cache)}")

            with zipfile.ZipFile(path) as f:
                f.extractall(cacheDir)

        return cacheDir.resolve()
