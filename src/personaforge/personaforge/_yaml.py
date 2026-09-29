from pathlib import Path
from typing import Any, Type

import yaml


class UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_mapping(loader: UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found duplicate key {!r}".format(key),
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_yaml(path: Path, error_type: Type[ValueError]) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return yaml.load(stream, Loader=UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise error_type("{}: {}".format(path, exc)) from exc
