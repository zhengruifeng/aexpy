from pathlib import Path

from aexpy import getCacheDirectory
from ..producer import DefaultProducer, Producer, NoCachedProducer, ProducerOptions
from abc import ABC, abstractmethod
from ..models import Distribution, Product, Release, ApiDescription, ApiDifference, ApiBreaking, Report


class Reporter(Producer):
    def defaultCache(self) -> "Path | None":
        return getCacheDirectory() / "reporting"

    @abstractmethod
    def report(self,
               oldRelease: "Release", newRelease: "Release",
               oldDistribution: "Distribution", newDistribution: "Distribution",
               oldDescription: "ApiDescription", newDescription: "ApiDescription",
               diff: "ApiDifference",
               bc: "ApiBreaking") -> "Report":
        """Report the differences between two versions of the API."""

        pass


class DefaultReporter(Reporter, DefaultProducer):
    def getCacheFile(self, oldRelease: "Release", newRelease: "Release",
                     oldDistribution: "Distribution", newDistribution: "Distribution",
                     oldDescription: "ApiDescription", newDescription: "ApiDescription",
                     diff: "ApiDifference",
                     bc: "ApiBreaking") -> "Path | None":
        return self.cache / "results" / oldRelease.project / \
            f"{oldRelease}&{newRelease}.json"

    def getOutFile(self, oldRelease: "Release", newRelease: "Release",
                   oldDistribution: "Distribution", newDistribution: "Distribution",
                   oldDescription: "ApiDescription", newDescription: "ApiDescription",
                   diff: "ApiDifference",
                   bc: "ApiBreaking") -> "Path | None":
        """Return the path to the report output file."""

        return self.cache / "reports" / oldRelease.project / \
            f"{oldRelease}&{newRelease}.txt"

    def getProduct(self, oldRelease: "Release", newRelease: "Release",
                   oldDistribution: "Distribution", newDistribution: "Distribution",
                   oldDescription: "ApiDescription", newDescription: "ApiDescription",
                   diff: "ApiDifference",
                   bc: "ApiBreaking") -> "Report":
        file = self.getOutFile(oldRelease=oldRelease, newRelease=newRelease, oldDistribution=oldDistribution, newDistribution=newDistribution,
                               oldDescription=oldDescription, newDescription=newDescription, diff=diff, bc=bc) if self.options.cached else None
        return Report(old=oldRelease, new=newRelease, file=file)

    def process(self, product: "Report", oldRelease: "Release", newRelease: "Release",
                oldDistribution: "Distribution", newDistribution: "Distribution",
                oldDescription: "ApiDescription", newDescription: "ApiDescription",
                diff: "ApiDifference",
                bc: "ApiBreaking"):
        pass

    def onCached(self, product: "Report", oldRelease: "Release", newRelease: "Release",
                 oldDistribution: "Distribution", newDistribution: "Distribution",
                 oldDescription: "ApiDescription", newDescription: "ApiDescription",
                 diff: "ApiDifference",
                 bc: "ApiBreaking"):
        pass

    def report(self,
               oldRelease: "Release", newRelease: "Release",
               oldDistribution: "Distribution", newDistribution: "Distribution",
               oldDescription: "ApiDescription", newDescription: "ApiDescription",
               diff: "ApiDifference",
               bc: "ApiBreaking") -> "Report":
        assert oldDistribution.release == oldRelease, f"{oldDistribution.release} != {oldRelease}"
        assert newDistribution.release == newRelease, f"{newDistribution.release} != {newRelease}"
        assert oldDescription.distribution.release == oldRelease, f"{oldDescription.distribution.release} != {oldRelease}"
        assert newDescription.distribution.release == newRelease, f"{newDescription.distribution.release} != {newRelease}"
        assert diff.old.release == oldRelease, f"{diff.old.release} != {oldRelease}"
        assert diff.new.release == newRelease, f"{diff.new.release} != {newRelease}"
        assert bc.old.release == oldRelease, f"{bc.old.release} != {oldRelease}"
        assert bc.new.release == newRelease, f"{bc.new.release} != {newRelease}"
        return self.produce(oldRelease=oldRelease, newRelease=newRelease, oldDistribution=oldDistribution, newDistribution=newDistribution, oldDescription=oldDescription, newDescription=newDescription, diff=diff, bc=bc)


def getDefault() -> "Reporter":
    from .generators import GeneratorReporter

    return GeneratorReporter()


class Empty(DefaultReporter, NoCachedProducer):
    def produce(self, *args, **kwargs) -> "Product":
        self.options.onlyCache = False
        self.options.cached = False
        return super().produce(*args, **kwargs)


def getEmpty() -> "Reporter":
    return Empty()
