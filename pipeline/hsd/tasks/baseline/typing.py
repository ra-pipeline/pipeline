from typing import TypeAlias

ClusteringResult: TypeAlias = tuple[int, list[list[int | bool]], list[int], list[list[int | float | bool]]]
DetectedLineList: TypeAlias = list[list[int | float | bool]]
LineProperty: TypeAlias = list[float | bool]
LineWindow: TypeAlias = str | dict | list[int] | list[float] | list[str]
FitFunc: TypeAlias = str | dict[int | str, str]
FitOrder: TypeAlias = str | int | dict[int | str, int]
