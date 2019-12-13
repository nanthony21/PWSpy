from __future__ import annotations
import numpy as np
import tifffile as tf
import os, json
from typing import Optional
import typing
from ._metadata import FluorMetaData
if typing.TYPE_CHECKING:
    from ._AcqDir import AcqDir


class FluorescenceImage:
    def __init__(self, data: np.ndarray, md: FluorMetaData):
        self.data = data
        self.metadata = md

    @classmethod
    def fromTiff(cls, directory: str, acquisitionDirectory: Optional[AcqDir] = None):
        md = FluorMetaData.fromTiff(directory, acquisitionDirectory) #This will raise an error if the folder isn't valid
        return cls.fromMetadata(md)

    @classmethod
    def fromMetadata(cls, md: FluorMetaData):
        path = os.path.join(md.filePath, FluorMetaData.FILENAME)
        img = tf.TiffFile(path)
        return cls(img.asarray(), md)

    def toTiff(self, directory: str):
        with open(os.path.join(directory, FluorMetaData.FILENAME), 'wb') as f:
            tf.imsave(f, self.data)
        with open(os.path.join(directory, FluorMetaData.MDPATH), 'w') as f:
            json.dump(self.metadata, f)
