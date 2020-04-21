from __future__ import annotations
import dataclasses
from datetime import datetime

import numpy as np
import pandas as pd
from numpy import ma
import multiprocessing as mp
import typing
from . import AbstractAnalysis, warnings, AbstractAnalysisSettings, AbstractRuntimeAnalysisSettings, \
    AbstractHDFAnalysisResults, AbstractAnalysisGroup
from pwspy import dateTimeFormat
import pwspy.dataTypes as pwsdt
from pwspy.utility.misc import cached_property
from pwspy.utility.reflection import reflectanceHelper, Material


def getFromDict(func):
    """This decorator makes it so that the function will only be evaluated if self.file is not None.
    If self.file is None then we will just search self.dict for a value with a key matching the name of the decorated function.
    We use this because while we often want to load data from a file for use, we also want to support the case of an object
    that has been created but has not yet been saved to a file."""
    def newFunc(self, *args):
        if self.file is None:
            return self.dict[func.__name__]
        else:
            return func(self, *args)

    newFunc.__name__ = func.__name__
    return newFunc


class DynamicsAnalysis(AbstractAnalysis):
    """This class performs the analysis of RMS_t_squared and D described in the paper: "Multimodal interferometric imaging of nanoscale structure and
    macromolecular motion uncovers UV induced cellular paroxysm". It is based on a set of matlab scripts written by the author of that paper, Scott Gladstein.
     The original scripts can be found in the `_oldMatlab` subpackage."""
    def __init__(self, settings: DynamicsRuntimeAnalysisSettings, ref: pwsdt.DynCube):
        super().__init__()
        extraReflectance = pwsdt.ExtraReflectanceCube.fromMetadata(settings.extraReflectanceMetadata) if settings.extraReflectanceMetadata is not None else None
        settings = settings.getSaveableSettings()
        assert ref.processingStatus.cameraCorrected
        ref.normalizeByExposure()
        if ref.metadata.pixelSizeUm is not None:  # Only works if pixel size was saved in the metadata.
            ref.filterDust(.75)  # Apply a blur to filter out dust particles. This is in microns. I'm not sure if this is the optimal value.
        if settings.referenceMaterial is None:
            theoryR = pd.Series(np.ones((len(ref.times),)), index=ref.times)  # Having this as all ones effectively ignores it.
            print("Warning: DynamicsAnalysis ignoring reference material correction")
        else:
            theoryR = reflectanceHelper.getReflectance(settings.referenceMaterial, Material.Glass, wavelengths=ref.metadata.wavelength, NA=settings.numericalAperture)
        if extraReflectance is None:
            Iextra = None  # a bogus reflection that is all zeros
            print("Warning: DynamicsAnalysis ignoring extra reflection")
        else:
            if extraReflectance.metadata.numericalAperture != settings.numericalAperture:
                print(f"Warning: The numerical aperture of your analysis does not match the NA of the Extra Reflectance Calibration. Calibration File NA: {extraReflectance.metadata.numericalAperture}. PWSAnalysis NA: {settings.numericalAperture}.")
            idx = np.asarray(np.array(extraReflectance.wavelengths) == ref.metadata.wavelength).nonzero()[0][0] #The index of extra reflectance that matches the wavelength of our dynamics cube
            I0 = ref.data.mean(axis=2) / (float(theoryR) + extraReflectance.data[:, :, idx]) #  I0 is the intensity of the illumination source, reconstructed in units of `counts`. this is an inversion of our assumption that reference = I0*(referenceReflectance + extraReflectance)
            Iextra = I0 * extraReflectance.data[:, :, idx] #  Convert from reflectance to predicted counts/ms.
            ref.subtractExtraReflection(Iextra)  # remove the extra reflection from our data#
        if not settings.relativeUnits:
            ref = ref / theoryR[None, None, :]  # now when we normalize by our reference we will get a result in units of physical reflectance rather than arbitrary units.

        self.refMean = ref.data.mean(axis=2)
        ref.normalizeByReference(self.refMean)  # We normalize so that the average is 1. This is for scaling purposes with the AC. Seems like the AC should be scale independent though, not sure.
        self.refAc = ref.getAutocorrelation()[:, :, :settings.diffusionRegressionLength+1].mean(axis=(0, 1))  # We find the average autocorrlation of the background to cut down on noise, presumably this is uniform accross the field of view any way, right?
        self.refTag = ref.metadata.idTag
        self.erTag = extraReflectance.metadata.idTag if extraReflectance is not None else None
        self.n_medium = 1.37  # The average index of refraction for chromatin?
        self.settings = settings
        self.extraReflection = Iextra

    def run(self, cube: pwsdt.DynCube) -> Tuple[DynamicsAnalysisResults, List[warnings.AnalysisWarning]]:
        assert cube.processingStatus.cameraCorrected
        warns = []
        cube.normalizeByExposure()
        if self.extraReflection is not None:
            cube.subtractExtraReflection(self.extraReflection)
        cube.normalizeByReference(self.refMean)

        cubeAc = cube.getAutocorrelation()
        cubeAc = cubeAc[:, :, :self.settings.diffusionRegressionLength+1] # We are only going to use the first few time points of the ACF, we can get rid of the rest.
        rms_t_squared = cubeAc[:, :, 0] - self.refAc[0]  # The rms^2 noise of the reference averaged over the whole image.
        rms_t_squared[rms_t_squared < 0] = 0  # Sometimes the above noise subtraction can cause some of our values to be barely below 0, that's going to be a problem.
        # If we didn't care about noise subtraction we could get rms_t as just `cube.data.std(axis=2)`

        # Determine the mean-reflectance for each pixel in the cell.
        reflectance = cube.data.mean(axis=2)

        #Diffusion
        cubeAc = ma.array(cubeAc) # Convert to the numpy.MaskedArray type to help us mark some data as invalid.
        cubeAc[cubeAc.data[:, :, 0] < np.sqrt(2)*self.refAc[0]] = ma.masked # Remove pixels with low SNR. Default threshold removes values where 1st point of acf is less than sqrt(2) of background acf
        ac = ma.array(cubeAc - self.refAc)  # Background subtracted autocorrelation function.
        ac = ac / ac[:, :, 0][:, :, None]  # Normalize by the zero-lag value
        ac[np.any(ac <= 0, axis=2)] = ma.masked  # Before taking the log of the autocorrelation any negative or zero values will cause problems. Remove the pixel entirely

        dt = (cube.times[-1] - cube.times[0]) / (len(cube.times) - 1) / 1e3  # Convert to seconds
        k = (self.n_medium * 2 * np.pi) / (cube.metadata.wavelength / 1e3)  # expressing wavelength in microns to match up with old matlab code.
        val = np.log(ac) / (4 * k ** 2) # See the `theory` section of the paper for an explanation of the 4k^2. The slope of log(ac) should be equivalent to 1/t_c in the paper.
        d_slope = -self._maskedLinearRegression(val, dt) # Get the slope of the autocorrelation. This is related to the diffusion in the cell. The minus is here to make the number positive, the slope is really negative.

        results = DynamicsAnalysisResults.create(meanReflectance=reflectance,
                                                 rms_t_squared=rms_t_squared,
                                                 reflectance=cube,
                                                 diffusion=d_slope,
                                                 settings=self.settings,
                                                 imCubeIdTag=cube.metadata.idTag,
                                                 referenceIdTag=self.refTag,
                                                 extraReflectionIdTag=self.erTag)

        return results, warns

    @staticmethod
    def _maskedLinearRegression(arr: ma.MaskedArray, dt: float):
        """Takes a 3d ACF array as input and returns a 2d array indicating the slope along the 3rd dimension of the input array.
         The dimensions of the output array match the first two dimensions of the input array. The input array can have invalid pixels masked out, this function
         will exclude them from the calculation."""
        origShape = arr.shape
        y = np.reshape(arr, (origShape[0]*origShape[1], origShape[2]))  #Convert to a 2d array [pixels, time]. This is required by the polyfit function.
        t = np.array([i*dt for i in range(origShape[2])]) # Generate a 1d array representing the time axis.
        # Y = np.reshape(y[~y.mask], (np.sum((~y.mask).sum()//y.shape[1], y.shape[1])))  # Remove all the masked pixels since the polyfit function doesn't know what to do with them.
        Y = np.reshape(y[~y.mask], ((~y.mask).sum()//y.shape[1], y.shape[1]))  # Remove all the masked pixels since the polyfit function doesn't know what to do with them.
        coeff = np.polyfit(t, Y.T, deg=1)  # Linear fit
        slope = coeff[0, :]  # Get the slope and ignore the y intercept
        Slope = ma.zeros(y.shape[0]) # Create an empty masked array that includes all pixels again
        Slope.mask = y.mask[:, 0] # Copy the original mask indicating which pixels are invalid.
        Slope[~Slope.mask] = slope  # Fill our calculated slopes into the yunmasked pixels.
        Slope = np.reshape(Slope, (origShape[0], origShape[1])) # Reshape back to a 2d image
        return Slope

    def copySharedDataToSharedMemory(self):
        refdata = mp.RawArray('f', self.refAc.size)
        refdata = np.frombuffer(refdata, dtype=np.float32).reshape(self.refAc.shape)
        np.copyto(refdata, self.refAc)
        self.refAc = refdata

        refmdata = mp.RawArray('f', self.refMean.size)
        refmdata = np.frombuffer(refmdata, dtype=np.float32).reshape(self.refMean.shape)
        np.copyto(refmdata, self.refMean)
        self.refMean = refmdata

        if self.extraReflection is not None:
            iedata = mp.RawArray('f', self.extraReflection.size)
            iedata = np.frombuffer(iedata, dtype=np.float32).reshape(self.extraReflection.shape)
            np.copyto(iedata, self.extraReflection)
            self.extraReflection = iedata


class DynamicsAnalysisResults(AbstractHDFAnalysisResults):
    @staticmethod
    def fields():
        return ['meanReflectance', 'reflectance', 'rms_t_squared', 'diffusion', 'time', 'settings', 'imCubeIdTag', 'referenceIdTag', 'extraReflectionIdTag']

    @staticmethod
    def name2FileName(name: str) -> str:
        return f'dynAnalysisResults_{name}.h5'

    @staticmethod
    def fileName2Name(fileName: str) -> str:
        return fileName.split('dynAnalysisResults_')[1][:-3]

    @classmethod
    def create(cls, settings: DynamicsAnalysisSettings, meanReflectance: np.ndarray, rms_t_squared: np.ndarray, reflectance: pwsdt.DynCube, diffusion: np.ndarray,
                imCubeIdTag: str, referenceIdTag: str, extraReflectionIdTag: typing.Optional[str]):
        #TODO check datatypes here
        d = {'time': datetime.now().strftime(dateTimeFormat),
            'meanReflectance': meanReflectance,
            'reflectance': reflectance,
            'diffusion': diffusion,
            'rms_t_squared': rms_t_squared,
            'imCubeIdTag': imCubeIdTag,
            'referenceIdTag': referenceIdTag,
            'extraReflectionIdTag': extraReflectionIdTag,
            'settings': settings}
        return cls(None, d)

    @cached_property
    @getFromDict
    def meanReflectance(self) -> np.ndarray:
        dset = self.file['meanReflectance']
        return np.array(dset)

    @cached_property
    @getFromDict
    def rms_t_squared(self) -> np.ndarray:
        dset = self.file['rms_t_squared']
        return np.array(dset)

    @cached_property
    @getFromDict
    def settings(self) -> DynamicsAnalysisSettings:
        return DynamicsAnalysisSettings.fromJsonString(self.file['settings'])

    @cached_property
    @getFromDict
    def reflectance(self) -> pwsdt.DynCube:
        dset = self.file['reflectance']
        return pwsdt.DynCube.fromHdfDataset(dset)

    @cached_property
    @getFromDict
    def diffusion(self) -> np.ndarray:
        dset = self.file['diffusion']
        return np.array(dset)

    @cached_property
    @getFromDict
    def imCubeIdTag(self) -> str:
        return bytes(np.array(self.file['imCubeIdTag'])).decode()

    @cached_property
    @getFromDict
    def referenceIdTag(self) -> str:
        return bytes(np.array(self.file['referenceIdTag'])).decode()

    @cached_property
    @getFromDict
    def time(self) -> str:
        return self.file['time']

    @cached_property
    @getFromDict
    def extraReflectionIdTag(self) -> str:
        return bytes(np.array(self.file['extraReflectionIdTag'])).decode()


@dataclasses.dataclass
class DynamicsAnalysisSettings(AbstractAnalysisSettings):
    """These settings determine the behavior of the `DynamicsAnalysis` class.
        Args:
            extraReflectanceId: The unique `IDTag` of the extraReflectance calibration that was used on this analysis.
            referenceMaterial: The material that was imaged in the reference image of this analysis. Found as an in pwspy.moduleConst.Material. The
                theoretically predicted
                reflectance of the reference image is used in the extraReflectance correction.
            numericalAperture: The illumination NA of the system. This is used for two purposes. First, we want to make sure that the NA of our data matches
                the NA of our extra reflectance correction cube.
                Second, the theoretically predicted reflectance of our reference is based not only on what our refereMaterial is but also the NA since
                reflectance is angle dependent.
            relativeUnits: If `True` then all calculation are performed such that the reflectance is 1 if it matches the reference. If `False` then we use the
                theoretical reflectance of the reference  (based on NA and reference material) to normalize our results to the actual physical reflectance of
                the sample (about 0.4% for water)
            diffusionRegressionLength: The original matlab scripts for analysis of dynamics data determined the slope of the log(ACF) by looking only at the
                first two indices, (log(ACF)[1]-log(ACF)[0])/dt. This results in very noisy results. However as you at higher index value of the log(ACF) the
                noise becomes much worse. A middle ground is to perform linear regression on the first 4 indices to determine the slope. You can adjust that
                number here.
    """
    extraReflectanceId: str
    referenceMaterial: Material
    numericalAperture: float
    relativeUnits: bool
    diffusionRegressionLength: int = 3

    FileSuffix = "dynAnalysis"  # This is used for saving and loading to json

    def __post_init__(self):
        assert self.diffusionRegressionLength > 0
        assert self.diffusionRegressionLength < 20  # Even 20 is probably way too long, unless a system is created with extremely low noise.

    def _asDict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.referenceMaterial is None:
            d['referenceMaterial'] = None
        else:
            d['referenceMaterial'] = self.referenceMaterial.name  # Convert from enum to string
        return d

    @classmethod
    def _fromDict(cls, d: dict) -> DynamicsAnalysisSettings:
        if d['referenceMaterial'] is not None:
            d['referenceMaterial'] = Material[d['referenceMaterial']]  # Convert from string to enum
        return cls(**d)


class DynamicsAnalysisGroup(AbstractAnalysisGroup):
    """This class is simply used to group together analysis classes that are compatible with eachother."""
    @staticmethod
    def settingsClass() -> typing.Type[DynamicsAnalysisSettings]:
        return DynamicsAnalysisSettings

    @staticmethod
    def resultsClass() -> typing.Type[DynamicsAnalysisResults]:
        return DynamicsAnalysisResults

    @staticmethod
    def analysisClass() -> typing.Type[DynamicsAnalysis]:
        return DynamicsAnalysis


@dataclasses.dataclass
class DynamicsRuntimeAnalysisSettings(AbstractRuntimeAnalysisSettings):
    settings: DynamicsAnalysisSettings
    extraReflectanceMetadata: typing.Optional[pwsdt.ERMetaData]

    def getSaveableSettings(self) -> DynamicsAnalysisSettings:
        return self.settings