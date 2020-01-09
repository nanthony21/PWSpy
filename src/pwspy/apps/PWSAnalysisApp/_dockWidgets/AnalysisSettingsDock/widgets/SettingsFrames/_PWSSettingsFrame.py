from __future__ import annotations
import os
from glob import glob
from typing import Optional
import typing

from pwspy.apps.PWSAnalysisApp._dockWidgets.AnalysisSettingsDock.widgets.SettingsFrames._AbstractSettingsFrame import AbstractSettingsFrame
from pwspy.apps.PWSAnalysisApp._dockWidgets.AnalysisSettingsDock.widgets.SettingsFrames._sharedWidgets import ExtraReflectanceSelector

if typing.TYPE_CHECKING:
    from pwspy.apps.sharedWidgets.extraReflectionManager.manager import ERManager

from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import QPalette, QValidator, QDoubleValidator
from PyQt5.QtWidgets import QScrollArea, QGridLayout, QLineEdit, QLabel, QGroupBox, QHBoxLayout, QWidget, QRadioButton, \
    QFrame, QSpinBox, QVBoxLayout, QComboBox, QDoubleSpinBox, QCheckBox, QSpacerItem, QSizePolicy, QLayout

from pwspy.dataTypes import CameraCorrection
from pwspy.analysis.pws import AnalysisSettings
from pwspy.apps.PWSAnalysisApp import applicationVars
from pwspy.apps.PWSAnalysisApp._sharedWidgets.collapsibleSection import CollapsibleSection


def humble(clas):
    """Returns a subclass of clas that will not allow scrolling unless it has been actively selected."""
    class HumbleDoubleSpinBox(clas):
        def __init__(self, *args):
            super(HumbleDoubleSpinBox, self).__init__(*args)
            self.setFocusPolicy(QtCore.Qt.StrongFocus)

        def focusInEvent(self, event):
            self.setFocusPolicy(QtCore.Qt.WheelFocus)
            super(HumbleDoubleSpinBox, self).focusInEvent(event)

        def focusOutEvent(self, event):
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            super(HumbleDoubleSpinBox, self).focusOutEvent(event)

        def wheelEvent(self, event):
            if self.hasFocus():
                return super(HumbleDoubleSpinBox, self).wheelEvent(event)
            else:
                event.ignore()
    return HumbleDoubleSpinBox


QHSpinBox = humble(QSpinBox)
QHDoubleSpinBox = humble(QDoubleSpinBox)
QHComboBox = humble(QComboBox)


class PWSSettingsFrame(AbstractSettingsFrame, QScrollArea):
    def __init__(self, erManager: ERManager):
        super().__init__()

        self._frame = VerticallyCompressedWidget(self)
        self._layout = QGridLayout()
        self._frame.setLayout(self._layout)
        self._frame.setFixedWidth(350)
        self.setMinimumWidth(self._frame.width()+5)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setWidget(self._frame)

        """Set up Frame"""
        """Presets"""
        row = 0
        self._analysisNameEdit = QLineEdit()
        self._layout.addWidget(QLabel("Analysis Name: "), row, 0, 1, 1)
        self._layout.addWidget(self._analysisNameEdit, row, 1, 1, 1)
        row += 1
        self.presets = QGroupBox("Presets")
        self.presets.setLayout(QHBoxLayout())
        self.presets.layout().setContentsMargins(0, 0, 0, 5)
        _2 = QWidget()
        _2.setLayout(QHBoxLayout())
        _2.layout().setContentsMargins(5, 0, 5, 0)
        for f in glob(os.path.join(applicationVars.analysisSettingsDirectory, '*_analysis.json')):
            name = os.path.split(f)[-1][:-14]
            b = QRadioButton(name)
            b.released.connect(
                lambda n=name: self.loadFromSettings(
                    AnalysisSettings.fromJson(applicationVars.analysisSettingsDirectory, n)))
            _2.layout().addWidget(b)
        _ = QScrollArea()
        _.setWidget(_2)
        _.setFrameShape(QFrame.NoFrame)
        _.setContentsMargins(0, 0, 0, 0)
        _.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        _.horizontalScrollBar().setStyleSheet("QScrollBar:horizontal { height: 10px; }")
        self.presets.setFixedHeight(45)
        self.presets.layout().addWidget(_)
        self._layout.addWidget(self.presets, row, 0, 1, 4)
        row += 1

        '''Hardwarecorrections'''
        layout = QGridLayout()
        dcLabel = QLabel('Dark Counts')
        self.darkCountBox = QHSpinBox()
        self.darkCountBox.setToolTip("The counts/pixel reported by the camera when it is not exposed to any light."
                                     " e.g if using 2x2 binning and you measure 400 counts, then the value to put here is 100.")
        dcLabel.setToolTip(self.darkCountBox.toolTip())
        self.darkCountBox.setRange(0, 10000)
        linLabel = QLabel("Linearity Correction")
        self.linearityEdit = QLineEdit()
        self.linearityEdit.setText("1")
        self.linearityEdit.setToolTip("A comma-separated polynomial to linearize the counts from the camera."
                                      "E.G an entry of A,B,C here will result in the data being transformed as newData = A * data + B * data^2 + C * data^3."
                                      "Leaving this as '1' will result in no transformation (usually CMOS cameras are already linear)")
        linLabel.setToolTip(self.linearityEdit.toolTip())
        self.linearityEdit.setValidator(CsvValidator())
        origPalette = self.linearityEdit.palette()
        palette = QPalette()
        palette.setColor(QPalette.Text, QtCore.Qt.red)
        self.linearityEdit.validator().stateChanged.connect(lambda state:
            self.linearityEdit.setPalette(palette) if state != QValidator.Acceptable else self.linearityEdit.setPalette(origPalette))

        _ = layout.addWidget
        _(dcLabel, 0, 0)
        _(self.darkCountBox, 0, 1)
        _(linLabel, 1, 0)
        _(self.linearityEdit, 1, 1)
        self.hardwareCorrections = CollapsibleSection('Automatic Correction', 200, self)
        self.hardwareCorrections.stateChanged.connect(self._updateSize)
        self.hardwareCorrections.setToolTip("The relationship between camera counts and light intensity is not always linear."
                                            "The correction parameters can usually be found automatically in the image metadata.")
        self.hardwareCorrections.setLayout(layout)
        self._layout.addWidget(self.hardwareCorrections, row, 0, 1, 4)
        row += 1

        '''Extra Reflection'''
        self.extraReflection = ExtraReflectanceSelector(self, erManager)
        self._layout.addWidget(self.extraReflection, row, 0, 1, 4)
        row += 1

        '''SignalPreparations'''
        self.signalPrep = QGroupBox("Signal Prep")
        self.signalPrep.setFixedSize(175, 75)
        self.signalPrep.setToolTip("In order to reduce the effects of measurement noise we filter out the high frequencies from our signal. We do this using a Buttersworth low-pass filter. Best to stick with the defaults on this one.")
        layout = QGridLayout()
        layout.setContentsMargins(5, 1, 5, 5)
        _ = layout.addWidget
        orderLabel = QLabel("Filter Order")
        self.filterOrder = QHSpinBox()
        self.filterOrder.setRange(0, 6)
        self.filterOrder.setToolTip("A lowpass filter is applied to the spectral signal to reduce noise. This determines the `order` of the digital filter.")
        orderLabel.setToolTip(self.filterOrder.toolTip())
        cutoffLabel = QLabel("Cutoff Freq.")
        self.filterCutoff = QHDoubleSpinBox()
        self.filterCutoff.setToolTip("The frequency in units of 1/wavelength for the filter cutoff.")
        cutoffLabel.setToolTip(self.filterCutoff.toolTip())
        _(orderLabel, 0, 0, 1, 1)
        _(self.filterOrder, 0, 1, 1, 1)
        _(cutoffLabel, 1, 0, 1, 1)
        _(self.filterCutoff, 1, 1, 1, 1)
        _(QLabel("nm<sup>-1</sup>"), 1, 2, 1, 1)
        self.signalPrep.setLayout(layout)
        self._layout.addWidget(self.signalPrep, row, 0, 1, 2)

        '''Cropping'''
        self.cropping = QGroupBox("Wavelength Cropping")
        self.cropping.setFixedSize(125, 75)
        self.cropping.setToolTip("In the past it was found that there was exceptionally high noise at the very beginning and end of an acquisition. For this reason we would exclude the first and last wavelengths of the image cube. While it is likely that the noise issue has now been fixed we still do this for consistency's sake.")
        layout = QGridLayout()
        layout.setContentsMargins(5, 1, 5, 5)
        _ = layout.addWidget
        self.wavelengthStart = QHSpinBox()
        self.wavelengthStop = QHSpinBox()
        self.wavelengthStart.setToolTip("Sometimes the beginning and end of the spectrum can have very high noise. For this reason we crop the data before analysis.")
        self.wavelengthStop.setToolTip("Sometimes the beginning and end of the spectrum can have very high noise. For this reason we crop the data before analysis.")
        self.wavelengthStart.setRange(300, 800)
        self.wavelengthStop.setRange(300, 800)
        _(QLabel("Start"), 0, 0)
        _(QLabel("Stop"), 0, 1)
        _(self.wavelengthStart, 1, 0)
        _(self.wavelengthStop, 1, 1)
        self.cropping.setLayout(layout)
        self._layout.addWidget(self.cropping, row, 2, 1, 2)
        row += 1

        '''Polynomial subtraction'''
        self.polySub = QGroupBox("Polynomial Subtraction")
        self.polySub.setFixedSize(150, 50)
        self.polySub.setToolTip("A polynomial is fit to each spectrum and then it is subtracted from the spectrum."
                                        "This is so that we remove effects of absorbtion and our final signal is only due to interference")
        layout = QGridLayout()
        layout.setContentsMargins(5, 1, 5, 5)
        _ = layout.addWidget
        self.polynomialOrder = QHSpinBox()
        _(QLabel("Order"), 0, 0, 1, 1)
        _(self.polynomialOrder, 0, 1, 1, 1)
        self.polySub.setLayout(layout)
        self._layout.addWidget(self.polySub, row, 0, 1, 2)
        row += 1

        '''Advanced Calculations'''
        self.advanced = CollapsibleSection('Skip Advanced Analysis', 200, self)
        self.advanced.stateChanged.connect(self._updateSize)
        self.advanced.setToolTip("If this box is ticked then some of the less common analyses will be skipped. This saves time and harddrive space.")
        self.autoCorrStopIndex = QHSpinBox()
        self.autoCorrStopIndex.setToolTip("Autocorrelation slope is determined by fitting a line to the first values of the autocorrelation function. This value determines how many values to include in this linear fit.")
        self.minSubCheckBox = QCheckBox("MinSub")
        self.minSubCheckBox.setToolTip("The calculation of autocorrelation decay slope involves taking the natural logarithm of of the autocorrelation. However noise often causes the autocorrelation to have negative values which causes problems for the logarithm. Checking this box adds an offset to the autocorrelation so that no values are negative.")
        layout = QGridLayout()
        _ = layout.addWidget
        _(QLabel("AutoCorr Stop Index"), 0, 0, 1, 1)
        _(self.autoCorrStopIndex, 0, 1, 1, 1)
        _(self.minSubCheckBox, 1, 0, 1, 1)
        self.advanced.setLayout(layout)
        self._layout.addWidget(self.advanced, row, 0, 1, 4)
        row += 1

        self._updateSize()

    def showEvent(self, a0: QtGui.QShowEvent) -> None:
        super().showEvent(a0)
        self._updateSize() #For some reason this must be done here and in the __init__ for it to start up properly.

    @property
    def analysisName(self) -> str:
        return self._analysisNameEdit.text()

    def _updateSize(self):
        height = 100  # give this much excess room.
        height += self.presets.height()
        height += self.hardwareCorrections.height()
        height += self.extraReflection.height()
        height += self.signalPrep.height()
        height += self.polySub.height()
        height += self.advanced.height()
        self._frame.setFixedHeight(height)

    # noinspection PyTypeChecker
    def loadFromSettings(self, settings: AnalysisSettings):
        self.filterOrder.setValue(settings.filterOrder)
        self.filterCutoff.setValue(settings.filterCutoff)
        self.polynomialOrder.setValue(settings.polynomialOrder)
        self.extraReflection.loadFromSettings(settings.numericalAperture, settings.referenceMaterial, settings.extraReflectanceId)
        self.wavelengthStop.setValue(settings.wavelengthStop)
        self.wavelengthStart.setValue(settings.wavelengthStart)
        self.advanced.setCheckState(2 if settings.skipAdvanced else 0)
        self.autoCorrStopIndex.setValue(settings.autoCorrStopIndex)
        self.minSubCheckBox.setCheckState(2 if settings.autoCorrMinSub else 0)

    def loadCameraCorrection(self, camCorr: Optional[CameraCorrection] = None):
        if camCorr is None: #Automatic camera corrections
            self.hardwareCorrections.setCheckState(2)
        else:
            self.hardwareCorrections.setCheckState(0)
            if camCorr.linearityPolynomial is None:
                self.linearityEdit.setText("1")
            else:
                self.linearityEdit.setText(",".join((str(i) for i in camCorr.linearityPolynomial)))
            self.darkCountBox.setValue(camCorr.darkCounts)

    def getSettings(self) -> AnalysisSettings:
        erId, refMaterial, numericalAperture = self.extraReflection.getSettings()
        return AnalysisSettings(filterOrder=self.filterOrder.value(),
                                 filterCutoff=self.filterCutoff.value(),
                                 polynomialOrder=self.polynomialOrder.value(),
                                 extraReflectanceId=erId,
                                 referenceMaterial=refMaterial,
                                 wavelengthStart=self.wavelengthStart.value(),
                                 wavelengthStop=self.wavelengthStop.value(),
                                 skipAdvanced=self.advanced.checkState() != 0,
                                 autoCorrMinSub=self.minSubCheckBox.checkState() != 0,
                                 autoCorrStopIndex=self.autoCorrStopIndex.value(),
                                 numericalAperture=numericalAperture)

    def getCameraCorrection(self) -> CameraCorrection:
        if self.hardwareCorrections.checkState() == 0:
            if self.linearityEdit.validator().state != QValidator.Acceptable:
                raise ValueError("The camera linearity correction input is not valid.")
            linText = self.linearityEdit.text()
            linearityPoly = tuple(float(i) for i in linText.split(','))
            cameraCorrection = CameraCorrection(self.darkCountBox.value(), linearityPoly)
        else:
            cameraCorrection = None
        return cameraCorrection


class CsvValidator(QValidator):
    stateChanged = QtCore.pyqtSignal(QValidator.State)

    def __init__(self):
        super().__init__()
        self.doubleValidator = QDoubleValidator()
        self.state = QValidator.Acceptable

    def validate(self, inp: str, pos: int):
        oldState = self.state
        for i in inp.split(','):
            ret = self.doubleValidator.validate(i, pos)
            if ret[0] == QValidator.Intermediate:
                self.state = ret[0]
                if self.state != oldState: self.stateChanged.emit(self.state)
                return self.state, inp, pos
            elif ret[0] == QValidator.Invalid:
                return ret
        self.state = QValidator.Acceptable
        if self.state != oldState: self.stateChanged.emit(self.state)
        return self.state, inp, pos


class VerticallyCompressedWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setLayout(QVBoxLayout())
        self._contentsFrame = QFrame()
        spacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout().addWidget(self._contentsFrame)
        self.layout().addItem(spacer)
        self.layout = self._layout # override methods
        self.setLayout = self._setLayout

    def _layout(self) -> QLayout:
        return self._contentsFrame.layout()

    def _setLayout(self, layout: QLayout):
        self._contentsFrame.setLayout(layout)