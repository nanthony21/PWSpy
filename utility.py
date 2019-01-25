# -*- coding: utf-8 -*-
"""
Created on Thu Oct 11 11:31:48 2018

@author: backman05
"""
from pwspython import ImCube, reflectanceHelper
from glob import glob
import matplotlib.pyplot as plt
import numpy as np
import psutil
import multiprocessing as mp
import threading as th
import typing
import os
from time import time
import pandas as pd
import itertools
from scipy.optimize import curve_fit

'''Local Functions'''
def _loadIms(q, fileDict, specifierNames):
        def a(arg, specifiers:typing.List[str] = []):
            if isinstance(arg,dict):
                for k,v in arg.items():
                    a(v,specifiers + [k])
            elif isinstance(arg,list):
                for file in arg:
                    fileSpecifiers = specifiers
                    _ =ImCube.loadAny(file)
                    if specifierNames is None:
                        _.specifiers = fileSpecifiers
                    else:
                        for i,name in enumerate(specifierNames):
                            setattr(_,name,fileSpecifiers[i])
                    _.filename = os.path.split(file)[1]
                    _.exposure = _.metadata['exposure']
                    q.put(_)
                    perc = psutil.virtual_memory().percent
                    print(file)
                    print("Memory Usage: ", perc,'%')
                    if perc >= 95:
                        del cubes
                        print('quitting')
                        quit()  
            else:
                raise TypeError(f'Filedict must only contain Dict and List, not an item of type: {type(arg)}')
        a(fileDict)

def _countIms(fileDict):
    def a(arg, numIms):
        if isinstance(arg,dict):
            for k,v in arg.items():
                numIms = a(v,numIms)
        elif isinstance(arg,list):
            numIms += len(arg)
            
        else:
            raise TypeError(f'Filedict must only contain Dict and List, not an item of type: {type(arg)}')
        return numIms
    return a(fileDict, 0)

def _interpolateNans(arr):
    def interp1(arr1):
        nans = np.isnan(arr1)
        f = lambda z: z.nonzero()[0]
        arr1[nans] = np.interp(f(nans), f(~nans), arr1[~nans])
        return arr1
    arr = np.apply_along_axis(interp1, 2, arr)
    return arr

'''User Functions'''
def loadAndProcess(fileDict:dict, processorFunc = None, specifierNames:list = None, parallel = False, procArgs = []) -> typing.List[ImCube]:
    #Error checking
    if not specifierNames is None:
        recursionDepth = 0
        fileStructure = fileDict
        while not isinstance(fileStructure, list):
            fileStructure = fileStructure[list(fileStructure.keys())[0]]
            recursionDepth += 1
        if recursionDepth != len(specifierNames):
            raise ValueError("The length of specifier names does not match the number of layers of folders in the fileDict")
    sTime = time()
    numIms = _countIms(fileDict)
    m = mp.Manager()
    q = m.Queue()
    thread = th.Thread(target = _loadIms, args=[q, fileDict, specifierNames])
    thread.start()

    if processorFunc is not None:
        # Start processing
        if parallel:
            po = mp.Pool(processes = psutil.cpu_count(logical=False)-1)
            cubes = po.starmap(processorFunc, [[q,*procArgs]]*numIms)
        else:
            cubes = [processorFunc(q,*procArgs) for i in range(numIms)]
    else:
        cubes = [q.get() for i in range(numIms)]
    thread.join()
    print(f"Loading took {time()-sTime} seconds")
    return cubes

def plotExtraReflection(cubes:list, selectMaskUsingSetting:str = None, plotReflectionImages:bool = False) -> (pd.DataFrame, pd.DataFrame):
    '''Expects a list of ImCubes which each has a `material` property matching one of the materials in the `ReflectanceHelper` module and a
    `setting` property labeling how the microscope was set up for this image.
    '''
    
    #Error checking
    assert isinstance(cubes[0], ImCube)
    assert hasattr(cubes[0],'material')
    assert hasattr(cubes[0],'setting')
    
    if selectMaskUsingSetting is None:        
        mask = cubes
    else:
        mask = [i for i in cubes if (i.setting == selectMaskUsingSetting)]
    print("Select an ROI")
    mask = mask[0].selectLassoROI() #Select an ROI to analyze
    
    # load theory reflectance
    theoryR = {}    #Theoretical reflectances
    materials = set([i.material for i in cubes])
    for material in materials: #For each unique material in the `cubes` list
        theoryR[material] = reflectanceHelper.getReflectance(material,'glass', index=cubes[0].wavelengths)
  
    # plot
    factors = {}
    reflections = {}
    fig, ax = plt.subplots() #For extra reflections
    fig.suptitle("Extra Reflection")
    ax.set_ylabel("%")
    ax.set_xlabel("nm")
    matCombos = list(itertools.combinations(materials, 2))  #All the combinations of materials that can be compared
    for i, (m1,m2) in enumerate(matCombos): #Make sure to arrange materials so that our reflectance ratio is greater than 1
        if (reflectanceHelper.getReflectance(m1,'glass')/reflectanceHelper.getReflectance(m2,'glass')).mean() < 1:
            matCombos[i] = (m2,m1)
    fig2, ratioAxes = plt.subplots(nrows = len(matCombos)) # for correction factor
    fig3, scatterAx = plt.subplots()    #A scatter plot of the theoretical vs observed reflectance ratio.
    scatterAx.set_ylabel("Theoretical Ratio")
    scatterAx.set_xlabel("Observed Ratio")
    fig4, scatterAx2 = plt.subplots()    #A scatter plot of the theoretical vs observed reflectance ratio.
    scatterAx2.set_ylabel("R_S + R_Extra / R_Ref")
    scatterAx2.set_xlabel("Observed Ratio")
#    scatterAx.set_xscale('log')
#    scatterAx.set_yscale('log')

    if not isinstance(ratioAxes, np.ndarray): ratioAxes = np.array(ratioAxes).reshape(1) #If there is only one axis we still want it to be a list for the rest of the code
    ratioAxes = dict(zip(matCombos,ratioAxes))
    for combo in matCombos:
        ratioAxes[combo].set_title(f'{combo[0]}/{combo[1]} reflection ratio')
        ratioAxes[combo].plot(theoryR[combo[0]]/theoryR[combo[1]], label='Theory')

    settings = set([i.setting for i in cubes]) #Unique setting values
    Rextras = {i:[] for i in matCombos}
    for sett in settings:
        scatterPoints = ([],[])
        scatterPoints2 = ([],[])
        for matCombo in matCombos:
            matCubes = {material:[cube for cube  in cubes if ((cube.material==material) and (cube.setting==sett))] for material in matCombo} #The imcubes relevant to this loop.
            allCombos = []
            for combo in itertools.product(*matCubes.values()):
                allCombos.append(dict(zip(matCubes.keys(), combo)))
            refRatios=[]
            subbedRefRatios = []
            for combo in allCombos:
                mat1,mat2 = combo.keys()
                Rextras[matCombo].append(((theoryR[mat1] * combo[mat2].getMeanSpectra(mask)[0]) - (theoryR[mat2] * combo[mat1].getMeanSpectra(mask)[0])) / (combo[mat1].getMeanSpectra(mask)[0] - combo[mat2].getMeanSpectra(mask)[0]))
                I0 = combo[mat2].getMeanSpectra(mask)[0] / (theoryR[mat2] + Rextras[matCombo][-1])
                Iextra = Rextras[matCombo][-1] * I0
                ax.plot(combo[mat1].wavelengths, Rextras[matCombo][-1], label = f'{sett} {mat1}:{int(combo[mat1].exposure)}ms {mat2}:{int(combo[mat2].exposure)}ms')
                refRatios.append(combo[mat1].getMeanSpectra(mask)[0]/combo[mat2].getMeanSpectra(mask)[0])
                subbedRefRatios.append((combo[mat1].getMeanSpectra(mask)[0] - Iextra) / (combo[mat2].getMeanSpectra(mask)[0] - Iextra))
                ratioAxes[matCombo].plot(combo[mat1].wavelengths, refRatios[-1], label=f'{sett} {mat1}:{int(combo[mat1].exposure)}ms {mat2}:{int(combo[mat2].exposure)}ms')
                
                if plotReflectionImages:
                    plt.figure()
                    plt.title(f"Reflectance %. {sett}, {mat1}:{int(combo[mat2].exposure)}ms, {mat2}:{int(combo[mat2].exposure)}ms")
                    _ = ((theoryR[mat1][np.newaxis,np.newaxis,:] * combo[mat2].data) - (theoryR[mat2][np.newaxis,np.newaxis,:] * combo[mat1].data)) / (combo[mat1].data - combo[mat2].data)
                    _[np.isinf(_)] = np.nan
                    if np.any(np.isnan(_)):
                        _ = _interpolateNans(_) #any division error resulting in an inf will really mess up our refIm. so we interpolate them out.
                    refIm = _.mean(axis=2)
                    plt.imshow(refIm,vmin=np.percentile(refIm,.5),vmax=np.percentile(refIm,99.5))
                    plt.colorbar()
            Rextras[matCombo] = np.array(Rextras[matCombo]).mean(axis=0) #Store the mean reflection spectrum of all instances of this material combo
            scatterPoints[1].append(theoryR[matCombo[0]].mean()/theoryR[matCombo[1]].mean())
            scatterPoints[0].append(np.array(refRatios).mean())
#            scatterPoints2[1].append((theoryR[matCombo[0]].mean() + Rextras[matCombo].mean()) / theoryR[matCombo[1]].mean())
            scatterPoints2[1].append(scatterPoints[1][-1])
            scatterPoints2[0].append(np.array(subbedRefRatios).mean())
            scatterAx.scatter(scatterPoints[0][-1], scatterPoints[1][-1], label=f'{matCombo[0]}/{matCombo[1]}')
            scatterAx2.scatter(scatterPoints2[0][-1], scatterPoints2[1][-1], label=f'{matCombo[0]}/{matCombo[1]}')
        print("{} correction factor".format(sett))
        Rextra = np.array([i for k,i in Rextras.items()]) #Store the mean reflection spectrum accross all material combos.
        factors[sett] = (Rextra.mean() + theoryR['water'].mean()) / theoryR['water'].mean()
        reflections[sett] = Rextra.mean(axis = 0)
        print(factors[sett])
    ax.legend()
    slope = np.linalg.lstsq(np.array(scatterPoints[0])[:,np.newaxis],scatterPoints[1])[0][0]
    slope2 = np.linalg.lstsq(np.array(scatterPoints2[0])[:,np.newaxis],scatterPoints2[1])[0][0]
    scatterAx.plot(np.linspace(min(scatterPoints[0]),max(scatterPoints[0])), factors[sett]*np.linspace(min(scatterPoints[0]),max(scatterPoints[0])))
    scatterAx.legend()
    scatterAx2.plot(np.linspace(min(scatterPoints2[0]),max(scatterPoints2[0])), slope2*np.linspace(min(scatterPoints2[0]),max(scatterPoints2[0])))
    scatterAx2.legend()
    print(f'Slope: {slope}')
    print(f'Slope2: {slope2}')
    [ratioAxes[combo].legend() for combo in matCombos]
    
    factors = pd.DataFrame(factors, index = [0])
    reflections = pd.DataFrame(reflections,index = cubes[0].wavelengths)
    return factors, reflections