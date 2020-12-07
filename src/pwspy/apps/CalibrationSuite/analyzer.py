# -*- coding: utf-8 -*-
"""
Created on Mon Oct 26 16:44:06 2020

@author: nick
"""
import traceback
import cv2
from pwspy.apps.CalibrationSuite.ITOMeasurement import ITOMeasurement, CalibrationResult
from pwspy.apps.CalibrationSuite.TransformGenerator import TransformGenerator
from pwspy.apps.CalibrationSuite._utility import CVAffineTransform
from pwspy.utility.reflection import Material
import pwspy.analysis.pws as pwsAnalysis
import numpy as np
from glob import glob
import os
import logging
from scipy.ndimage import binary_dilation
from ._scorers import *
from pwspy.utility.plotting import PlotNd

settings = pwsAnalysis.PWSAnalysisSettings.loadDefaultSettings("Recommended")
settings.referenceMaterial = Material.Air

logger = logging.getLogger(__name__)

class AbstractMeasurementLoader(abc.ABC):
    """
    In charge of loading ITO measurements from a folder structure. Multiple classes of this type could be made to support loading from
    different folder organization schemes.
    """
    @property
    @abc.abstractmethod
    def template(self) -> ITOMeasurement:
        pass

    @property
    @abc.abstractmethod
    def measurements(self) -> typing.Iterable[ITOMeasurement]:
        pass


class DateMeasurementLoader(AbstractMeasurementLoader):
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

        self._measurements = tuple(self._measurements)

    def template(self) -> ITOMeasurement:
        return self._template

    def measurements(self) -> typing.Iterable[ITOMeasurement]:
        return self._measurements


class ITOAnalyzer:
    """
    This class uses a template measurement to analyze a series of other measurements and give them scores for how well they match to the template.

    Args:
        loader: An object that loads the template and measurements from file.
    """
    def __init__(self, loader: AbstractMeasurementLoader):
        self._loader = loader

        self._matcher = TransformGenerator(loader.template.analysisResults, debugMode=False, fastMode=True)

        self.resultPairs = self._generateTransforms(useCached=True)

        self.scores = []
        for measurement, result in self.resultPairs:
            logger.debug(f"Scoring measurement {measurement.name}")
            scorer = CombinedScorer(loader.template.analysisResults, result)
            self.scores.append(scorer._scores)
        a = 1

    def _generateTransforms(self, useCached: bool = True):
        resultPairs = []
        if useCached:
            needsProcessing = []
            for m in self._loader.measurements:
                if self._loader.template.idTag in m.listCalibrationResults():
                    logger.debug(f"Loading cached results for {m.name}")
                    result = m.loadCalibrationResult(self._loader.template.idTag)
                    resultPairs.append((m, result))
                else:
                    needsProcessing.append(m)
        else:
            needsProcessing = self._loader.measurements
        transforms = self._matcher.match([i.analysisResults for i in needsProcessing])

        for transform, measurement in zip(transforms, needsProcessing):
            logger.debug(f"Generating new results for {measurement.name}")
            if transform is None:
                logger.debug(f"Skipping transformation of {measurement.name}")
            else:
                # Refine transform, set scale=1 and rotation=0, we only expect to have translation. Maybe we shouldn't be coercing rotation?
                transform = CVAffineTransform.fromPartialMatrix(transform)
                assert abs(transform.scale[0]-1) < .005, f"The estimated transform includes a scaling factor of {abs(transform.scale[0]-1)*100} percent!"
                assert np.abs(np.rad2deg(transform.rotation)) < .2, f"The estimated transform include a rotation of {np.rad2deg(transform.rotation)} degrees!"
                transform = CVAffineTransform(scale=1, rotation=0, shear=0, translation=transform.translation)  # Coerce scale and rotation
                transform = transform.toPartialMatrix()
                reflectance = self._applyTransform(transform, measurement)
                result = CalibrationResult.create(self._loader.template.idTag, transform, reflectance)
                measurement.saveCalibrationResult(result, overwrite=True)
                resultPairs.append((measurement, result))
        return resultPairs

    @staticmethod
    def _applyTransform(transform, measurement):
        logger.debug(f"Starting data transformation of {measurement.name}")
        # TODO default warp interpolation is bilinear, should we instead use nearest-neighbor?
        im = measurement.analysisResults.meanReflectance
        tform = cv2.invertAffineTransform(transform)
        meanReflectance = cv2.warpAffine(im, tform, im.shape, borderValue=-666.0)  # Blank regions after transform will have value -666, can be used to generate a mask.
        mask = meanReflectance == -666.0
        mask = binary_dilation(mask)  # Due to interpolation we sometimes get weird values at the edge. dilate the mask so that those edges get cut off.
        kcube = measurement.analysisResults.reflectance
        reflectance = np.zeros_like(kcube.data)
        for i in range(kcube.data.shape[2]):
            reflectance[:, :, i] = cv2.warpAffine(kcube.data[:, :, i], tform, kcube.data.shape[:2]) + meanReflectance
        measurement.analysisResults.releaseMemory()
        reflectance[mask] = np.nan
        return reflectance



