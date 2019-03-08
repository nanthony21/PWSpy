import typing

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QTableWidget, QAbstractItemView, QApplication, QTableWidgetItem, QPushButton, QMenu, QWidget

from pwspy.analysis.analysisResults import AbstractAnalysisResults
from pwspy.imCube.ICMetaDataClass import ICMetaData
import os


class CopyableTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.setSelectionMode = lambda: (_ for _ in ()).throw(NotImplementedError("The CopyableTable class requires the selection mode to remain as `contiguous`"))


    def keyPressEvent(self, event):
        if event.matches(QtGui.QKeySequence.Copy):
            self.copy()
        else:
            super().keyPressEvent(event)

    def copy(self):
        try:
            sel = self.selectedRanges()[0]
            t = '\t'.join(
                [self.horizontalHeaderItem(i).text() for i in range(sel.leftColumn(), sel.rightColumn() + 1)]) + '\n'
            for i in range(sel.topRow(), sel.bottomRow() + 1):
                for j in range(sel.leftColumn(), sel.rightColumn() + 1):
                    if t[-1] != '\n': t += '\t'
                    item = self.item(i, j)
                    t += ' ' if item is None else item.text()
                t += '\n'
            QApplication.clipboard().setText(t)
        except Exception as e:
            print("Copy Failed: ", e)


class NumberTableWidgetItem(QTableWidgetItem):
    def __init__(self, num: float):
        super().__init__(str(num))
        num = float(num)  # in case the constructor is called with a string.
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)  # read only
        self.number = num

    def __lt__(self, other: 'NumberTableWidgetItem'):
        return self.number < other.number

    def __gt__(self, other: 'NumberTableWidgetItem'):
        return self.number > other.number

class ResultsTableItem(AbstractAnalysisResults):
    def __init__(self, meta: ICMetaData, maskName: str, maskNum: int, ):

class ResultsTable(CopyableTable):
    itemsCleared = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setSortingEnabled(True)
        self._items = []

    def addItem(self, item: ResultsTableItem) -> None:
        row = len(self._items)
        # The fact that we are adding items assuming its the last row is a problem is sorting is on.
        self.setSortingEnabled(False)
        self.setRowCount(row + 1)
        self.setItem(row, 0, item._pathLabel)
        self.setItem(row, 1, item._numLabel)
        self.setItem(row, 2, item._roiLabel)
        self.setItem(row, 3, item._anLabel)
        self.setCellWidget(row, 4, item._notesButton)
        self.setSortingEnabled(True)
        self._items.append(item)

    def clearCellItems(self) -> None:
        self.setRowCount(0)
        self._items = []
        self.itemsCleared.emit()




class CellTableWidgetItem:
    cube: ICMetaData

    def __init__(self, cube: ICMetaData, label: str, num: int):
        self.cube = cube
        self.num = num
        self.path = label
        self._notesButton = QPushButton("Open")
        self._notesButton.setFixedSize(40, 30)
        self._pathLabel = QTableWidgetItem(self.path)
        self._numLabel = NumberTableWidgetItem(num)
        self._roiLabel = NumberTableWidgetItem(len(cube.getMasks()))
        self._anLabel = NumberTableWidgetItem(len(cube.getAnalyses()))
        self._notesButton.released.connect(self.cube.editNotes)
        self._items = [self._pathLabel, self._numLabel, self._roiLabel, self._anLabel]
        self._invalid = False
        self._reference = False

    def setInvalid(self, invalid: bool):
        if invalid:
            self._setItemColor(QtCore.Qt.red)
            self._reference = False
        else:
            self._setItemColor(QtCore.Qt.white)
        self._invalid = invalid

    def setReference(self, reference: bool) -> None:
        if self.isInvalid():
            return
        if reference:
            self._setItemColor(QtCore.Qt.green)
        else:
            self._setItemColor(QtCore.Qt.white)
        self._reference = reference

    def _setItemColor(self, color):
        for i in self._items:
            i.setBackground(color)

    def isInvalid(self) -> bool:
        return self._invalid

    def isReference(self) -> bool:
        return self._reference


class CellTableWidget(QTableWidget):
    referencesChanged = QtCore.pyqtSignal(bool, list)
    itemsCleared = QtCore.pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        columns = ('Path', 'Cell#', 'ROIs', 'Analyses', 'Notes')
        self.setRowCount(0)
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.verticalHeader().hide()
        [self.setColumnWidth(i, w) for i, w in zip(range(len(columns)), [60, 40, 40, 50, 40])]
        self._cellItems = []

    def showContextMenu(self, point: QtCore.QPoint):
        menu = QMenu("Context Menu")
        state = not self.selectedCellItems[0].isInvalid()
        stateString = "Disable Cell(s)" if state else "Enable Cell(s)"
        refState = not self.selectedCellItems[0].isReference()
        refStateString = "Set as Reference" if refState else "Unset as Reference"
        invalidAction = menu.addAction(stateString)
        invalidAction.triggered.connect(lambda: self.toggleSelectedCellsInvalid(state))
        refAction = menu.addAction(refStateString)
        refAction.triggered.connect(lambda: self.toggleSelectedCellsReference(refState))
        menu.exec(self.mapToGlobal(point))

    def toggleSelectedCellsInvalid(self, state: bool):
        for i in self.selectedCellItems:
            i.setInvalid(state)

    def toggleSelectedCellsReference(self, state: bool) -> None:
        items = self.selectedCellItems
        for i in items:
            i.setReference(state)
        self.referencesChanged.emit(state, items)

    @property
    def selectedCellItems(self) -> typing.List[CellTableWidgetItem]:
        """Returns the rows that have been selected."""
        rowIndices = [i.row() for i in self.selectedIndexes()[::self.columnCount()]]
        rowIndices.sort()
        return [self._cellItems[i] for i in rowIndices]

    @property
    def analyzableCells(self) -> typing.List[CellTableWidgetItem]:
        return [i for i in self._cellItems if not (i.isInvalid() or i.isReference())]

    def addCellItem(self, item: CellTableWidgetItem) -> None:
        row = len(self._cellItems)
        self.setSortingEnabled(
            False)  # The fact that we are adding items assuming its the last row is a problem is sorting is on.
        self.setRowCount(row + 1)
        self.setItem(row, 0, item._pathLabel)
        self.setItem(row, 1, item._numLabel)
        self.setItem(row, 2, item._roiLabel)
        self.setItem(row, 3, item._anLabel)
        self.setCellWidget(row, 4, item._notesButton)
        self.setSortingEnabled(True)
        self._cellItems.append(item)

    def clearCellItems(self) -> None:
        self.setRowCount(0)
        self._cellItems = []
        self.itemsCleared.emit()


class ReferencesTableItem(QTableWidgetItem):
    def __init__(self, item: CellTableWidgetItem):
        self.item = item
        super().__init__(os.path.join(item._pathLabel.text(), f'Cell{item.num}'))


class ReferencesTable(QTableWidget):
    def __init__(self, parent: QWidget, cellTable: CellTableWidget):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(('Reference',))
        self.setRowCount(0)
        self.verticalHeader().hide()
        cellTable.referencesChanged.connect(self.updateReferences)
        cellTable.itemsCleared.connect(self.clearItems)
        self._references: typing.List[CellTableWidgetItem] = []

    def updateReferences(self, state: bool, items: typing.List[CellTableWidgetItem]):
        if state:
            for item in items:
                if item not in self._references:
                    row = len(self._references)
                    self.setRowCount(row + 1)
                    self.setItem(row, 0, ReferencesTableItem(item))
                    self._references.append(item)
        else:
            for item in items:
                if item in self._references:
                    self._references.remove(item)
                    # find row number
                    for i in range(self.rowCount()):
                        if item is self.item(i, 0).item:
                            self.removeRow(i)
                            break

    def clearItems(self):
        self.setRowCount(0)
        self._references = []

    @property
    def selectedReferenceMeta(self) -> typing.List[ICMetaData]:
        """Returns the rows that have been selected."""
        items: ReferencesTableItem = self.selectedItems()
        assert len(items) <= 1
        return items[0].item.cube