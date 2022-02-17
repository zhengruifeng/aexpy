import ast
import logging
import textwrap
from ast import Call, NodeVisitor, expr, parse
from dataclasses import dataclass, field

from aexpy.analyses.models import ApiCollection, ClassEntry, FunctionEntry
from .. import clearSrc
from . import Caller, CallgraphBuilder, Callsite, Argument, Callgraph


class CallsiteGetter(NodeVisitor):
    def __init__(self, result: Caller, src) -> None:
        super().__init__()
        self.result = result
        self.src = src

    def visit_Call(self, node: Call):
        site = Callsite(value=node)
        site.targetValue = node.func
        match node.func:
            case ast.Attribute() as attr:
                site.targets = [attr.attr]
            case ast.Name() as name:
                site.targets = [name.id]
        for arg in node.args:
            argu = Argument(
                value=arg, raw=ast.get_source_segment(self.src, arg))
            site.arguments.append(argu)
        for arg in node.keywords:
            argu = Argument(name=arg.arg, value=arg.value, iskwargs=arg.arg is None,
                            raw=ast.get_source_segment(self.src, arg.value))
            site.arguments.append(argu)
        self.result.sites.append(site)

        super().generic_visit(node)


class FunctionResolver:
    def __init__(self, api: ApiCollection) -> None:
        self.api = api
        self.subclasses = {}

    def dispatch(self, cls: ClassEntry, name: str):
        if name in cls.members:
            return cls.members[name]
        for item in cls.mro:
            tcls = self.api.entries.get(item)
            if not isinstance(tcls, ClassEntry):
                continue
            if name in tcls.members:
                return tcls.members[name]
        return None

    def resolveMethods(self, cls: ClassEntry, name: str) -> list[str]:
        result = []
        if cls.id not in self.subclasses:
            sc = []
            for item in self.api.classes.values():
                if cls.id in item.bases:
                    sc.append(item)
            self.subclasses[cls.id] = sc
        sc = self.subclasses[cls.id]
        for item in sc:
            target = self.dispatch(item, name)
            if target:
                result.append(target)
        return list(set(result))

    def resolveTargetsByName(self, name: str) -> list[str]:
        targetEntries = self.api.names.get(name)

        if targetEntries is None:
            return []

        resolvedTargets = []

        for targetEntry in targetEntries:
            if isinstance(targetEntry, ClassEntry):
                resolvedTargets.append(
                    f"{targetEntry.id}.__init__")  # get constructor
            elif isinstance(targetEntry, FunctionEntry):
                resolvedTargets.append(targetEntry.id)

        return resolvedTargets


class BasicCallgraphBuilder(CallgraphBuilder):
    def __init__(self, logger: logging.Logger | None = None) -> None:
        super().__init__()
        self.logger = logger if logger is not None else logging.getLogger(
            "callgraph-basic")

    def build(self, api: ApiCollection) -> Callgraph:
        result = Callgraph()
        resolver = FunctionResolver(api)

        for func in api.funcs.values():
            caller = Caller(id=func.id)

            src = clearSrc(func.src)

            try:
                astree = parse(src)
            except Exception as ex:
                self.logger.error(
                    f"Failed to parse code from {func.id}:\n{src}", exc_info=ex)
                result.add(caller)
                continue

            self.logger.debug(f"Visit AST of {func.id}")

            getter = CallsiteGetter(caller, src)
            getter.visit(astree)

            for site in caller.sites:
                if len(site.targets) == 0:
                    continue

                site.targets = resolver.resolveTargetsByName(site.targets[0])

            result.add(caller)

        return result