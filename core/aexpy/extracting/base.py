import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, override

from aexpy import json
from aexpy.models.description import TRANSFER_BEGIN, ApiEntry, CollectionEntry

from .. import getAppDirectory
from ..models import ApiDescription, Distribution
from ..utils import elapsedTimer, ensureDirectory, logWithFile
from .environment import EnvirontmentExtractor


class BaseExtractor(EnvirontmentExtractor):
    """Basic extractor that uses dynamic inspect."""

    @override
    def extractInEnv(self, result, run, runPython):
        assert result.distribution
        
        subres = runPython(f"-m aexpy.extracting.main", cwd=getAppDirectory().parent,
                     text=True, capture_output=True, input=result.distribution.dumps())

        self.logger.info(f"Inner extractor exit with {subres.returncode}.")

        if subres.stdout.strip():
            self.logger.debug(f"STDOUT:\n{subres.stdout}")
        if subres.stderr.strip():
            self.logger.info(f"STDERR:\n{subres.stderr}")

        subres.check_returncode()

        data = subres.stdout.split(TRANSFER_BEGIN, 1)[1]
        data = json.loads(data)
        result.load(data)