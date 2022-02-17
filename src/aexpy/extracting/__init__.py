from logging import Logger
from pathlib import Path
from ..producer import Producer
from abc import ABC, abstractmethod
from ..models import Distribution, Release, ApiDescription


class Extractor(Producer):
    @abstractmethod
    def extract(self, dist: "Distribution") -> "ApiDescription":
        pass


def getDefault() -> "Extractor":
    from .basic import Extractor as BasicExtractor
    return BasicExtractor()


class _Empty(Extractor):
    def extract(self, dist: "Distribution") -> "ApiDescription":
        with ApiDescription(distribution=dist).produce(logger=self.logger, redo=self.redo) as api:
            return api


def getEmpty() -> "Extractor":
    return _Empty()
