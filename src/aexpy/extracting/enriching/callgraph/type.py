import ast
import logging
import textwrap
from ast import Call, NodeVisitor, expr, parse
from dataclasses import dataclass, field

import mypy
from mypy.nodes import Decorator, Expression, FuncDef, CallExpr, MemberExpr, NameExpr, StrExpr, TypeInfo, Var, ARG_STAR2, IntExpr, FloatExpr, ComplexExpr, ListExpr, SetExpr, DictExpr, TupleExpr
from mypy.traverser import TraverserVisitor
from mypy.types import Instance, UnionType, NoneType, Type, AnyType, CallableType
from mypy.subtypes import is_subtype

from aexpy.models import ApiDescription, ClassEntry, FunctionEntry
from .. import clearSrc
from aexpy.extracting.third.mypyserver import PackageMypyServer
from . import Caller, CallgraphBuilder, Callsite, Argument, Callgraph
from .basic import FunctionResolver


def hasAnyType(types: "list[Type]") -> "bool":
    return any((tp for tp in types if isinstance(tp, AnyType)))


ANY_TYPERESULT = [AnyType(0)]


def resolvePossibleTypes(o: "Expression") -> "list[Type]":
    result = []

    def appendType(type: "Type"):
        match type:
            case Instance() as ins:
                result.append(ins)
            case UnionType() as union:
                for item in union.items:
                    appendType(item)

    match o:
        case NameExpr() as name:
            match name.node:
                case TypeInfo() as ti:
                    result.append(Instance(ti, []))
                case Var() as var:
                    appendType(var.type)

        case CallExpr() as call:
            subTypes = resolvePossibleTypes(call.callee)
            if hasAnyType(subTypes):
                return ANY_TYPERESULT
            subTypes = [tp for tp in subTypes if isinstance(tp, CallableType)]

            for sub in subTypes:
                appendType(sub.ret_type)

        case MemberExpr() as member:
            subTypes = resolvePossibleTypes(member.expr)
            if hasAnyType(subTypes):
                return ANY_TYPERESULT
            subTypes = [tp for tp in subTypes if isinstance(tp, Instance)]

            for sub in subTypes:
                attr = sub.type.get(member.name)
                if attr is None:
                    continue
                if attr.type:
                    appendType(attr.type)

    if hasAnyType(result):
        return ANY_TYPERESULT

    return result


class CallsiteGetter(TraverserVisitor):
    def __init__(self, api: "ApiDescription", result: "Caller", resolver: "FunctionResolver", logger: "logging.Logger") -> None:
        super().__init__()
        self.api = api
        self.resolver = resolver
        self.result = result
        self.logger = logger

    def visit_call_expr(self, o: "CallExpr") -> None:
        site = Callsite(value=o)
        site.targetValue = o.callee
        try:
            match o.callee:
                case NameExpr() as name:
                    if name.fullname in self.api.entries:
                        site.targets = [name.fullname]
                    else:
                        site.targets = self.resolver.resolveTargetsByName(
                            name.fullname if name.fullname else name.name)
                case MemberExpr() as member:
                    exprTypes = resolvePossibleTypes(member.expr)
                    if hasAnyType(exprTypes):
                        site.targets = self.resolver.resolveTargetsByName(
                            member.name)
                    else:
                        targets = []
                        for tp in exprTypes:
                            if not isinstance(tp, Instance):
                                continue
                            tg = tp.type.get(member.name)
                            if tg is not None:
                                targets.append(tg.fullname)
                            cls = self.api.entries.get(tp.type.fullname)
                            if cls:
                                targets.extend(
                                    self.resolver.resolveMethods(cls, member.name))

                        site.targets = targets
        except Exception as ex:
            self.logger.error(
                f"Failed to resolve target for {o}.", exc_info=ex)

        for i in range(len(site.targets)):
            entry = self.api.entries.get(site.targets[i])
            if isinstance(entry, ClassEntry):
                site.targets[i] = f"{site.targets[i]}.__init__"

        for i, a in enumerate(o.args):
            argu = Argument(
                value=a, name=o.arg_names[i], iskwargs=o.arg_kinds[i] == ARG_STAR2)
            site.arguments.append(argu)
        self.result.sites.append(site)

        super().visit_call_expr(o)


class TypeCallgraphBuilder(CallgraphBuilder):
    def __init__(self, server: "PackageMypyServer", logger: "logging.Logger | None" = None) -> None:
        super().__init__()
        self.server = server
        self.logger = logger.getChild("callgraph-type") if logger is not None else logging.getLogger(
            "callgraph-type")

    def build(self, api: "ApiDescription") -> Callgraph:
        result = Callgraph()
        resolver = FunctionResolver(api)

        for func in api.funcs.values():
            caller = Caller(id=func.id)

            element = self.server.element(func)

            if element is None:
                self.logger.error(
                    f"Failed to load element {func.id} @ {func.location}.")
                continue

            symbolNode = element[0]
            node = symbolNode.node

            if isinstance(node, Decorator):
                self.logger.info(
                    f"Detect decorators for {func.id}, use inner function.")
                node = node.func

            if not isinstance(node, FuncDef):
                self.logger.error(
                    f"Node {node} is not a function definition.")
                continue

            self.logger.debug(f"Visit AST of {func.id}")

            getter = CallsiteGetter(api, caller, resolver, self.logger)
            node.accept(getter)

            result.add(caller)

        return result
