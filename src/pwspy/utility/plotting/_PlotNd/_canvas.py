import typing
from typing import Tuple

import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QResizeEvent
from PyQt5.QtWidgets import QWidget
from matplotlib import pyplot as plt, gridspec
from matplotlib.backend_bases import ResizeEvent
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from ._plots import ImPlot, SidePlot, CBar

#class SpecSel

def ifactive(func):
    def newfunc(self, event):
        if self.spectraViewActive:
            return func(self, event)
    return newfunc


class PlotNdCanvas(FigureCanvasQTAgg):
    def __init__(self, data: np.ndarray, names: Tuple[str, ...] = ('y', 'x', 'lambda'),
                 initialCoords: Tuple[int, ...] = None, extraDimIndices: typing.List = None):
        assert len(names) == len(data.shape)
        fig = plt.Figure(figsize=(6, 6), tight_layout=True)
        self.fig = fig
        super().__init__(self.fig)

        self.childPlots = []
        self.max = self.min = None  # The minimum and maximum for the color scaling

        if extraDimIndices is None:
            self._indexes = tuple(range(s) for s in data.shape)
        else:
            assert len(extraDimIndices) == len(data.shape)-2
            self._indexes = tuple([range(data.shape[0]), range(data.shape[1])] + extraDimIndices)

        extraDims = len(data.shape[2:])  # the first two axes are the image dimensions. Any axes after that are extra dimensions that can be scanned through

        gs = gridspec.GridSpec(3, 2 + extraDims, hspace=0,
                               width_ratios=[.2 / (extraDims)] * extraDims + [1, .2],
                               height_ratios=[.1, 1, .2], wspace=0)

        ax: plt.Axes = fig.add_subplot(gs[1, extraDims])
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        self.image = ImPlot(ax, self._indexes[0], self._indexes[1], (0, 1))

        ax: plt.Axes = fig.add_subplot(gs[1, extraDims + 1], sharey=self.image.ax)
        ax.yaxis.set_ticks_position('right')
        ax.get_xaxis().set_visible(False)
        self.spY = SidePlot(ax, self._indexes[0], True, 0)

        ax: plt.Axes = fig.add_subplot(gs[2, extraDims], sharex=self.image.ax)
        ax.xaxis.set_label_coords(.5, .95)
        ax.get_yaxis().set_visible(False)
        self.spX = SidePlot(ax, self._indexes[1], False, 1)

        ax: plt.Axes = fig.add_subplot(gs[0, extraDims])
        self.cbar = CBar(ax, self.image.im)

        extra = [fig.add_subplot(gs[1, i]) for i in range(extraDims)]
        [extra[i].set_ylim(0, data.shape[2 + i] - 1) for i in range(extraDims)]
        [extra[i].get_xaxis().set_visible(False) for i in range(extraDims)]
        self.extra = []
        for i, ax in enumerate(extra):
            if extraDimIndices is None:
                self.extra.append(SidePlot(ax, range(data.shape[i + 2]), True, 2 + i))
            else:
                self.extra.append(SidePlot(ax, self._indexes[2+i], True, 2 + i))

        self.artistManagers = [self.spX, self.spY, self.image] + self.extra
        self.names = None
        self.setAxesNames(names)

        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setFocus()

        self._data = data
        self.resetColor()
        self.coords = tuple(i // 2 for i in data.shape) if initialCoords is None else initialCoords

        self.spectraViewActive = True
        self.mpl_connect('button_press_event', self.onclick)
        self.mpl_connect('motion_notify_event', self.ondrag)
        self.mpl_connect('scroll_event', self.onscroll)
        self.mpl_connect('draw_event', self._updateBackground)
        self.updatePlots(blit=False)

    def setSpectraViewActive(self, active: bool):
        self.spectraViewActive = active
        if not active:
            self.draw() #This will clear the spectraviewer related crosshairs and plots.

    def _updateBackground(self, event):
        for artistManager in self.artistManagers:
            artistManager.updateBackground(event)
        self.cbar.draw()

    def updatePlots(self, blit=True):
        for plot in self.artistManagers:
            slic = tuple(c if i not in plot.dimensions else slice(None) for i, c in enumerate(self.coords))
            newData = self._data[slic]
            plot.setData(newData)
            newCoords = tuple(c for i, c in enumerate(self.coords) if i in plot.dimensions)
            plot.setMarker(newCoords)
        if blit:
            self.performBlit()
        else:
            self.draw()

    def performBlit(self):
        """Re-render the axes."""
        for artistManager in self.artistManagers: # The fact that spX is first here makes it not render on click. sometimes not sure why.
            if artistManager.background is not None:
               self.restore_region(artistManager.background)
            artistManager.drawArtists() #Draw the artists
            self.blit(artistManager.ax.bbox)

    def updateLimits(self, Max, Min):
        self.min = Min
        self.max = Max
        self.image.setRange(self.min, self.max)
        self.spY.setRange(self.min, self.max)
        self.spX.setRange(self.min, self.max)
        for sp in self.extra:
            sp.setRange(self.min, self.max)
        self.cbar.draw()
        self.draw_idle()
        try:
            self.updatePlots()  # This will fail when this is run in the constructor.
        except:
            pass

    def resetColor(self):
        Max = np.percentile(self._data[np.logical_not(np.isnan(self._data))], 99.99)
        Min = np.percentile(self._data[np.logical_not(np.isnan(self._data))], 0.01)
        self.updateLimits(Max, Min)

    def setAxesNames(self, names: typing.Iterable[str]):
        self.names = tuple(names)
        self.spY.ax.set_title(self.names[0])
        self.spX.ax.set_xlabel(self.names[1])
        for i in range(len(self.extra)):
            self.extra[i].ax.set_title(self.names[2+i])

    def rollAxes(self):
        self.setAxesNames([self.names[-1]] + list(self.names[:-1]))
        self._indexes = (self._indexes[-1],) + tuple(self._indexes[:-1])
        self.coords = (self.coords[-1],) + tuple(self.coords[:-1])
        for plot in self.artistManagers:
            if isinstance(plot, SidePlot):
                [plot.setIndex(ind) for i, ind in enumerate(self._indexes) if i in plot.dimensions]
            elif isinstance(plot, ImPlot):
                plot.setIndices(self._indexes[plot.dimensions[0]], self._indexes[plot.dimensions[1]])
        axes = list(range(len(self._data.shape)))
        _ = np.transpose(self._data, [axes[-1]] + axes[:-1])
        self.data = _
        self.draw()

    @property
    def data(self) -> np.ndarray:
        return self._data

    @data.setter
    def data(self, d: np.ndarray):
        self._data = d
        self.updatePlots()

    @ifactive
    def onscroll(self, event):
        if (event.button == 'up') or (event.button == 'down'):
            step = int(4 * event.step)
            try:
                plot = [plot for plot in self.artistManagers if plot.ax == event.inaxes][0]
            except IndexError: # No plot is being moused over
                return
            self.coords = tuple((c + step) % self._data.shape[plot.dimensions[0]] if i in plot.dimensions else c for i, c in enumerate(self.coords))
            self.updatePlots()

    @ifactive
    def onclick(self, event):
        if event.inaxes is None:
            return
        if event.dblclick:
            am = [artistManager for artistManager in self.artistManagers if artistManager.ax == event.inaxes][0]
            if isinstance(am, SidePlot):
                fig, ax = plt.subplots()
                ax.plot(am.getIndex(), am.getData())
                self.childPlots.append(fig)
                fig.show()
        ax = event.inaxes
        x, y = event.xdata, event.ydata
        button = event.button
        self.processMouse(ax, x, y, button, colorbar=True)

    def processMouse(self, ax, x, y, button, colorbar):
        if ax == self.image.ax:
            self.coords = (self.image.verticalValueToCoord(y), self.image.horizontalValueToCoord(x)) + self.coords[2:]
        elif ax == self.spY.ax:
            self.coords = (self.spY.valueToCoord(y),) + self.coords[1:]
        elif ax == self.spX.ax:
            self.coords = (self.coords[0], self.spX.valueToCoord(x)) + self.coords[2:]
        elif ax in [sp.ax for sp in self.extra]:
            idx = [sp.ax for sp in self.extra].index(ax)
            sp = [sp for sp in self.extra if sp.ax is ax][0]
            ycoord = sp.valueToCoord(y)
            self.coords = self.coords[:2 + idx] + (int(ycoord),) + self.coords[3 + idx:]
        self.updatePlots()

    @ifactive
    def ondrag(self, event):
        if event.inaxes is None:
            return
        if event.button != 1:
            return
        ax = event.inaxes
        x, y = event.xdata, event.ydata
        button = event.button
        self.processMouse(ax, x, y, button, colorbar=False)