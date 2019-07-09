from __future__ import annotations
import os
from typing import Optional

from PyQt5 import QtCore
from PyQt5.QtCore import QObject, QThread
from PyQt5.QtWidgets import QMessageBox, QApplication, QWidget
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from pwspy.apps.PWSAnalysisApp.sharedWidgets.dialogs import BusyDialog
from pwspy.apps.sharedWidgets.extraReflectionManager.ERDataComparator import ERDataComparator
from pwspy.apps.sharedWidgets.extraReflectionManager.ERDataDirectory import ERDataDirectory, EROnlineDirectory
from .ERSelectorWindow import ERSelectorWindow
from .ERUploaderWindow import ERUploaderWindow
from pwspy.imCube.ExtraReflectanceCubeClass import ERMetadata
from pwspy.utility.GoogleDriveDownloader import GoogleDriveDownloader

from pwspy.apps.PWSAnalysisApp import applicationVars

#TODO this whole submodule is kind of a fragile mess and probably not organized in a smart way.

class ERManager:
    def __init__(self, filePath: str):
        self._directory = filePath
        self._downloader: GoogleDriveDownloader = None
        indexPath = os.path.join(self._directory, 'index.json')
        if not os.path.exists(indexPath):
            self.download('index.json')
        dataDir = ERDataDirectory(self._directory, self)
        onlineDir = EROnlineDirectory(self)
        self.dataComparator = ERDataComparator(dataDir, onlineDir)

    def createSelectorWindow(self, parent: QWidget):
        return ERSelectorWindow(self, parent)

    def createManagerWindow(self, parent: QWidget):
        return ERUploaderWindow(self, parent)

    def rescan(self):
        self.dataComparator.rescan()

    def download(self, fileName: str, directory: Optional[str] = None, parentWidget: Optional[QWidget] = None):
        """Begin downloading `fileName` in a separate thread. Use the main thread to update a progress bar.
        If directory is left blank then file will be downloaded to the ERManager main directory"""
        if self._downloader is None:
            self._downloader = _QtGoogleDriveDownloader(applicationVars.googleDriveAuthPath)
        if directory is None:
            directory = self._directory  # Use the main directory
        if fileName not in [i['name'] for i in self._downloader.allFiles]:
            raise ValueError(f"File {fileName} does not exist on google drive")
        t = _DownloadThread(self._downloader, fileName, directory)
        b = BusyDialog(parentWidget, f"Downloading {fileName}. Please Wait...", progressBar=True)
        t.finished.connect(b.accept)
        self._downloader.progress.connect(b.setProgress)
        t.errorOccurred.connect(lambda e: QMessageBox.information(parentWidget, 'Drive Downloader Thread', str(e)))
        t.start()
        b.exec()

    def upload(self, fileName: str):
        parentId = self._downloader.getIdByName("ExtraReflectanceCubes")
        filePath = os.path.join(self._directory, fileName)
        self._downloader.uploadFile(filePath, parentId)

    def getMetadataFromId(self, Id: str) -> ERMetadata:
        """Given the Id string for ExtraReflectanceCube this will search the index.json and return the ERMetadata file"""
        try:
            match = [item for item in self.index['reflectanceCubes'] if item['idTag'] == Id][0]
        except IndexError:
            raise IndexError(f"An ExtraReflectanceCube with idTag {Id} was not found in the index.json file at {self._directory}.")
        return ERMetadata.fromHdfFile(self._directory, match['name'])


class _DownloadThread(QThread):
    """A QThread to download from google drive"""
    errorOccurred = QtCore.pyqtSignal(Exception)
    def __init__(self, downloader, fileName, directory):
        super().__init__()
        self.downloader = downloader
        self.fileName = fileName
        self.directory = directory
    def run(self):
        try:
            files = self.downloader.getFolderIdContents(
                self.downloader.getIdByName('PWSAnalysisAppHostedFiles'))
            files = self.downloader.getFolderIdContents(
                self.downloader.getIdByName('ExtraReflectanceCubes', fileList=files))
            fileId = self.downloader.getIdByName(self.fileName, fileList=files)
            self.downloader.downloadFile(fileId, os.path.join(self.directory, self.fileName))
        except Exception as e:
            self.errorOccurred.emit(e)

class _QtGoogleDriveDownloader(GoogleDriveDownloader, QObject):
    """Same as the standard google drive downloader except it emits a progress signal after each chunk downloaded."""
    progress = QtCore.pyqtSignal(int)
    def __init__(self, authPath: str):
        GoogleDriveDownloader.__init__(self, authPath)
        QObject.__init__(self)

    def downloadFile(self, Id: int, savePath: str):
        """Save the file with `id` to `savePath`"""
        fileRequest = self.api.files().get_media(fileId=Id)
        with open(savePath, 'wb') as f:
            downloader = MediaIoBaseDownload(f, fileRequest)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                self.progress.emit(int(status.progress() * 100))



