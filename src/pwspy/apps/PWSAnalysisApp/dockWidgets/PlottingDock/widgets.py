import re
from os import path as osp

import numpy as np
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QWidget, QBoxLayout, QSpacerItem, QGridLayout, QButtonGroup, QPushButton, QMenu, QAction, \
    QSlider, QApplication, QLabel, QDialog, QVBoxLayout, QSpinBox, QDoubleSpinBox, QAbstractSpinBox, QComboBox, \
    QLineEdit
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.widgets import LassoSelector

from pwspy.analysis.analysisResults import AnalysisResultsLoader
from pwspy.apps.PWSAnalysisApp.sharedWidgets.rangeSlider import QRangeSlider
from pwspy.imCube import ImCube
from pwspy.imCube.ICMetaDataClass import ICMetaData
from pwspy.imCube.otherClasses import Roi
from pwspy.utility import PlotNd
from pwspy.utility.matplotlibwidg import MyLasso, AxManager, MyEllipse, mySelectorWidget, AdjustableSelector
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional


class AspectRatioWidget(QWidget):
    def __init__(self, aspect: float, parent: QWidget = None):
        super().__init__(parent)
        self._aspect = aspect

    def resizeEvent(self, event: QtGui.QResizeEvent):
        self._resize(event.size().width())

    def _resize(self, width):
        newHeight = width / self._aspect
        self.setMaximumHeight(newHeight)

    def setAspect(self, aspect: float):
        self._aspect = aspect
        self._resize(self.width())


class AnalysisPlotter:
    def __init__(self, metadata: ICMetaData, analysis: AnalysisResultsLoader = None):
        self.analysis = analysis
        self.metadata = metadata
        self.data = None
        self.analysisField = None

    def changeData(self, field):
        if field != self.analysisField:
            self.analysisField = field
            if field == 'imbd': #Load the imbd from the ICMetadata object
                self.data = self.metadata.getImBd()
            else:
                if self.analysis is None:
                    raise ValueError(f"Analysis Plotter for ImCube {self.metadata.filePath} does not have an analysis file.")
                self.data = getattr(self.analysis, field)
            assert len(self.data.shape) == 2


class LittlePlot(FigureCanvasQTAgg, AnalysisPlotter):
    def __init__(self, metadata: ICMetaData, analysis: AnalysisResultsLoader, title: str, initialField='imbd'):
        AnalysisPlotter.__init__(self, metadata, analysis)
        self.fig = Figure()
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.im = self.ax.imshow(np.zeros((100, 100)))
        self.title = f"{title} {initialField}"
        self.ax.set_title(self.title, fontsize=8)
        self.ax.yaxis.set_visible(False)
        self.ax.xaxis.set_visible(False)
        FigureCanvasQTAgg.__init__(self, self.fig)
        self.mpl_connect("button_release_event", self.mouseReleaseEvent)
        self.setMinimumWidth(20)
        self.changeData(initialField)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.plotnd = None

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            BigPlot(self.metadata, self.data, self.title, self)

    def changeData(self, field):
        AnalysisPlotter.changeData(self, field)
        t = self.title.split(' ')
        t[-1] = field
        self.title = ' '.join(t)
        self.ax.set_title(self.title, fontsize=8)
        self.im.set_data(self.data)
        self.im.set_clim((np.percentile(self.data, 0.1), np.percentile(self.data, 99.9)))
        self.draw_idle()

    def showContextMenu(self, point: QPoint):
        menu = QMenu("ContextMenu", self)
        if self.analysis is not None:
            anPlotAction = QAction("Plot3d Analyzed Reflectance", self)
            anPlotAction.triggered.connect(self.plotAn3d)
            menu.addAction(anPlotAction)
        rawPlotAction = QAction("Plot3d Raw Data", self)
        rawPlotAction.triggered.connect(self.plotRaw3d)
        menu.addAction(rawPlotAction)
        menu.exec(self.mapToGlobal(point))

    def plotAn3d(self):
        self.plotnd = PlotNd(self.analysis.reflectance.data)

    def plotRaw3d(self):
        self.plotnd = PlotNd(ImCube.fromMetadata(self.metadata).data)


class BigPlot(QWidget):
    class SaturationDialog(QDialog):
        def __init__(self, parent):
            super().__init__(parent=parent, flags=QtCore.Qt.FramelessWindowHint)
            self.setModal(True)
            l = QVBoxLayout()
            self.numBox = QDoubleSpinBox()
            self.numBox.setValue(0.1)
            self.numBox.setMinimum(0)
            self.numBox.setSingleStep(0.1)
            self.okButton = QPushButton("Ok")
            self.okButton.released.connect(self.accept)
            l.addWidget(QLabel("Saturation %"))
            l.addWidget(self.numBox)
            l.addWidget(self.okButton)
            self.setLayout(l)

        @property
        def value(self):
            return self.numBox.value()

    class RangeDialog(QDialog):
        def __init__(self, parent):
            super().__init__(parent=parent, flags = QtCore.Qt.FramelessWindowHint)
            self.setModal(True)
            l = QGridLayout()
            self.minBox = QDoubleSpinBox()

            self.maxBox = QDoubleSpinBox()
            self.okButton = QPushButton("Ok")
            self.okButton.released.connect(self.accept)
            l.addWidget(QLabel("Min"), 0, 0, 1, 1)
            l.addWidget(QLabel("Max"), 0, 1, 1, 1)
            l.addWidget(self.minBox, 1, 0, 1, 1)
            l.addWidget(self.maxBox, 1, 1, 1, 1)
            l.addWidget(self.okButton, 2, 1, 1, 1)
            self.setLayout(l)

        def show(self):
            for b in [self.minBox, self.maxBox]:
                b.setMaximum(self.parent().slider.max())
                b.setMinimum(self.parent().slider.min())
            self.minBox.setValue(self.parent().slider.start())
            self.maxBox.setValue(self.parent().slider.end())
            super().show()

        @property
        def minimum(self): return self.minBox.value()

        @property
        def maximum(self): return self.maxBox.value()

    def __init__(self, metadata: ICMetaData, data: np.ndarray, title: str, parent=None):
        QWidget.__init__(self, parent=parent, flags=QtCore.Qt.Window)
        self.setWindowTitle(title)
        layout = QGridLayout()
        self.data = data
        self.metadata = metadata
        self._rois = []
        self.fig = Figure()
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.get_yaxis().set_visible(False)
        self.ax.get_xaxis().set_visible(False)
        self.im = self.ax.imshow(data, cmap='gray')
        self.fig.colorbar(self.im, ax=self.ax)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.canvas.setFocus()
        self.fig.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)
        self.slider = QRangeSlider(self)
        self.slider.endValueChanged.connect(self.climImage)
        self.slider.startValueChanged.connect(self.climImage)
        self.autoDlg = BigPlot.SaturationDialog(self)
        self.autoDlg.accepted.connect(self.setSaturation)
        self.rangeDlg = BigPlot.RangeDialog(self)
        self.rangeDlg.accepted.connect(self.setRange)
        self.saturationButton = QPushButton("Auto")
        self.saturationButton.released.connect(self.autoDlg.show)
        self.manualRangeButton = QPushButton("Range")
        self.manualRangeButton.released.connect(self.rangeDlg.show)
        self.roiFilter = QComboBox(self)
        self.roiFilter.setEditable(True)
        # updateFilter
        self.roiFilter.addItem(' ')
        self.roiFilter.addItem('.*')
        roiNames = set(list(zip(*self.metadata.getRois()))[0])
        self.roiFilter.addItems(roiNames)
        self.roiFilter.currentIndexChanged.connect(self.showRois)

        self.cmapCombo = QComboBox(self)
        self.cmapCombo.addItems(['gray', 'jet', 'plasma', 'Reds'])
        self.cmapCombo.currentTextChanged.connect(self.changeCmap)

        layout.addWidget(self.canvas, 0, 0, 8, 8)
        layout.addWidget(QLabel("Color Range"), 9, 0, 1, 1)
        layout.addWidget(self.slider, 9, 1, 1, 4)
        layout.addWidget(self.saturationButton, 9, 6, 1, 1)
        layout.addWidget(self.manualRangeButton, 9, 7, 1, 1)
        layout.addWidget(NavigationToolbar(self.canvas, self), 10, 0, 1, 4)
        layout.addWidget(QLabel("Roi"), 10, 4, 1, 1)
        layout.addWidget(self.roiFilter, 10, 5, 1, 1)
        layout.addWidget(QLabel("Color Map"), 10, 6, 1, 1)
        layout.addWidget(self.cmapCombo, 10, 7, 1, 1)
        layout.setRowStretch(0, 1)  # This causes the plot to take up all the space that isn't needed by the other widgets.
        self.setLayout(layout)

        M = self.data.max()
        self.slider.setMax(M)
        m = self.data.min()
        self.slider.setMin(m)

        self.show()
        self.setSaturation()

        self.annot = self.ax.annotate("", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="w"),
                            arrowprops=dict(arrowstyle="->"))




        self.fig.canvas.mpl_connect("motion_notify_event", self.hover)


    def hover(self, event):
        def update_annot(roi, poly):
            self.annot.xy = poly.xy.mean(axis=0) # Set the location to the center of the polygon.
            text = f"{roi.name}, {roi.number}"
            self.annot.set_text(text)
            #            self.annot.get_bbox_patch().set_facecolor(cmap(norm(c[ind["ind"][0]])))
            self.annot.get_bbox_patch().set_alpha(0.4)
        vis = self.annot.get_visible()
        if event.inaxes == self.ax:
            for roi, overlay, poly in self._rois:
                contained, _ = poly.contains(event)
                if contained:
                    if not vis:
                        update_annot(roi, poly)
                        self.annot.set_visible(True)
                        self.fig.canvas.draw_idle()
                    return
            if vis: #If we got here then not hover actions were found.
                self.annot.set_visible(False)
                self.fig.canvas.draw_idle()

    def showRois(self):
        pattern = self.roiFilter.currentText()
        self.clearRois()
        for name, num, fformat in self.metadata.getRois():
            if re.match(pattern, name):
                self.addRoi(self.metadata.loadRoi(name, num, fformat))
        self.canvas.draw_idle()

    def clearRois(self):
        for roi, overlay, poly in self._rois:
            overlay.remove()
            poly.remove()
        self._rois = []

    def addRoi(self, roi: Roi):
        overlay = roi.getImage(self.ax) # an image showing the exact shape of the ROI
        poly = roi.getBoundingPolygon() # A polygon used for mouse event handling
        poly.set_visible(False)#poly.set_facecolor((0,0,0,0)) # Make polygon invisible
        self.ax.add_patch(poly)
        self._rois.append((roi, overlay, poly))


    def setSaturation(self):
        percentage = self.autoDlg.value
        m = np.percentile(self.data, percentage)
        M = np.percentile(self.data, 100 - percentage)
        self.slider.setStart(m)
        self.slider.setEnd(M)

    def setRange(self):
        self.slider.setStart(self.rangeDlg.minimum)
        self.slider.setEnd(self.rangeDlg.maximum)

    def climImage(self):
        self.im.set_clim((self.slider.start(), self.slider.end()))
        self.canvas.draw_idle()

    def changeCmap(self, map: str):
        self.im.set_cmap(map)
        self.canvas.draw_idle()

#TODO all these classes deal with ICMetadata with an optional Analysis. make a class to conveniently package them.
class RoiDrawer(QWidget):
    def __init__(self, metadatas: List[Tuple[ICMetaData, Optional[AnalysisResultsLoader]]], parent=None, initialField='imbd'):
        QWidget.__init__(self, parent=parent, flags=QtCore.Qt.Window)
        self.setWindowTitle("What?!")
        self.metadatas = metadatas
        layout = QGridLayout()
        self.plotWidg = BigPlot(metadatas[0][0], np.random.rand(100, 100), 'title')
        self.buttonGroup = QButtonGroup(self)
        self.lassoButton = QPushButton("L")
        self.ellipseButton = QPushButton("O")
        self.lastButton_ = None
        self.buttonGroup.addButton(self.lassoButton, 1)
        self.buttonGroup.addButton(self.ellipseButton)
        self.buttonGroup.buttonReleased.connect(self.handleButtons)
        [i.setCheckable(True) for i in self.buttonGroup.buttons()]
        self.adjustButton = QPushButton("Adj")
        self.adjustButton.setCheckable(True)
        self.adjustButton.toggled.connect(self.handleAdjustButton)
        self.previousButton = QPushButton('←') #TODO add functionality
        self.nextButton = QPushButton('→')

        layout.addWidget(self.lassoButton, 0, 0, 1, 1)
        layout.addWidget(self.ellipseButton, 0, 1, 1, 1)
        layout.addWidget(self.adjustButton, 0, 2, 1, 1)
        layout.addWidget(self.previousButton, 0, 4, 1, 1)
        layout.addWidget(self.nextButton, 0, 5, 1, 1)
        layout.addWidget(self.plotWidg, 1, 0, 8, 8)
        self.setLayout(layout)
        self.selector: AdjustableSelector = AdjustableSelector(self.plotWidg.ax, MyLasso) #TODO actually get roi object and save it.

        self.show()

    def handleButtons(self, button):
        if button != self.lastButton_:
            if button is self.lassoButton:
                self.selector.setSelector(MyLasso)
            elif button is self.ellipseButton:
                self.selector.setSelector(MyEllipse)
            self.lastButton_ = button

    def handleAdjustButton(self, checkstate: bool):
        if self.selector is not None:
            self.selector.adjustable = checkstate


if __name__ == '__main__':
    app = QApplication([])
    b = BigPlot(np.random.random((1024, 1024)), 'Title')
    app.exec()