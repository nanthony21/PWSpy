from typing import List, Tuple, Optional

import numpy as np
from PyQt5 import QtCore
from PyQt5.QtWidgets import QWidget, QGridLayout, QButtonGroup, QPushButton
from matplotlib import patches

from pwspy.analysis.analysisResults import AnalysisResultsLoader
from pwspy.apps.PWSAnalysisApp.dockWidgets.PlottingDock.bigPlot import BigPlot
from pwspy.imCube import ICMetaData
from pwspy.imCube.otherClasses import Roi
from pwspy.utility.matplotlibwidg import AdjustableSelector, MyLasso, MyEllipse


class RoiDrawer(QWidget):
    def __init__(self, metadatas: List[Tuple[ICMetaData, Optional[AnalysisResultsLoader]]], parent=None, initialField='imbd'):
        QWidget.__init__(self, parent=parent, flags=QtCore.Qt.Window)
        self.setWindowTitle("Roi Drawer 3000")
        self.metadatas = metadatas
        layout = QGridLayout()
        self.mdIndex = 0
        self.plotWidg = BigPlot(metadatas[self.mdIndex][0], metadatas[self.mdIndex][0].getImBd(), 'title')
        self.buttonGroup = QButtonGroup(self)
        self.noneButton = QPushButton("None")
        self.lassoButton = QPushButton("Lasso")
        self.ellipseButton = QPushButton("Ellipse")
        self.lastButton_ = None
        self.buttonGroup.addButton(self.noneButton)
        self.buttonGroup.addButton(self.lassoButton)
        self.buttonGroup.addButton(self.ellipseButton)
        self.buttonGroup.buttonReleased.connect(self.handleButtons)
        [i.setCheckable(True) for i in self.buttonGroup.buttons()]
        self.noneButton.setChecked(True)
        self.adjustButton = QPushButton("Adj")
        self.adjustButton.setCheckable(True)
        self.adjustButton.toggled.connect(self.handleAdjustButton)
        self.previousButton = QPushButton('←') #TODO add functionality
        self.nextButton = QPushButton('→')
        self.previousButton.released.connect(self.showPreviousCell)
        self.nextButton.released.connect(self.showNextCell)

        layout.addWidget(self.noneButton, 0, 0, 1, 1)
        layout.addWidget(self.lassoButton, 0, 1, 1, 1)
        layout.addWidget(self.ellipseButton, 0, 2, 1, 1)
        layout.addWidget(self.adjustButton, 0, 3, 1, 1)
        layout.addWidget(self.previousButton, 0, 4, 1, 1)
        layout.addWidget(self.nextButton, 0, 5, 1, 1)
        layout.addWidget(self.plotWidg, 1, 0, 8, 8)
        self.setLayout(layout)
        self.selector: AdjustableSelector = AdjustableSelector(self.plotWidg.ax, MyLasso, onfinished=self.finalizeRoi)
        self.show()

    def finalizeRoi(self, verts: np.ndarray):
        poly = patches.Polygon(verts, facecolor=(1, 0, 0, 0.4))
        # path = poly.get_path()
        shape = self.plotWidg.data.shape
        # Y, X = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]))
        # coords = list(zip(Y.flatten(), X.flatten()))
        # matches = path.contains_points(coords)
        # mask = matches.reshape(shape)
        self.plotWidg.ax.add_patch(poly) #TODO tie all this in the BigPlot addRoi method. change how rois are saved. Disable onhover when roi drawing is active.
        r = Roi(self.plotWidg.roiFilter.currentText(), 1, data=np.array(verts), dataAreVerts=True, dataShape=shape)#TODO placeholder
        r.toHDFOutline(self.metadatas[self.mdIndex][0].filePath)


    def handleButtons(self, button):
        if button != self.lastButton_:
            if button is self.lassoButton:
                self.selector.setSelector(MyLasso)
                self.selector.setActive(True)
                self.plotWidg.enableHoverAnnotation(False)
                self.adjustButton.setEnabled(True)
            elif button is self.ellipseButton:
                self.selector.setSelector(MyEllipse)
                self.selector.setActive(True)
                self.plotWidg.enableHoverAnnotation(False)
                self.adjustButton.setEnabled(True)
            elif button is self.noneButton:
                self.selector.setActive(False)
                self.plotWidg.enableHoverAnnotation(True)
                self.adjustButton.setEnabled(False)
            self.lastButton_ = button

    def handleAdjustButton(self, checkstate: bool):
        if self.selector is not None:
            self.selector.adjustable = checkstate

    def showNextCell(self):
        self.mdIndex += 1
        if self.mdIndex >= len(self.metadatas):
            self.mdIndex = 0
        self._updateDisplayedCell()

    def showPreviousCell(self):
        self.mdIndex -= 1
        if self.mdIndex < 0:
            self.mdIndex = len(self.metadatas) - 1
        self._updateDisplayedCell()

    def _updateDisplayedCell(self):
        md = self.metadatas[self.mdIndex][0]
        self.plotWidg.setMetadata(md)
        self.plotWidg.setImageData(md.getImBd())