from typing import List

from PyQt5 import QtCore
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QDialog, QWidget, QSlider, QLabel, QPushButton, QGridLayout
from cycler import cycler
from matplotlib.image import AxesImage
from shapely.geometry import Polygon as shapelyPolygon, LinearRing, MultiPolygon
from matplotlib.patches import Polygon

from pwspy.utility.fluorescence.segmentation import segmentAdaptive
from pwspy.utility.matplotlibWidgets.coreClasses import AxManager
from pwspy.utility.matplotlibWidgets._selectorWidgets import SelectorWidgetBase


class FullImPaintSelector(SelectorWidgetBase):
    def __init__(self, axMan: AxManager, im: AxesImage, onselect=None):
        super().__init__(axMan, im)
        self.onselect = onselect
        self.dlg = AdaptivePaintDialog(self, self.ax.figure.canvas)

    @staticmethod
    def getHelpText():
        return "Segment a full image using opencv thresholding techniques."

    def reset(self):
        self.removeArtists()

    def set_active(self, active: bool):
        super().set_active(active)
        if active:
            self.dlg.show()
            # Move dialog to the side
            rect = self.dlg.geometry()
            parentRect = self.ax.figure.canvas.geometry()
            # rect.moveTo(self.ax.figure.canvas.mapToGlobal(QPoint(parentRect.x() + parentRect.width() - rect.width(), parentRect.y())))
            rect.moveTo(self.ax.figure.canvas.mapToGlobal(QPoint(parentRect.x() - rect.width(), parentRect.y())))
            self.dlg.setGeometry(rect)
            self.dlg.paint()
        else:
            self.dlg.close()

    def drawRois(self, polys: List[shapelyPolygon]):
        if len(polys) > 0:
            alpha = 0.3
            colorCycler = cycler(color=[(1, 0, 0, alpha), (0, 1, 0, alpha), (0, 0, 1, alpha), (1, 1, 0, alpha), (1, 0, 1, alpha)])
            for poly, color in zip(polys, colorCycler()):
                p = Polygon(poly.exterior.coords, color=color['color'], animated=True)
                self.addArtist(p)
                self.axMan.update()

    def _press(self, event):
        if event.button == 1:  # Left Click
            coord = (event.xdata, event.ydata)
            for artist in self.artists:
                assert isinstance(artist, Polygon)
                if artist.get_path().contains_point(coord):
                    l = shapelyPolygon(LinearRing(artist.xy))
                    l = l.simplify(l.length / 2e2, preserve_topology=False)
                    if isinstance(l, MultiPolygon):  # There is a chance for this to convert a Polygon to a Multipolygon.
                        l = max(l, key=lambda a: a.area)  # To fix this we extract the largest polygon from the multipolygon
                    handles = l.exterior.coords
                    self.onselect(artist.xy, handles)
                    break


class AdaptivePaintDialog(QDialog):
    def __init__(self, parentSelector: FullImPaintSelector, parent: QWidget):
        super().__init__(parent=parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowTitleHint | QtCore.Qt.CustomizeWindowHint) #Get rid of the close button. this is handled by the selector widget active status
        self.parentSelector = parentSelector
        self.setWindowTitle("Adapter Painter")

        self.stale = True #This tells us whether we can load regions from the cache or need to recalculate
        self.cachedRegions = None
        self.cachedImage = None

        self._paintDebounce = QtCore.QTimer()  # This timer prevents the selectionChanged signal from firing too rapidly.
        self._paintDebounce.setInterval(200)
        self._paintDebounce.setSingleShot(True)
        self._paintDebounce.timeout.connect(self.paint)

        self.adptRangeSlider = QSlider(QtCore.Qt.Horizontal, self)
        maxImSize = max(parentSelector.image.get_array().shape)
        self.adptRangeSlider.setMaximum(maxImSize//2*2+1) #This must be an odd value or else its possible to set the slider to an even value. Opencv doesn't like that.
        self.adptRangeSlider.setMinimum(3)
        self.adptRangeSlider.setSingleStep(2)
        #TODO recommend value based on expected pixel size of a nucleus. need to access metadata.
        self.adptRangeSlider.setValue(551)
        self.adpRangeDisp = QLabel(str(self.adptRangeSlider.value()), self)
        def adptRangeChanged(val):
            self.stale = True
            self.adpRangeDisp.setText(str(val))
            if self.adptRangeSlider.value() % 2 == 0:
                self.adptRangeSlider.setValue(self.adptRangeSlider.value()//2*2+1)#This shouldn't ever happen. but it sometimes does anyway. make sure that adptRangeSlider is an odd number
            self._paintDebounce.start()
        self.adptRangeSlider.valueChanged.connect(adptRangeChanged)

        self.subSlider = QSlider(QtCore.Qt.Horizontal, self)
        self.subSlider.setMinimum(-50)
        self.subSlider.setMaximum(50)
        self.subSlider.setValue(-10)
        self.subDisp = QLabel(str(self.subSlider.value()), self)
        def subRangeChanged(val):
            self.stale = True
            self.subDisp.setText(str(val))
            self._paintDebounce.start()
        self.subSlider.valueChanged.connect(subRangeChanged)

        self.simplificationSlider = QSlider(QtCore.Qt.Horizontal, self)
        self.simplificationSlider.setMinimum(0)
        self.simplificationSlider.setMaximum(20)
        self.simplificationSlider.setValue(5)
        self.simDisp = QLabel(str(self.simplificationSlider.value()), self)
        def simpChanged(val):
            self.stale = True
            self.simDisp.setText(str(val))
            self._paintDebounce.start()
        self.simplificationSlider.valueChanged.connect(simpChanged)

        self.refreshButton = QPushButton("Refresh", self)
        self.refreshButton.released.connect(self.paint)

        l = QGridLayout()
        l.addWidget(QLabel("Adaptive Range (px)", self), 0, 0)
        l.addWidget(self.adptRangeSlider, 0, 1)
        l.addWidget(self.adpRangeDisp, 0, 2)
        l.addWidget(QLabel("Threshold Offset", self), 1, 0)
        l.addWidget(self.subSlider, 1, 1)
        l.addWidget(self.subDisp, 1, 2)
        l.addWidget(QLabel("Simplification", self), 2, 0)
        l.addWidget(self.simplificationSlider, 2, 1)
        l.addWidget(self.simDisp, 2, 2)
        l.addWidget(self.refreshButton, 3, 0)
        self.setLayout(l)

    def show(self):
        super().show()

    def paint(self):
        """Refresh the recommended regions. If stale is false then just repaint the cached regions without recalculating."""
        if self.parentSelector.image.get_array() is not self.cachedImage: #The image has been changed.
            self.cachedImage = self.parentSelector.image.get_array()
            self.stale = True
        if self.stale:
            try:
                polys = segmentAdaptive(self.parentSelector.image.get_array(), adaptiveRange=self.adptRangeSlider.value(), subtract=self.subSlider.value(), polySimplification=self.simplificationSlider.value())
                self.cachedRegions = polys
                self.stale = False
            except Exception as e:
                print("Warning: adaptive segmentation failed with error: ", e)
                return
        else:
            polys = self.cachedRegions
        self.parentSelector.reset()
        self.parentSelector.drawRois(polys)