# -*- coding: utf-8 -*-
"""
Created on Thu Oct 11 11:31:48 2018

@author: backman05
"""
from pwspython import ImCube
import matplotlib.pyplot as plt
import numpy as np
import psutil
import multiprocessing as mp
import threading as th
import typing
import os
from time import time
import sys
from threading import Timer

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


def plot3d(X):
    class perpetualTimer():
       def __init__(self,t,parent):
          self.t=t
          self.hFunction = parent.increment
          self.thread = Timer(self.t,self.handle_function)
          self.running = False
       def handle_function(self):
          self.hFunction()
          self.thread = Timer(self.t,self.handle_function)
          self.thread.start()
       def start(self):
          self.thread.start()
          self.running=True
       def cancel(self):
          self.thread.cancel()
          self.running=False


    class IndexTracker(object):
        def __init__(self, ax, X):
            self.ax = ax
            ax.set_title('use scroll wheel to navigate images')
            self.X = X
            rows, cols, self.slices = X.shape
            self.ind = self.slices//2
            self.max = np.percentile(self.X,99.9)
            self.min = np.percentile(self.X,0.1)
            self.im = ax.imshow(self.X[:, :, self.ind])
            self.im.set_clim(self.min,self.max)
            self.cbar = plt.colorbar(self.im, ax=ax)
            self.auto=perpetualTimer(0.2,self)
            self.update()  
        def onscroll(self, event):
            if ((event.button == 'up') or (event.button=='down')):
                self.ind = (self.ind + int(event.step)) % self.slices
            self.update()    
        #todo: add autoscrolldef press(event):
        def press(self,event):
            if event.key == 'a':
                if self.auto.running: self.auto.cancel() 
                else: self.auto.start()

        def increment(self):
            self.ind +=1
            if self.ind >= self.X.shape[2]: self.ind -= self.X.shape[2]
            self.update()
            
        def update(self):
            self.im.set_data(self.X[:, :, self.ind])
#            self.im.set_clim(self.X.min(),self.X.max())
            ax.set_ylabel('slice %s' % self.ind)
            self.im.axes.figure.canvas.draw()
    try:
        fig, ax = plt.subplots(1, 1)   
        tracker = IndexTracker(ax, X)
        
        fig.canvas.mpl_connect('key_press_event', tracker.press)
        fig.canvas.mpl_connect('scroll_event', tracker.onscroll)
        while plt.fignum_exists(fig.number):
            fig.canvas.flush_events()
    finally:
        tracker.auto.cancel()
        
