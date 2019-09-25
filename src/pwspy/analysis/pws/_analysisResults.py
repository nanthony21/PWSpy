from __future__ import annotations
from typing import Optional, Tuple
import h5py
import numpy as np
import os.path as osp
from datetime import datetime
import typing

from analysis import AbstractAnalysisSettings

if typing.TYPE_CHECKING:
    from pwspy.dataTypes import KCube
from analysis.pws._analysisSettings import AnalysisSettings
from pwspy.moduleConsts import dateTimeFormat
from pwspy.utility.misc import cached_property
from pwspy.analysis._abstract import AbstractAnalysisResults


def clearError(func):
    def newFunc(*args):
        try:
            return func(*args)
        except KeyError:
            raise KeyError(f"The analysis file does not contain a {func.__name__} item.")
    newFunc.__name__ = func.__name__  # failing to do this renaming can mess with other decorators e.g. cached_property
    return newFunc

def getFromDict(func):
    def newFunc(self, *args):
        if self.file is None:
            return self.dict[func.__name__]
        else:
            return func(self, *args)

    newFunc.__name__ = func.__name__
    return newFunc


class PWSAnalysisResults(AbstractAnalysisResults): #TODO All these cached properties stay in memory once they are loaded. It may be necessary to add a mechanism to decache them when memory is needed.
    """A loader for analysis results that will only load them from hard disk as needed."""

    @staticmethod
    def fields():
        return ['time', 'reflectance', 'meanReflectance', 'rms', 'polynomialRms', 'autoCorrelationSlope', 'rSquared',
                'ld', 'imCubeIdTag', 'referenceIdTag', 'extraReflectionTag', 'settings']

    @staticmethod
    def name2FileName(name: str) -> str:
        return f'analysisResults_{name}.h5'

    @staticmethod
    def fileName2Name(fileName: str) -> str:
        return fileName.split('analysisResults_')[1][:-3]

    @classmethod
    def create(cls, settings: AnalysisSettings, reflectance: KCube, meanReflectance: np.ndarray, rms: np.ndarray,
                polynomialRms: np.ndarray, autoCorrelationSlope: np.ndarray, rSquared: np.ndarray, ld: np.ndarray,
                imCubeIdTag: str, referenceIdTag: str, extraReflectionTag: Optional[str]):
        #TODO check datatypes here
        d = {'time': datetime.now().strftime(dateTimeFormat),
            'reflectance': reflectance,
            'meanReflectance': meanReflectance,
            'rms': rms,
            'polynomialRms': polynomialRms,
            'autoCorrelationSlope': autoCorrelationSlope,
            'rSquared': rSquared,
            'ld': ld,
            'imCubeIdTag': imCubeIdTag,
            'referenceIdTag': referenceIdTag,
            'extraReflectionTag': extraReflectionTag,
            'settings': settings}
        return cls(None, d)

    @cached_property
    @clearError
    @getFromDict
    def settings(self) -> AnalysisSettings:
        return AnalysisSettings.fromJsonString(self.file['settings'])

    @cached_property
    @clearError
    @getFromDict
    def imCubeIdTag(self) -> str:
        return bytes(np.array(self.file['imCubeIdTag'])).decode()

    @cached_property
    @clearError
    @getFromDict
    def referenceIdTag(self) -> str:
        return bytes(np.array(self.file['referenceIdTag'])).decode()

    @cached_property
    @clearError
    @getFromDict
    def time(self) -> str:
        return self.file['time']

    @cached_property
    @clearError
    @getFromDict
    def reflectance(self):
        from pwspy.dataTypes import KCube
        dset = self.file['reflectance']
        return KCube.fromHdfDataset(dset)

    @cached_property
    @clearError
    @getFromDict
    def meanReflectance(self) -> np.ndarray:
        dset = self.file['meanReflectance']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def rms(self) -> np.ndarray:
        dset = self.file['rms']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def polynomialRms(self) -> np.ndarray:
        dset = self.file['polynomialRms']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def autoCorrelationSlope(self) -> np.ndarray:
        dset = self.file['autoCorrelationSlope']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def rSquared(self) -> np.ndarray:
        dset = self.file['rSquared']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def ld(self) -> np.ndarray:
        dset = self.file['ld']
        return np.array(dset)

    @cached_property
    @clearError
    @getFromDict
    def opd(self) -> Tuple[np.ndarray, np.ndarray]:
        from pwspy.dataTypes import KCube
        dset = self.file['reflectance']
        cube = KCube.fromHdfDataset(dset)
        opd, opdIndex = cube.getOpd(isHannWindow=True, indexOpdStop=100)
        return opd, opdIndex

    @cached_property
    @clearError
    @getFromDict
    def extraReflectionTag(self) -> str:
        return bytes(np.array(self.file['extraReflectionTag'])).decode()