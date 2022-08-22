from abc import ABC, abstractmethod
from pathlib import Path

from ..models import Distribution, ProduceCache, Product, Release
from ..producers import Producer


class Preprocessor(Producer):
    def preprocess(self, release: "Release", product: "Distribution"):
        """Preprocess a release and return a distribution."""
        pass
