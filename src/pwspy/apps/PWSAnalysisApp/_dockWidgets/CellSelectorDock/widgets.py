import json
import os
import typing
from json import JSONDecodeError
from typing import List, Optional, Type

from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QPushButton, QTableWidgetItem, QTableWidget, QAbstractItemView, QMenu, QWidget, QMessageBox
from pwspy.dataTypes import AcqDir

from pwspy.apps.PWSAnalysisApp._sharedWidgets.dictDisplayTree import DictDisplayTree, DictDisplayTreeDialog
from pwspy.apps.PWSAnalysisApp._sharedWidgets.tables import NumberTableWidgetItem
from pwspy.dataTypes import ICMetaData

def evalToolTip(cls: Type[QWidget], method):
    """Given a QWidget and a function that returns a string, this decorator returns a modified class that will evaluate
    the function each time the tooltip is requested."""
    class newClass(cls):
        def event(self, e: QtCore.QEvent):
            if e.type() == QtCore.QEvent.ToolTip:
                self.setToolTip(method())
            return super().event(e)
    return newClass


class CellTableWidgetItem:
    def __init__(self, acq: AcqDir, label: str, num: int):
        self.acqDir = acq
        self.num = num
        self.path = label
        self.notesButton = evalToolTip(QPushButton, acq.getNotes)("Open")
        self.notesButton.setFixedSize(40, 30)
        self.pathLabel = QTableWidgetItem(self.path)
        self.numLabel = NumberTableWidgetItem(num)
        self.roiLabel = NumberTableWidgetItem(0)
        self.anLabel = NumberTableWidgetItem(0)
        self.notesButton.released.connect(self.acqDir.editNotes)
        self._items = [self.pathLabel, self.numLabel, self.roiLabel, self.anLabel]
        self.refresh()
        self.mdPath = os.path.join(self.acqDir.filePath, 'AnAppPrefs.json')
        try:
            with open(self.mdPath, 'r') as f:
                self.md = json.load(f)
        except (JSONDecodeError, FileNotFoundError):
            self.md = {'invalid': False, 'reference': False}
        self.setInvalid(self._invalid) #Update item color based on saved status. Since invalid status overrides reference status we must do this first.
        self.setReference(self._reference)

    @property
    def row(self):
        """Since this can be added to a table that uses sorting we can't know that the row number will remain constant.
        This should return the correct row number."""
        return self.numLabel.row()

    @property
    def _invalid(self): return self.md['invalid']

    @_invalid.setter
    def _invalid(self, val): self.md['invalid'] = val

    @property
    def _reference(self): return self.md['reference']

    @_reference.setter
    def _reference(self, val): self.md['reference'] = val

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

    def setSelected(self, select: bool):
        for i in self._items:
            i.setSelected(select)

    def close(self):
        with open(self.mdPath, 'w') as f:
            json.dump(self.md, f)

    def __del__(self):
        self.close() #This is here just in case. realistacally del rarely gets called, need to manually close each cell item.

    def refresh(self):
        self.roiLabel.setNumber(len(self.acqDir.getRois()))
        self.anLabel.setNumber(len(self.acqDir.pws.getAnalyses()))
        if self.acqDir.getNotes() != '':
            self.notesButton.setStyleSheet('QPushButton { background-color: lightgreen;}')
        else:
            self.notesButton.setStyleSheet('QPushButton { background-color: lightgrey;}')

        nameNums = [(name, num) for name, num, fformat in self.acqDir.getRois()]
        if len(nameNums) > 0:
            names = set(list(zip(*nameNums))[0])
            d = {name: [num for nname, num in nameNums if nname == name] for name in names}
            self.roiLabel.setToolTip("\n".join([f'{k}: {v}' for k, v in d.items()]))

        self.anLabel.setToolTip(', '.join(self.acqDir.pws.getAnalyses()))


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
        #This makes the items stay looking selected even when the table is inactive
        self.setStyleSheet("""QTableWidget::item:active {
                                selection-background-color: darkblue;
                                selection-color: white;}
                                
                                QTableWidget::item:inactive {
                                selection-background-color: darkblue;
                                selection-color: white;}""")
        self.palette().setColor(QPalette.Highlight, QtGui.QColor("#3a7fc2")) # This makes it so the selected cells stay colored even when the table isn't active.
        self.palette().setColor(QPalette.HighlightedText, QtCore.Qt.white)

    @property
    def cellItems(self) -> List[CellTableWidgetItem]:
        return self._cellItems

    def showContextMenu(self, point: QtCore.QPoint):
        if len(self.selectedCellItems) > 0:
            menu = QMenu("Context Menu")
            state = not self.selectedCellItems[0].isInvalid()
            stateString = "Disable Cell(s)" if state else "Enable Cell(s)"
            refState = not self.selectedCellItems[0].isReference()
            refStateString = "Set as Reference" if refState else "Unset as Reference"
            invalidAction = menu.addAction(stateString)
            invalidAction.triggered.connect(lambda: self.toggleSelectedCellsInvalid(state))
            refAction = menu.addAction(refStateString)
            refAction.triggered.connect(lambda: self.toggleSelectedCellsReference(refState))
            mdAction = menu.addAction("Display Metadata")
            mdAction.triggered.connect(self.displayCellMetadata)
            menu.exec(self.mapToGlobal(point))

    def displayCellMetadata(self):
        for i in self.selectedCellItems:
            d = DictDisplayTreeDialog(self, i.acqDir.pws._dict, title=os.path.join(i.path, f"Cell{i.num}"))
            d.show()

    def toggleSelectedCellsInvalid(self, state: bool):
        changedItems = []
        for i in self.selectedCellItems:
            if i.isInvalid() != state:
                i.setInvalid(state)
                changedItems.append(i)
        if state:
            self.referencesChanged.emit(False, changedItems)

    def toggleSelectedCellsReference(self, state: bool) -> None:
        items = self.selectedCellItems
        changedItems = []
        for i in items:
            if (i.isReference() != state) and (not i.isInvalid()):
                i.setReference(state)
                changedItems.append(i)
        self.referencesChanged.emit(state, changedItems)

    @property
    def selectedCellItems(self) -> typing.List[CellTableWidgetItem]:
        """Returns the rows that have been selected."""
        rowIndices = [i.row() for i in self.selectedIndexes()[::self.columnCount()]]
        rowIndices.sort()
        _ = {i.row: i for i in self._cellItems} #Cell items keyed by their current row position.
        return [_[i] for i in rowIndices]

    @property
    def analyzableCells(self) -> typing.List[CellTableWidgetItem]:
        return [i for i in self._cellItems if not (i.isInvalid() or i.isReference())]

    def addCellItem(self, item: CellTableWidgetItem) -> None:
        row = len(self._cellItems)
        self.setSortingEnabled(False)  # The fact that we are adding items assuming its the last row is a problem if sorting is on.
        self.setRowCount(row + 1)
        self.setItem(row, 0, item.pathLabel)
        self.setItem(row, 1, item.numLabel)
        self.setItem(row, 2, item.roiLabel)
        self.setItem(row, 3, item.anLabel)
        self.setCellWidget(row, 4, item.notesButton)
        self.setSortingEnabled(True)
        self._cellItems.append(item)

    def clearCellItems(self) -> None:
        self.setRowCount(0)
        for c in self._cellItems:
            c.close() #This causes the cell item to save it's metadata.
        self._cellItems = []
        self.itemsCleared.emit()


class ReferencesTableItem(QTableWidgetItem):
    def __init__(self, item: CellTableWidgetItem):
        self.item = item
        super().__init__(f"Cell{item.num}")
        self.setToolTip(os.path.join(item.pathLabel.text(), f'Cell{item.num}'))


class ReferencesTable(QTableWidget):
    def __init__(self, parent: QWidget, cellTable: CellTableWidget):
        super().__init__(parent)
        #This makes the items stay looking selected even when the table is inactive
        self.setStyleSheet("""QTableWidget::item:active {   
                                selection-background-color: darkblue;
                                selection-color: white;}

                                QTableWidget::item:inactive {
                                selection-background-color: darkblue;
                                selection-color: white;}""")
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(('Reference',))
        self.setRowCount(0)
        self.verticalHeader().hide()
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        cellTable.referencesChanged.connect(self.updateReferences)
        cellTable.itemsCleared.connect(self.clearItems)
        self._references: typing.List[CellTableWidgetItem] = []

    def showContextMenu(self, point: QtCore.QPoint):
        items = self.selectedItems()
        if len(items) > 0:
            menu = QMenu("Context Menu")
            refStateString = "Unset as Reference"
            refAction = menu.addAction(refStateString)
            refAction.triggered.connect(lambda: self.updateReferences(False, [i.item for i in self.selectedItems()]))
            menu.exec(self.mapToGlobal(point))

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
                    item.setReference(False)
                    # find row number
                    for i in range(self.rowCount()):
                        if item is self.item(i, 0).item:
                            self.removeRow(i)
                            break

    def clearItems(self):
        self.setRowCount(0)
        self._references = []

    @property
    def selectedReferenceMeta(self) -> Optional[AcqDir]:
        """Returns the ICMetadata that have been selected. Return None if nothing is selected."""
        items: List[ReferencesTableItem] = self.selectedItems()
        assert len(items) <= 1
        if len(items) == 0:
            return None
        else:
            return items[0].item.acqDir
