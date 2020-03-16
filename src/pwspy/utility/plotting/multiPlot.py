from typing import List

from PyQt5 import QtCore
from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton, QApplication
import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5 import NavigationToolbar2QT
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.image import AxesImage


class MultiPlot(QWidget):
    def __init__(self, artists: List[List[Artist]], title: str, parent=None):
        """A widget that displays an image."""
        QWidget.__init__(self, parent=parent, flags=QtCore.Qt.Window)
        self.setWindowTitle(title)
        layout = QGridLayout()
        self.artists = artists
        self.figure = artists[0][0].figure
        self.ax: Axes = self.artists[0][0].axes

        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFocusPolicy(QtCore.Qt.ClickFocus) #Not sure what this is for
        self.canvas.setFocus()
        self.figure.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)

        self.previousButton = QPushButton('←')
        self.nextButton = QPushButton('→')
        self.previousButton.released.connect(self.showPreviousIm)
        self.nextButton.released.connect(self.showNextIm)


        layout.addWidget(self.canvas, 0, 0, 8, 8)
        layout.addWidget(self.previousButton, 9, 1, 1, 1)
        layout.addWidget(self.nextButton, 9, 2, 1, 1)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self), 10, 0, 1, 4)

        layout.setRowStretch(0, 1)  # This causes the plot to take up all the space that isn't needed by the other widgets.
        self.setLayout(layout)

        self.index = 0
        self._updateDisplayedImage()


    def showPreviousIm(self):
        self.index -= 1
        if self.index < 0:
            self.index = len(self.artists) - 1
        self._updateDisplayedImage()

    def showNextIm(self):
        self.index += 1
        if self.index >= len(self.artists):
            self.index = 0
        self._updateDisplayedImage()

    def imshow(self, *args, **kwargs):
        self.artists.append([self.ax.imshow(*args, **kwargs)])
        self.index = len(self.artists)-1
        self._updateDisplayedImage()

    def _updateDisplayedImage(self):
        for i, frame in enumerate(self.artists):
            for artist in frame:
                artist.set_visible(self.index==i)
        self.canvas.draw_idle()


if __name__ == '__main__':
    import sys
    import matplotlib.pyplot as plt
    plt.ion()
    # a: AxesImage = None
    # a.se
    app = QApplication(sys.argv)
    sh = (1024, 1024)
    ims = [[plt.imshow(np.random.random(sh)), plt.text(100, 100, str(i))] for i in range(3)]
    mp = MultiPlot(ims, "Hey")
    mp.ax.get_xaxis().set_visible(False)
    mp.ax.get_yaxis().set_visible(False)
    [mp.imshow(np.random.random(sh)) for i in range(3)]
    mp.show()
    sys.exit(app.exec())
