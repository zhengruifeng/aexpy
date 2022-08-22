import code
import pathlib
import subprocess
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path
from typing import Callable
from uuid import uuid1

from aexpy import json
from aexpy.diffing import Differ
from aexpy.env import PipelineConfig, ProducerConfig
from aexpy.evaluating import Evaluator
from aexpy.extracting import Extractor
from aexpy.models import (ApiDescription, ApiDifference,
                          Distribution, Release, Report)
from aexpy.models.difference import BreakingRank, DiffEntry
from aexpy.preprocessing import Preprocessor
from aexpy.reporting import Reporter


def getDefault() -> "PipelineConfig":
    from aexpy.diffing import Empty as EDiffer
    from aexpy.extracting import Empty as EExtractor
    from aexpy.preprocessing.pip import PipPreprocessor as PPreprocessor

    from .evaluator import Evaluator as PEvaluator
    from .reporter import Reporter as PReporter

    return PipelineConfig(
        name="pidiff",
        preprocess=PPreprocessor.id(),
        extractor=EExtractor.id(),
        differ=EDiffer.id(),
        evaluator=PEvaluator.id(),
        reporter=PReporter.id(),
    )
