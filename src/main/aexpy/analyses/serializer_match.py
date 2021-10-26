import json
from enum import Enum
from typing import Dict

from .models import (ApiCollection, ApiEntry, ApiManifest, ClassEntry,
                     AttributeEntry, FunctionEntry, Location, ModuleEntry,
                     Parameter, ParameterKind, SpecialEntry, SpecialKind)


def _filter_obj_dict(x):
    res = {}
    for k, v in x.__dict__.items():
        if str(k).startswith("_"):
            continue
        res[k] = v
    return res


def jsonify(x):
    match x:
        case FunctionEntry():
            return {
                "schema": "func",
                **_filter_obj_dict(x)
            }
        case AttributeEntry():
            return {
                "schema": "attr",
                **_filter_obj_dict(x)
            }
        case ClassEntry():
            return {
                "schema": "class",
                **_filter_obj_dict(x)
            }
        case ModuleEntry():
            return {
                "schema": "module",
                **_filter_obj_dict(x)
            }
        case SpecialEntry():
            return {
                "schema": "special",
                **_filter_obj_dict(x)
            }
        case ApiManifest():
            return _filter_obj_dict(x)
        case Enum():
            return x.value
        case _:
            return _filter_obj_dict(x)


def serialize(collection: ApiCollection, **kwargs) -> str:
    return json.dumps(collection, default=jsonify, **kwargs)


def deserializeApiEntry(entry: Dict) -> ApiEntry:
    schema = entry.pop("schema")
    data: Dict = entry
    locationData: Dict = data.pop("location")

    match schema:
        case "attr":
            binded = AttributeEntry(**data)
        case "module":
            binded = ModuleEntry(**data)
        case "class":
            binded = ClassEntry(**data)
        case "func":
            paras = data.pop("parameters")
            bindedParas = []
            for para in paras:
                kind = ParameterKind(para.pop("kind"))
                bindedParas.append(Parameter(kind=kind, **para))
            binded = FunctionEntry(parameters=bindedParas, **data)
        case "special":
            kind = SpecialKind(data.pop("kind"))
            binded = SpecialEntry(kind=kind, **data)

    assert isinstance(binded, ApiEntry)
    binded.location = Location(**locationData)
    return binded


def deserialize(text) -> ApiCollection:
    raw = json.loads(text)
    manifest = ApiManifest(**raw["manifest"])
    return ApiCollection(manifest, {key: deserializeApiEntry(entry) for key, entry in raw["entries"].items()})
