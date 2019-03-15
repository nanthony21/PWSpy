import json
from typing import Tuple

import h5py
import jsonschema

from pwspy.imCube.ICBaseClass import ICBase
import numpy as np
import os


class ExtraReflectanceCube(ICBase):
    _jsonSchema = {"$schema": "http://json-schema.org/schema#",
                   '$id': 'extraReflectionMetadataSchema',
                   'title': 'extraReflectionMetadataSchema',
                   'required': ['system', 'description'],
                   'type': 'object',
                   'properties': {
                       'system': {'type': 'string'},
                       'description': {'type': 'string'}
                        }
                   }

    def __init__(self, data: np.ndarray, wavelengths:Tuple[float, ...], metadata: dict):
        jsonschema.validate(instance=metadata, schema=self._jsonSchema)
        if data.max() > 1 or data.min() < 0:
            raise ValueError("Reflectance values must be between 0 and 1")
        super().__init__(data, wavelengths)
        self.metadata = metadata

    @property
    def idTag(self):
        return f"ExtraReflection_{self.metadata['system']}_{self.metadata['time']}"

    @property
    def wavelengths(self) -> Tuple[float, ...]:
        return self.index

    @classmethod
    def load(cls, directory: str, name: str):
        with h5py.File(os.path.join(directory, f'{name}_eReflectance.h5')) as hf:
            dset = hf['extraReflection']
            data, index = ICBase._decodeHdf(dset)
            return cls(data, index, json.loads(dset.attrs['metadata']))

    def save(self, directory: str, name: str) -> None:
        savePath = os.path.join(directory, f'{name}_eReflectance.h5')
        if os.path.exists(savePath):
            raise OSError(f"The path {savePath} already exists.")
        with h5py.File(savePath, 'w') as hf:
            hf = ICBase.toHdf(hf, 'extraReflection')
            hf.attrs['metadata'] = np.string_(json.dumps(self.metadata))