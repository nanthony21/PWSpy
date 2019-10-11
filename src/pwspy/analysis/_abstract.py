from __future__ import annotations
from abc import ABC, abstractmethod
import json
import os.path as osp
from typing import List
import typing
if typing.TYPE_CHECKING:
    from pwspy.dataTypes import ICBase
import h5py
import numpy as np

class AbstractAnalysisSettings(ABC):

    @classmethod
    def fromJson(cls, filePath: str, name: str):
        with open(osp.join(filePath, f'{name}_{cls.FileSuffix}.json'), 'r') as f:
            d=json.load(f)
        return cls._fromDict(d)

    def toJson(self, filePath: str, name: str):
        d = self._asDict()
        with open(osp.join(filePath, f'{name}_{self.FileSuffix}.json'), 'w') as f:
            json.dump(d, f, indent=4)

    def toJsonString(self):
        return json.dumps(self._asDict(), indent=4)

    @classmethod
    def fromJsonString(cls, string: str):
        return cls._fromDict(json.loads(string))

    @abstractmethod
    def _asDict(self) -> dict:
       pass

    @classmethod
    @abstractmethod
    def _fromDict(cls, d: dict) -> AbstractAnalysisSettings:
        pass

    @property
    @abstractmethod
    def FileSuffix(self):
        pass


class AbstractAnalysis(ABC):
    @abstractmethod
    def __init__(self, settings: AbstractAnalysisSettings):
        """Does all of the one-time tasks needed to start running an analysis. e.g. prepare the reference, load the extrareflection cube, etc."""
        self.settings = settings

    @abstractmethod
    def run(self, cube: ICBase) -> AbstractAnalysisResults:
        """Given an ImCube to analyze this function returns an instanse of AnalysisResults. In the PWSAnalysisApp this function is run in parallel by the AnalysisManager."""
        pass

class AbstractAnalysisResults(ABC):
    @classmethod
    @abstractmethod
    def create(cls):
        """Used to create results from existing variables. These results can then be saved to file."""
        pass

    @classmethod
    @abstractmethod
    def load(cls, directory: str, name: str):
        """Used to load results from a saved file"""
        pass


class AbstractHDFAnalysisResults(AbstractAnalysisResults):
    def __init__(self, file: h5py.File, variablesDict: dict, analysisName: Optional[str] = None):
        """"Can be instantiated with one of the two arguments. To load from file provide the h5py file. To create from variable provide a dictionary keyed by all the field names."""
        if file is not None:
            assert variablesDict is None
        elif variablesDict is not None:
            assert file is None
        self.file = file
        self.dict = variablesDict
        self.analysisName = analysisName


    @staticmethod
    @abstractmethod
    def fields() -> List[str]:
        pass

    @staticmethod
    @abstractmethod
    def _name2FileName(name: str) -> str:
        pass

    @staticmethod
    @abstractmethod
    def fileName2Name(fileName: str) -> str:
        pass

    def toHDF(self, directory: str, name: str):
        from pwspy.dataTypes import KCube #Need this for instance checking
        fileName = osp.join(directory, self._name2FileName(name))
        if osp.exists(fileName):
            raise OSError(f'{fileName} already exists.')
        # now save the stuff
        with h5py.File(fileName, 'w') as hf:
            for field in self.fields():
                k = field
                v = getattr(self, field)
                if isinstance(v, AbstractAnalysisSettings):
                    v = v.toJsonString()
                if isinstance(v, str):
                    hf.create_dataset(k, data=np.string_(v))  # h5py recommends encoding strings this way for compatability.
                elif isinstance(v, KCube):
                    hf = v.toFixedPointHdfDataset(hf, k)
                elif isinstance(v, np.ndarray):
                    hf.create_dataset(k, data=v)
                elif v is None:
                    pass
                else:
                    raise TypeError(f"Analysis results type {k}, {type(v)} not supported or expected")

    @classmethod
    def load(cls, directory: str, name: str):
        filePath = osp.join(directory, cls._name2FileName(name))
        if not osp.exists(filePath):
            raise OSError("The analysis file does not exist.")
        file = h5py.File(filePath, 'r')
        return cls(file, None, name)

    def __del__(self):
        if self.file:
            self.file.close()
