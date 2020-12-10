# -*- coding: utf-8 -*-
"""
Created on Mon Oct 26 16:44:06 2020

@author: nick
"""
import cv2
from pwspy.apps.CalibrationSuite.ITOMeasurement import ITOMeasurement, TransformedData
from pwspy.apps.CalibrationSuite.TransformGenerator import TransformGenerator
from pwspy.apps.CalibrationSuite._utility import CVAffineTransform, CubeSplitter, DualCubeSplitter
from pwspy.utility.reflection import Material
import logging
from scipy.ndimage import binary_dilation
from ._scorers import *
from .loaders import settings, AbstractMeasurementLoader
from pwspy.utility.plotting import PlotNd
import matplotlib.pyplot as plt

settings.referenceMaterial = Material.Air

logger = logging.getLogger(__name__)


class Analyzer:
    """
    This class uses a template measurement to analyze a series of other measurements and give them scores for how well they match to the template.

    Args:
        loader: An object that loads the template and measurements from file.
    """
    def __init__(self, loader: AbstractMeasurementLoader, useCached: bool = True, debugMode: bool = False):
        self._loader = loader

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

        self._matcher = TransformGenerator(loader.template.analysisResults, debugMode=debugMode, fastMode=True)
        transforms = self._matcher.match([i.analysisResults for i in needsProcessing])

        transformedData = []
        for transform, measurement in zip(transforms, needsProcessing):
            if transform is None:
                logger.debug(f"Skipping transformation of {measurement.name}")
            else:
                transformedData.append(self._transformData(measurement, transform))

        # Scoring the bulk arrays
        for measurement, data in zip(needsProcessing, transformedData):
            logger.debug(f"Scoring measurement {measurement.name}")
            slc = data.getValidDataSlice()
            templateArr = (loader.template.analysisResults.reflectance + loader.template.analysisResults.meanReflectance[:, :, None])[slc]
            testArr = data.data[slc]
            scorer = CombinedScorer(templateArr, testArr)
            result = CalibrationResult.create(
                templateIdTag=loader.template.idTag,
                affineTransform=data.affineTransform,
                transformedData=data.data,
                scores=scorer._scores
            )
            measurement.saveCalibrationResult(result, overwrite=True)
        a = 1

        # Use the cube splitter to view scores at a smaller scale
        # idx = 1
        # slc = self.resultPairs[idx][1].getValidDataSlice()
        # arr1 = self.resultPairs[idx][1].transformedData[slc]
        # arr2 = self._loader.template.analysisResults.reflectance.data + self._loader.template.analysisResults.meanReflectance[:, :, None]
        # arr2 = arr2[slc]
        # c = DualCubeSplitter(arr2, arr1)
        # def score(arr1, arr2):
        #     comb = MSEScorer(arr1, arr2)
        #     return comb.score()
        # for factor in range(1, 5):
        #     out = c.apply(score, factor)
        #     plt.figure()
        #     plt.imshow(out, cmap='gray')
        #     plt.colorbar()
        # a = 1

        # View the full SSIM result array
        # idx = 0
        # slc = self.resultPairs[idx][1].getValidDataSlice()
        # arr1 = self.resultPairs[idx][1].transformedData[slc]
        # arr2 = self._loader.template.analysisResults.reflectance.data + self._loader.template.analysisResults.meanReflectance[:, :, None]
        # arr2 = arr2[slc]
        # from skimage.metrics import structural_similarity
        # score, full = structural_similarity(arr2, arr1, full=True)
        # p = PlotNd(full)
        # a = 1
        # for measurement, result in self.resultPairs:
        #     logger.debug(f"Scoring SubArrays of {measurement.name}")

    def _transformData(self, measurement: ITOMeasurement, transform: np.ndarray) -> TransformedData:
        """

        Args:
            measurement: A single `Measurement` of the calibration standard
            transform: The 2x3 affine transformation mapping the raw data to the template data.

        Returns:
            A transformeddata object
        """
        # Refine transform, set scale=1 and rotation=0, we only expect to have translation.  TODO Maybe we shouldn't be coercing rotation?
        transform = CVAffineTransform.fromPartialMatrix(transform)
        assert abs(transform.scale[0]-1) < .005, f"The estimated transform includes a scaling factor of {abs(transform.scale[0]-1)*100} percent!"
        assert np.abs(np.rad2deg(transform.rotation)) < .2, f"The estimated transform includes a rotation of {np.rad2deg(transform.rotation)} degrees!"
        transform = CVAffineTransform(scale=1, rotation=0, shear=0, translation=transform.translation)  # Coerce scale and rotation
        transform = transform.toPartialMatrix()
        reflectance = self._applyTransform(transform, measurement)
        return TransformedData(transform, reflectance)

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



