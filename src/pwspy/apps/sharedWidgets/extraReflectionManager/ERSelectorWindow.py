from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QMessageBox, QWidget, QCheckBox, QVBoxLayout, \
    QPushButton, QLineEdit, QComboBox, QGridLayout, QLabel, QDialogButtonBox, QHBoxLayout, QAbstractItemView

from pwspy import moduleConsts
from pwspy.apps.PWSAnalysisApp.sharedWidgets.tables import DatetimeTableWidgetItem
from pwspy.imCube.ExtraReflectanceCubeClass import ERMetadata
import numpy as np

import typing
if typing.TYPE_CHECKING:
    from pwspy.apps.sharedWidgets.extraReflectionManager import ERManager
    from pwspy.apps.sharedWidgets.extraReflectionManager.ERIndex import ERIndexCube


class ERTableWidgetItem:
    def __init__(self, fileName: str, description: str, idTag: str, name: str, downloaded: bool):
        self.fileName = fileName
        self.description = description
        self.idTag = idTag
        self.systemName = self.idTag.split('_')[1]
        self.datetime = datetime.strptime(self.idTag.split('_')[2], moduleConsts.dateTimeFormat)
        self.name = name

        self.sysItem = QTableWidgetItem(self.systemName)
        self.dateItem = DatetimeTableWidgetItem(self.datetime)
        self._checkBox = QCheckBox()
        self.checkBoxWidget = QWidget()
        l = QHBoxLayout()
        l.setAlignment(QtCore.Qt.AlignCenter)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self._checkBox)
        self.checkBoxWidget.setLayout(l)
        self.sysItem.setToolTip('\n'.join([f'File Name: {self.fileName}', f'ID: {self.idTag}', f'Description: {self.description}']))
        if downloaded:
            #Item can be selected. Checkbox no longer usable
            self._checkBox.setCheckState(QtCore.Qt.Checked)
            self._checkBox.setEnabled(False)
            self.sysItem.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        else:
            #Checkbox can be checked to allow downloading. Nothing else can be done.
            self.sysItem.setFlags(QtCore.Qt.NoItemFlags)
            self.dateItem.setFlags(QtCore.Qt.NoItemFlags)
        self._downloaded = downloaded

    @property
    def downloaded(self): return self._downloaded

    def isChecked(self):
        return self._checkBox.isChecked()


class ERSelectorWindow(QDialog):
    selectionChanged = QtCore.pyqtSignal(ERMetadata)
    def __init__(self, manager: ERManager, parent: Optional[QWidget] = None):
        self._manager = manager
        self._selectedId: str = None
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Extra Reflectance Selector")
        self.setLayout(QVBoxLayout())
        self.table = QTableWidget(self)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(self.displayInfo)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setRowCount(0)
        self.table.setColumnCount(3)
        self.table.setSortingEnabled(True)
        self.table.setHorizontalHeaderLabels([" ", "System", "Date"])
        self.table.setColumnWidth(0, 10)

        self.downloadButton = QPushButton("Download Checked Items")
        self.downloadButton.released.connect(self._downloadCheckedItems)
        self.updateButton = QPushButton('Update Index')
        self.updateButton.setToolTip("Update the index containing information about which Extra Reflectance Cubes are available for download.")
        self.updateButton.released.connect(self._updateIndex)
        self.acceptSelectionButton = QPushButton("Accept Selection")
        self.acceptSelectionButton.released.connect(self.accept)
        self.layout().addWidget(self.table)
        l = QHBoxLayout()
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self.downloadButton)
        l.addWidget(self.updateButton)
        w = QWidget()
        w.setLayout(l)
        self.layout().addWidget(w)
        self.layout().addWidget(self.acceptSelectionButton)
        self._initialize()

    def _updateIndex(self):
        self._manager.download("index.json")
        self._initialize()

    def _initialize(self):
        self._manager.rescan()
        self._items: List[ERTableWidgetItem] = []
        for item in self._manager.dataDir.index.cubes:
            self._addItem(item)

    def _addItem(self, item: ERIndexCube):
        tableItem = ERTableWidgetItem(fileName=item.fileName, description=item.description, idTag=item.idTag, name=item.name, downloaded=self._manager.dataDir.status.loc[item.idTag]['idTagMatch'])
        self._items.append(tableItem)
        self.table.setRowCount(len(self._items))
        self.table.setCellWidget(self.table.rowCount() - 1, 0, tableItem.checkBoxWidget)
        self.table.setItem(self.table.rowCount() - 1, 1, tableItem.sysItem)
        self.table.setItem(self.table.rowCount() - 1, 2, tableItem.dateItem)

    def displayInfo(self, item: QTableWidgetItem):
        item = [i for i in self._items if i.sysItem.row() == item.row()][0]
        message = QMessageBox.information(self, item.name, '\n\n'.join([f'FileName: {item.fileName}',
                                                                      f'ID Tag: {item.idTag}',
                                                                      f'Description: {item.description}']))

    def _downloadCheckedItems(self):
        for item in self._items:
            if item.isChecked() and not item.downloaded:
                # If the checkbox is enabled then it hasn't been downloaded yet. if it is checked then it should be downloaded
                self._manager.download(item.fileName)
        self._initialize()

    def accept(self) -> None:
        try:
            rowIndex = [i.row() for i in self.table.selectedIndexes()[::self.table.columnCount()]][0] #  There should be only one.
            self.setSelection(self._items[rowIndex].idTag)
        except IndexError: # Nothing was selected
            pass
        super().accept()

    def getSelectedId(self):
        return self._selectedId

    def setSelection(self, idTag: str):
        md = self._manager.getMetadataFromId(idTag)
        self._selectedId = idTag
        self.selectionChanged.emit(md)

