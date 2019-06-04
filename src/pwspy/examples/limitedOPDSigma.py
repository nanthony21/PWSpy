# -*- coding: utf-8 -*-
"""
Created on Tue Jan  8 10:07:20 2019

@author: Nick Anthony
"""

from pwspy import ImCube, KCube, CameraCorrection
import matplotlib.pyplot as plt
import scipy.signal as sps
import os
import numpy as np
import scipy as sp

'''User Input'''
path = r'G:\Data\LCPWS1TimeSeriesCorrelation\2_7_2019 11.07'
refName = 'Cell999'  # This is an imcube of glass, used for normalization.
cellNames = ['Cell1', 'Cell2']  # , 'Cell3', 'Cell4','Cell5']
maskSuffix = 'resin'

# identify the depth in um to which the OPD spectra need to be integrated
integrationDepth = 2.0  ##  in um
isHannWindow = True  # Should Hann windowing be applied to eliminate edge artifacts?
subtractResinOpd = True
resetResinMasks = False
wvStart = 510  # start wavelength for poly subtraction
wvEnd = 690  # end wavelength for poly subtraction
sampleRI = 1.545  # The refractive index of the resin. This is taken from matlab code, I don't know if it's correct.
orderPolyFit = 0
wv_step = 2
correction = CameraCorrection(2000, (0.977241216, 1.73E-06, 1.70E-11))

'''************'''

b, a = sps.butter(6, 0.1 * wv_step)
opdIntegralEnd = integrationDepth * 2 * sampleRI  # We need to convert from our desired depth into an opd value. There are some questions about having a 2 here but that's how it is in the matlab code so I'm keeping it.

### load and save mirror or glass image cube
ref = ImCube.loadAny(os.path.join(path, refName))
ref.correctCameraEffects(correction)
ref.filterDust(6)
ref.normalizeByExposure()

if subtractResinOpd:
    ### load and save reference empty resin image cube
    fig, ax = plt.subplots()
    resinOpds = {}
    for cellName in cellNames:
        resin = ImCube.loadAny(os.path.join(path, cellName))
        resin.correctCameraEffects(correction)
        resin.normalizeByExposure()
        resin /= ref
        resin = KCube.fromImCube(resin)
        if resetResinMasks:
            [resin.deleteMask(i, maskSuffix) for i in resin.getMasks()[maskSuffix]]
        if maskSuffix in resin.getMasks():
            mask = resin.loadMask(1, maskSuffix)
        else:
            print('Select a region containing only resin.')
            mask = resin.selectLassoROI()
            resin.saveMask(mask, 1, maskSuffix)
        resin.data -= resin.data.mean(axis=2)[:, :, np.newaxis]
        opdResin, xvals = resin.getOpd(isHannWindow, indexOpdStop=None, mask=mask)
        resinOpds[cellName] = opdResin
        ax.plot(xvals, opdResin, label=cellName)
        ax.vlines([opdIntegralEnd], ymin=opdResin.min(), ymax=opdResin.max())
        ax.set_xlabel('OPD')
        ax.set_ylabel("Amplitude")
    ax.legend()
    plt.pause(0.2)

rmses = {}  # Store the rms maps for later saving
for cellName in cellNames:
    cube = ImCube.loadAny(os.path.join(path, cellName))
    cube.correctCameraEffects(correction)
    cube.normalizeByExposure()
    cube /= ref
    cube.data = sps.filtfilt(b, a, cube.data, axis=2)
    cube = KCube.fromImCube(cube)

    ## -- Polynomial Fit
    print("Subtracting Polynomial")
    polydata = cube.data.reshape((cube.data.shape[0] * cube.data.shape[1], cube.data.shape[2]))
    polydata = np.rollaxis(polydata, 1)  # Flatten the array to 2d and put the wavenumber axis first.
    cubePoly = np.zeros(polydata.shape)  # make an empty array to hold the fit values.
    polydata = np.polyfit(cube.wavenumbers, polydata,
                          orderPolyFit)  # At this point polydata goes from holding the cube data to holding the polynomial values for each pixel. still 2d.
    for i in range(orderPolyFit + 1):
        cubePoly += (np.array(cube.wavenumbers)[:, np.newaxis] ** i) * polydata[i,
                                                                       :]  # Populate cubePoly with the fit values.
    cubePoly = np.moveaxis(cubePoly, 0, 1)
    cubePoly = cubePoly.reshape(cube.data.shape)  # reshape back to a cube.
    # Remove the polynomial fit from filtered cubeCell.
    cube.data = cube.data - cubePoly

    # Find the fft for each signal in the desired wavelength range
    opdData, xvals = cube.getOpd(isHannWindow, None)

    if subtractResinOpd:
        opdData = opdData - resinOpds[cellName]

    rmsData = np.sqrt(np.mean(cube.data ** 2, axis=2))
    try:
        integralStopIdx = np.where(xvals >= opdIntegralEnd)[0][0]
    except IndexError:  # If we get an index error here then our opdIntegralEnd is probably bigger than we can achieve. Just use the biggest value we have.
        integralStopIdx = None
        opdIntegralEnd = max(xvals)
        print(f'Integrating to OPD {opdIntegralEnd}')

    opdSquared = np.sum(opdData[:, :, :integralStopIdx] ** 2,
                        axis=2)  # Parseval's theorem tells us that this is equivalent to the sum of the squares of our original signal
    opdSquared *= len(cube.wavenumbers) / opdData.shape[
        2]  # If the original data and opd were of the same length then the above line would be correct. Since the fft has been upsampled. we need to normalize.
    rmsOpdIntData = np.sqrt(
        opdSquared)  # this should be equivalent to normal RMS if our stop index is high and resin subtraction is disabled.

    cmap = plt.get_cmap('jet')
    fig, axs = plt.subplots(1, 2)
    im = axs[0].imshow(rmsData, cmap=cmap, clim=[np.percentile(rmsData, 0.5), np.percentile(rmsData, 99.5)])
    fig.colorbar(im, ax=axs[0])
    axs[0].set_title('RMS')
    im = axs[1].imshow(rmsOpdIntData, cmap=cmap,
                       clim=[np.percentile(rmsOpdIntData, 0.5), np.percentile(rmsOpdIntData, 99.5)])
    fig.colorbar(im, ax=axs[1])
    axs[1].set_title(f'RMS from OPD below {opdIntegralEnd} after resin OPD subtraction')
    fig.suptitle(cellName)
    rmses[cellName] = rmsOpdIntData
    plt.pause(0.2)
plt.pause(0.5)

# plt.waitforbuttonpress(timeout=-1)
for k, v in rmses.items():
    if input(f"Save opdRms for {k}? (y/n): ").strip().lower() == 'y':
        sp.io.savemat(os.path.join(path, k, 'phantom_Rms.mat'), {'cubeRms': v.astype(np.float32)})  # save as a single
