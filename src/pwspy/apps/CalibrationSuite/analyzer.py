# -*- coding: utf-8 -*-
"""
Created on Mon Oct 26 16:44:06 2020

@author: nick
"""
import traceback
from datetime import datetime
import cv2
from pwspy.apps.CalibrationSuite.ITOMeasurement import ITOMeasurement
from pwspy.apps.CalibrationSuite.TransformGenerator import TransformGenerator
from pwspy.utility.reflection import Material
import pwspy.analysis.pws as pwsAnalysis
import numpy as np
from glob import glob
import os
import pandas as pd
import logging
from scipy.ndimage import binary_dilation
import weakref
settings = pwsAnalysis.PWSAnalysisSettings.loadDefaultSettings("Recommended")
settings.referenceMaterial = Material.Air


class ITOAnalyzer:
    _SETTINGS = settings
    _DATETIMEFORMAT = "%m_%d_%Y"

    def __init__(self, directory: str, templateDirectory: str):
        self._template = ITOMeasurement(templateDirectory, self._SETTINGS)

        self._measurements = []
        for f in glob(os.path.join(directory, '*')):
            if os.path.isdir(f):
                try:
                    self._measurements.append(ITOMeasurement(f, self._SETTINGS))
                except Exception as e:
                    print(f"Failed to load measurement at directory {f}")
                    print(traceback.print_exc())

        self._matcher = TransformGenerator(self._template.analysisResults, debugMode=False, fastMode=True)

        dates = [datetime.strptime(i.name, self._DATETIMEFORMAT) for i in self._measurements]
        self._data = pd.DataFrame({"measurements": [weakref.ref(i) for i in self._measurements]}, index=dates)

        #TODO use calibration results to save/load cached results
        self._generateTransforms()
        self.transformData()

    def _generateTransforms(self, useCached: bool = True):
        # TODO how to cache transforms (Save to measurement directory with a reference to the template directory?)
        transforms = self._matcher.match([i().analysisResults for i in self._data.measurements])
        self._data['transforms'] = transforms

    def transformData(self):
        logger = logging.getLogger(__name__)

        def applyTransform(row):
            if row.transforms is None:
                logger.debug(f"Skipping transformation of {row.measurements().name}")
                return None, None
            logger.debug(f"Starting data transformation of {row.measurements().name}")
            # TODO default warp interpolation is bilinear, should we instead use nearest-neighbor?
            im = row.measurements().analysisResults.meanReflectance
            tform = cv2.invertAffineTransform(row.transforms)
            meanReflectance = cv2.warpAffine(im, tform, im.shape, borderValue=-666.0)  # Blank regions after transform will have value -666, can be used to generate a mask.
            mask = meanReflectance == -666.0
            mask = binary_dilation(mask)  # Due to interpolation we sometimes get weird values at the edge. dilate the mask so that those edges get cut off.
            kcube = row.measurements().analysisResults.reflectance
            reflectance = np.zeros_like(kcube.data)
            for i in range(kcube.data.shape[2]):
                reflectance[:, :, i] = cv2.warpAffine(kcube.data[:, :, i], tform, kcube.data.shape[:2]) + meanReflectance
            row.measurements().analysisResults.releaseMemory()
            reflectance[mask] = np.nan
            return tuple((reflectance,))  # Bad things happen if you put a numpy array directly into a dataframe. That's why we have the tuple.

        self._data['reflectance'] = self._data.apply(applyTransform, axis=1)


